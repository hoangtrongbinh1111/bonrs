"""Web app: multi-user UI over the same pipeline. Run: uvicorn bonrs.web:app --host 0.0.0.0 --port 8765

Trust model: members are tenants. Everything a run's agent can write (the run folder, the tenant folder) is read
through safeio (no symlink/FIFO/hard-link tricks) and every job, git call or file tool on tenant data runs through
sandbox (the owner's own uid in Docker, a scrubbed environment everywhere). Secrets never enter a job.
"""
import json, math, os, re, secrets, shutil, signal, subprocess, threading, time, traceback, unicodedata
from datetime import datetime
from pathlib import Path
import requests, yaml
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool, iterate_in_threadpool
from . import ROOT, DATA, RUNS, KNOWLEDGE, db, kb, pipeline, remote, safeio, sandbox

app = FastAPI(title="bonrs", docs_url=None, redoc_url=None, openapi_url=None)
ALLOWED_UPLOAD = {".pdf", ".docx", ".md", ".txt", ".csv", ".zip", ".html", ".tex", ".bib", ".json"}
MAX_UPLOAD, MAX_FILES = 50 * 1024 * 1024, 20
MAX_BODY = MAX_UPLOAD * MAX_FILES + (1 << 20)
SAFE = re.compile(r"^[A-Za-z0-9._/\-]+$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}$")
UPSTREAM = os.environ.get("BONRS_ANTHROPIC_UPSTREAM", "https://api.anthropic.com").rstrip("/")
SELF_URL = os.environ.get("BONRS_SELF_URL", "http://127.0.0.1:8765").rstrip("/")
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
       "img-src 'self' data: blob:; connect-src 'self' https://api.openalex.org; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")


# ---------------- request guard + security headers ----------------
@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        n = request.headers.get("content-length")  # cap every body before anything buffers it (no chunked uploads)
        if request.headers.get("transfer-encoding") and not n: return JSONResponse({"detail": "length required"}, 411)
        if n and (not n.isdigit() or int(n) > (MAX_BODY if "multipart/form-data" in request.headers.get("content-type", "")
                                              else 64 << 20 if path.startswith("/api/llm/") else 8 << 20)): return JSONResponse({"detail": "too large"}, 413)
        origin = request.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != request.headers.get("host"): return JSONResponse({"detail": "bad origin"}, 403)  # CSRF
        if request.headers.get("sec-fetch-site") == "cross-site": return JSONResponse({"detail": "cross-site request"}, 403)
        if "multipart/form-data" in request.headers.get("content-type", ""):  # authenticate before the body is parsed/spooled
            n = request.headers.get("content-length")
            if not n or not n.isdigit(): return JSONResponse({"detail": "length required"}, 411)
            if int(n) > MAX_BODY: return JSONResponse({"detail": "too large"}, 413)
            if not _session_user(request.cookies.get("bonrs")): return JSONResponse({"detail": "login required"}, 401)
    resp = await call_next(request)
    h = resp.headers
    h.setdefault("X-Content-Type-Options", "nosniff"); h.setdefault("Referrer-Policy", "no-referrer"); h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin"); h.setdefault("Content-Security-Policy", CSP)
    if path.startswith("/api/"): h.setdefault("Cache-Control", "no-store")
    return resp


async def body(request: Request) -> dict:
    raw = await request.body()
    if not raw: return {}
    try: b = json.loads(raw)
    except ValueError: raise HTTPException(400, "invalid JSON")
    if not isinstance(b, dict): raise HTTPException(400, "JSON object expected")
    return b


def _str(b: dict, k: str, n: int = 200, default="") -> str:
    v = b.get(k, default)
    if v is None: return default
    if not isinstance(v, (str, int, float)) or isinstance(v, bool): raise HTTPException(400, f"{k}: text expected")
    return str(v).strip()[:n]


# ---------------- auth ----------------
def _session_user(cookie):
    t = db.verify(cookie)
    if not t: return None
    u = db.one("SELECT id,email,role,sv,disabled,api_key IS NOT NULL AS has_key,oauth_token IS NOT NULL AS has_oauth FROM users WHERE id=?", t[0])
    if not u or u["disabled"] or u["sv"] != t[1] or u["role"] not in ("admin", "member"): return None
    return {k: u[k] for k in ("id", "email", "role", "has_key", "has_oauth")}


def user(request: Request) -> dict:
    u = _session_user(request.cookies.get("bonrs"))
    if not u: raise HTTPException(401, "login required")
    return u


def admin(u=Depends(user)):
    if u["role"] != "admin": raise HTTPException(403, "admin only")
    return u


def run_of(slug: str, u: dict) -> Path:
    if not SLUG.match(slug or ""): raise HTTPException(404, "no such run")
    r = db.one("SELECT owner FROM runs WHERE slug=?", slug)
    if not r: raise HTTPException(404, "no such run")
    if r["owner"] != u["id"] and u["role"] != "admin": raise HTTPException(403, "not your run")
    return RUNS / slug


def owner_of(slug: str) -> int: return int((db.one("SELECT owner FROM runs WHERE slug=?", slug) or {}).get("owner") or 0)


def rel_ok(rel: str) -> str:
    if not rel or not SAFE.match(rel) or ".." in rel.split("/") or rel.startswith("/"): raise HTTPException(400, "bad path")
    return rel


def safe_path(base: Path, rel: str) -> Path:
    """Server-owned trees only (knowledge base). Tenant-writable trees go through safeio."""
    p = (base / rel_ok(rel)).resolve()
    try: p.relative_to(base.resolve())
    except ValueError: raise HTTPException(400, "bad path")
    return p


_FAILS: dict[str, list[float]] = {}
_DUMMY = db.hash_pw(secrets.token_hex(8))  # same scrypt cost for unknown emails: no account-existence timing oracle


LIMITS = {"p": 8, "e": 30, "i": 60}  # per email+IP, per email, per IP: one noisy client cannot lock out everyone behind the same proxy


def _limited(*keys) -> bool:
    now = time.time()
    for k in keys: _FAILS[k] = [t for t in _FAILS.get(k, []) if now - t < 900]
    if len(_FAILS) > 50_000: _FAILS.clear()  # bounded memory
    return any(len(_FAILS[k]) >= LIMITS[k[0]] for k in keys)


def _cookie(resp, request, u):
    resp.set_cookie("bonrs", db.sign(u["id"], u["sv"]), httponly=True, samesite="strict", max_age=14 * 86400, path="/",
                    secure=os.environ.get("BONRS_SECURE_COOKIE") == "1" or request.url.scheme == "https")


@app.post("/api/login")
async def login(request: Request):
    b = await body(request); email = _str(b, "email", 254).lower(); pw = _str(b, "password", 1000)
    ip = request.client.host if request.client else "-"; keys = (f"p:{email}|{ip}", f"e:{email}", f"i:{ip}")
    if _limited(*keys): raise HTTPException(429, "too many attempts, try again in 15 minutes")
    u = db.one("SELECT * FROM users WHERE email=? AND disabled=0", email)
    ok = db.check_pw(pw, u["pw"] if u else _DUMMY) and u is not None
    if not ok:
        for k in keys: _FAILS[k].append(time.time())
        raise HTTPException(401, "wrong email or password")
    r = JSONResponse({"ok": True}); _cookie(r, request, u); return r


@app.post("/api/logout")
def logout(request: Request):
    t = db.verify(request.cookies.get("bonrs"))
    if t: db.ex("UPDATE users SET sv=sv+1 WHERE id=? AND sv=?", t[0], t[1])  # revokes every copy of this cookie
    r = JSONResponse({"ok": True}); r.delete_cookie("bonrs", path="/"); return r


@app.get("/api/me")
def me(u=Depends(user)): return u


@app.put("/api/me/key")
async def my_key(request: Request, u=Depends(user)):
    k = _str(await body(request), "api_key", 300) or None
    db.ex("UPDATE users SET api_key=? WHERE id=?", k, u["id"]); return {"ok": True}


OAUTH = re.compile(r"^sk-ant-oat[A-Za-z0-9_\-]{10,400}$")


@app.put("/api/me/oauth")
async def my_oauth(request: Request, u=Depends(user)):
    """The user's own Claude Pro/Max subscription: the token printed by `claude setup-token` on their computer.
    Only this user's jobs use it (a subscription is personal: never shared with other users)."""
    t = _str(await body(request), "token", 500) or None
    if t and not OAUTH.match(t): raise HTTPException(400, "token must be the sk-ant-oat… value printed by `claude setup-token`")
    db.ex("UPDATE users SET oauth_token=? WHERE id=?", t, u["id"]); return {"ok": True}


@app.put("/api/me/password")
async def my_password(request: Request, u=Depends(user)):
    b = await body(request); row = db.one("SELECT pw, sv FROM users WHERE id=?", u["id"])
    if not db.check_pw(_str(b, "old", 1000), row["pw"]): raise HTTPException(400, "current password is wrong")
    new = _str(b, "new", 1000)
    if len(new) < 8: raise HTTPException(400, "password must have at least 8 characters")
    db.ex("UPDATE users SET pw=?, sv=sv+1 WHERE id=?", db.hash_pw(new), u["id"])
    r = JSONResponse({"ok": True}); _cookie(r, request, {"id": u["id"], "sv": row["sv"] + 1}); return r


# ---------------- admin ----------------
SETTING_KEYS = ["anthropic_api_key", "openalex_api_key", "s2_api_key", "contact_email", "default_model", "max_parallel_jobs",
                "max_budget_usd", "crawl_every_hours", "auto_approve_confidence", "job_timeout_hours", "default_gate_timeout_hours"]
NUMERIC = {"max_parallel_jobs": (int, 1, 16), "max_budget_usd": (float, 0.1, 1000), "crawl_every_hours": (float, 0, 8760),
           "auto_approve_confidence": (float, 0, 1), "job_timeout_hours": (float, 0.1, 240), "default_gate_timeout_hours": (float, 0, 1440)}
DEFAULTS = {"max_parallel_jobs": 2, "max_budget_usd": 30.0, "crawl_every_hours": 168.0, "job_timeout_hours": 24.0, "default_model": "claude-opus-5-5",
            "default_gate_timeout_hours": 12.0}


def num_setting(k: str, default=None):
    default = DEFAULTS.get(k) if default is None else default
    v = db.setting(k)
    try: v = NUMERIC[k][0](str(v).replace(",", ".")) if v not in (None, "") else default
    except (TypeError, ValueError): return default
    return v if math.isfinite(v) else default


@app.get("/api/admin/users")
def list_users(_=Depends(admin)): return db.q("SELECT id,email,role,created FROM users WHERE disabled=0 ORDER BY id")


@app.post("/api/admin/users")
async def add_user(request: Request, _=Depends(admin)):
    b = await body(request); email = _str(b, "email", 254).lower(); pw = _str(b, "password", 1000); role = _str(b, "role", 10, "member")
    if not EMAIL.match(email): raise HTTPException(400, "invalid email")
    if len(pw) < 8: raise HTTPException(400, "password must have at least 8 characters")
    if role not in ("admin", "member"): raise HTTPException(400, "role must be admin or member")
    if db.one("SELECT id FROM users WHERE email=?", email): raise HTTPException(400, "exists")
    return {"id": db.ex("INSERT INTO users(email,pw,role,created) VALUES (?,?,?,?)", email, db.hash_pw(pw), role, time.time())}


@app.put("/api/admin/users/{uid}/password")
async def reset_password(uid: int, request: Request, _=Depends(admin)):
    pw = _str(await body(request), "password", 1000)
    if len(pw) < 8: raise HTTPException(400, "password must have at least 8 characters")
    db.ex("UPDATE users SET pw=?, sv=sv+1 WHERE id=? AND disabled=0", db.hash_pw(pw), uid); return {"ok": True}


@app.delete("/api/admin/users/{uid}")
def del_user(uid: int, a=Depends(admin)):
    """Deactivate, never delete: the id stays taken, every session dies, queued/running work stops."""
    if uid == a["id"]: raise HTTPException(400, "cannot delete yourself")
    db.ex("UPDATE users SET disabled=1, email=email||'#deleted-'||id, pw='!', api_key=NULL, sv=sv+1 WHERE id=? AND disabled=0", uid)
    for j in db.q("SELECT * FROM jobs WHERE owner=? AND status IN ('queued','running')", uid): _stop_job(j)
    db.ex("DELETE FROM hosts WHERE owner=?", uid); return {"ok": True}


@app.get("/api/admin/settings")
def get_settings(_=Depends(admin)):
    out = {k: ("••••" + str(v)[-4:] if "key" in k and v else v) for k in SETTING_KEYS if (v := db.setting(k)) is not None}
    return {**out, "_defaults": DEFAULTS}


@app.put("/api/admin/settings")
async def put_settings(request: Request, _=Depends(admin)):
    b = await body(request); clean = {}
    for k, v in b.items():
        if k not in SETTING_KEYS or (isinstance(v, str) and v.startswith("••••")): continue
        if v in (None, ""): clean[k] = None; continue
        if k in NUMERIC:
            t, lo, hi = NUMERIC[k]
            try: v = t(float(str(v).replace(",", ".")))
            except ValueError: raise HTTPException(400, f"{k}: number expected")
            if not (lo <= v <= hi): raise HTTPException(400, f"{k}: must be between {lo} and {hi}")
        elif not isinstance(v, str) or len(v) > 300: raise HTTPException(400, f"{k}: text expected")
        clean[k] = v
    for k, v in clean.items(): db.set_setting(k, v)
    return {"ok": True}


@app.get("/api/admin/jobs")
def all_jobs(_=Depends(admin)): return db.q("SELECT j.*, u.email FROM jobs j LEFT JOIN users u ON u.id=j.owner ORDER BY j.id DESC LIMIT 200")


# ---------------- hosts ----------------
@app.get("/api/hosts")
def hosts(u=Depends(user)): return [{**h, "config": json.loads(h["config"])} for h in db.q("SELECT * FROM hosts WHERE owner=? OR owner=0", u["id"])]


@app.post("/api/hosts")
async def add_host(request: Request, u=Depends(user)):
    b = await body(request)
    if not re.match(r"^[a-z0-9_-]{1,40}$", _str(b, "name", 41)): raise HTTPException(400, "name: lowercase letters, digits, - _")
    try: cfg = remote.check_host({k: b.get(k) for k in ("type", "ssh", "port", "workdir", "setup", "gpus", "sbatch") if b.get(k) not in (None, "")})
    except (ValueError, TypeError) as e: raise HTTPException(400, str(e))
    owner = 0 if (b.get("shared") and u["role"] == "admin") else u["id"]
    conf = {k: v for k, v in cfg.items() if k not in ("name", "type")}
    return {"id": db.ex("INSERT INTO hosts(owner,name,type,config,created) VALUES (?,?,?,?,?)", owner, b["name"], cfg["type"], json.dumps(conf), time.time())}


@app.delete("/api/hosts/{hid}")
def del_host(hid: int, u=Depends(user)): db.ex("DELETE FROM hosts WHERE id=? AND (owner=? OR ?='admin')", hid, u["id"], u["role"]); return {"ok": True}


def _ensure_key(owner: int) -> Path:
    td = sandbox.tenant_dir(owner); k = td / "ssh/id_ed25519"
    if not (td / "ssh/id_ed25519.pub").exists():
        r = sandbox.run(owner, ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", f"bonrs-user-{owner}", "-f", str(k)], td, capture_output=True, text=True, timeout=60)
        if r.returncode != 0: raise HTTPException(500, f"cannot create SSH key: {r.stderr.strip()[:200]}")
    return k


@app.get("/api/sshkey")
def sshkey(u=Depends(user)):
    """Each user has an own key: authorise it on your hosts (shared hosts need each user's key)."""
    k = _ensure_key(u["id"])
    return {"public_key": (safeio.read_text(k.parent, "id_ed25519.pub", 4096) or "").strip()}


def _probe(u: dict, cfg: dict) -> dict:
    """Connect as the user's own sandboxed uid with the user's own key; report what the machine has."""
    td = sandbox.tenant_dir(u["id"])
    if cfg["type"] == "local": argv = ["bash", "-c", remote.PROBE]
    else:
        key = _ensure_key(u["id"])
        argv = ["ssh", *remote.ssh_opts(cfg, key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "ConnectionAttempts=1",
                "--", cfg["ssh"], f"mkdir -p {cfg['workdir']} && {remote.PROBE}"]
    try: r = sandbox.run(u["id"], argv, td / "home", capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired: return {"ok": False, "output": "timeout", "info": {}}
    return {"ok": "BONRS_OK" in r.stdout, "output": (r.stdout + r.stderr)[-3000:], "info": remote.probe_info(r.stdout)}


@app.post("/api/hosts/probe")
async def probe_host(request: Request, u=Depends(user)):
    """Try a machine before saving it (the add-machine wizard), or look at the bonrs server itself (type local)."""
    b = await body(request)
    try: cfg = remote.check_host({k: b.get(k) for k in ("type", "ssh", "port", "workdir") if b.get(k) not in (None, "")})
    except (ValueError, TypeError) as e: raise HTTPException(400, str(e))
    return _probe(u, cfg)


@app.post("/api/hosts/{hid}/test")
def test_host(hid: int, u=Depends(user)):
    h = db.one("SELECT * FROM hosts WHERE id=? AND (owner=? OR owner=0)", hid, u["id"])
    if not h: raise HTTPException(404)
    try: cfg = remote.check_host({"name": h["name"], "type": h["type"], **json.loads(h["config"])})
    except (ValueError, TypeError) as e: raise HTTPException(400, str(e))
    return _probe(u, cfg)


# ---------------- budget suggestion from past runs ----------------
_BH: dict = {"t": 0.0, "data": None}


def _past_costs():
    """(stage costs by model, total cost of finished runs by model), from every run's events. Cached 5 minutes."""
    if _BH["data"] is not None and time.time() - _BH["t"] < 300: return _BH["data"]
    by_model, totals = {}, {}
    for rd in RUNS.iterdir():
        if not SLUG.match(rd.name) or rd.is_symlink(): continue
        try:
            model, st = str(_yaml(rd).get("model") or ""), _json(rd, "state.json")
            for line in (safeio.read_text(rd, "events.jsonl", 4_000_000, tail=True) or "").splitlines():
                try: e = json.loads(line)
                except json.JSONDecodeError: continue
                if isinstance(e, dict) and e.get("type") == "stage_end" and not e.get("error") and _num(e.get("cost")) > 0:
                    by_model.setdefault(model, []).append((str(e.get("actor", "")).removeprefix("agent:"), _num(e.get("cost"))))
            if isinstance(st, dict) and len(st.get("done") or []) == len(pipeline.ORDER): totals.setdefault(model, []).append(_num(st.get("cost")))
        except Exception: continue
    _BH.update(t=time.time(), data=(by_model, totals)); return _BH["data"]


@app.get("/api/guide")
def guide(lang: str = "vi"):
    """User guide (docs/GUIDE.vi.md or docs/GUIDE.en.md); public so the login page can link to it."""
    f = ROOT / "docs" / f"GUIDE.{'en' if lang == 'en' else 'vi'}.md"
    return PlainTextResponse(f.read_text() if f.exists() else "# Guide\n\nMissing docs file.", media_type="text/markdown")


@app.get("/api/defaults")
def defaults(u=Depends(user)):
    """What a new run starts with (admin-set or built-in): any user may read these."""
    return {"model": db.setting("default_model") or DEFAULTS["default_model"], "max_budget_usd": num_setting("max_budget_usd"),
            "gate_timeout_hours": num_setting("default_gate_timeout_hours")}


@app.get("/api/budget-hint")
def budget_hint(model: str = "", u=Depends(user)):
    """Per-step budget that past steps fit in with room to spare: max(1.5 × 90th percentile, 1.1 × highest), rounded up to 5 USD."""
    by_model, totals = _past_costs()
    pts, basis = by_model.get(model) or [], "model"
    if len(pts) < 5: pts, basis = [p for v in by_model.values() for p in v], "all"
    if not pts: return {"recommended": DEFAULTS["max_budget_usd"], "n": 0, "basis": "default", "est_run_total": None}
    cs = sorted(c for _, c in pts); pick = lambda f: cs[min(len(cs) - 1, int(f * (len(cs) - 1) + 0.5))]
    rec = int(min(200, max(10, math.ceil(max(pick(0.9) * 1.5, cs[-1] * 1.1) / 5) * 5)))
    tot = totals.get(model, []) if basis == "model" else [t for v in totals.values() for t in v]
    per = {}
    for s_, c in pts: per.setdefault(s_, []).append(c)
    est = sum(tot) / len(tot) if tot else sum(sum(v) / len(v) for v in per.values())
    return {"recommended": rec, "n": len(cs), "basis": basis, "mean": round(sum(cs) / len(cs), 2), "max": round(cs[-1], 2), "est_run_total": round(est, 0)}


_ASSIST: dict[str, dict] = {}


def _assist_run(aid: str, owner: int, inp: dict, model: str):
    a = _ASSIST[aid]; j = {"owner": owner}
    try:
        w = sandbox.tenant_dir(owner) / "work" / f"assist-{aid}"; w.mkdir(parents=True, exist_ok=True)
        prompt = (ROOT / "prompts/idea_assist.md").read_text().replace("{INPUT}", json.dumps(inp, ensure_ascii=False))
        argv = [os.environ.get("BONRS_CLAUDE_BIN", "claude"), "-p", prompt, "--output-format", "json", "--no-session-persistence", "--model", model,
                "--max-budget-usd", "2", "--disallowedTools", "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Agent,NotebookEdit"]
        r = sandbox.run(owner, argv, w, env=_job_env(j), capture_output=True, text=True, timeout=300)
        res = None
        for line in reversed(r.stdout.strip().splitlines()):
            try: ev = json.loads(line)
            except json.JSONDecodeError: continue
            if isinstance(ev, dict) and "result" in ev: res = ev; break
        if not res or res.get("is_error"): raise ValueError((res or {}).get("result") or r.stderr[-300:] or "no answer")
        txt = str(res["result"]); o = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
        clean = lambda v, n: str(v or "")[:n]
        a["result"] = {"title": clean(o.get("title"), 200), "domain": o.get("domain") if o.get("domain") in ("ml", "biomed", "socsci", "other") else "other",
                       "final": clean(o.get("final"), 4500), "journal_fit": clean(o.get("journal_fit"), 400),
                       "debate": [{"role": clean(d.get("role"), 40), "say": clean(d.get("say"), 1200)} for d in (o.get("debate") or []) if isinstance(d, dict)][:6],
                       "changes": [clean(x, 300) for x in (o.get("changes") or [])][:8], "questions": [clean(x, 300) for x in (o.get("questions") or [])][:4],
                       "cost": _num(res.get("total_cost_usd"))}
        a["status"] = "done"
    except Exception as e:
        a["status"], a["error"] = "failed", str(e)[:300]
    finally:
        _LLM_TOKENS.pop(j.get("_token"), None)
        shutil.rmtree(sandbox.tenant_dir(owner) / "work" / f"assist-{aid}", ignore_errors=True)


@app.post("/api/assist/idea")
async def assist_idea(request: Request, u=Depends(user)):
    """AI drafts the idea, debates it in 4 roles and returns a final brief. Runs as the user, on the user's own Claude connection."""
    b = await body(request)
    for k, v in list(_ASSIST.items()):
        if time.time() - v["t"] > 3600: _ASSIST.pop(k, None)
    if any(v["owner"] == u["id"] and v["status"] == "running" for v in _ASSIST.values()): raise HTTPException(429, "AI is still working on your previous request")
    if sum(v["owner"] == u["id"] for v in _ASSIST.values()) >= 30: raise HTTPException(429, "too many requests this hour")
    inp = {"idea": _str(b, "idea", 5000), "journal": _str(b, "journal", 300), "domain": _str(b, "domain", 20), "base_papers": _str(b, "base_papers", 3000),
           "previous": _str(b, "previous", 5000), "feedback": _str(b, "feedback", 3000)}
    if len(inp["idea"]) < 5 and not inp["previous"]: raise HTTPException(400, "write a few words about the idea first")
    model = _str(b, "model", 80) or db.setting("default_model") or DEFAULTS["default_model"]
    if not re.fullmatch(r"[A-Za-z0-9._\-\[\]]{1,80}", model): raise HTTPException(400, "bad model name")
    aid = secrets.token_hex(8); _ASSIST[aid] = {"owner": u["id"], "status": "running", "t": time.time()}
    threading.Thread(target=_assist_run, args=(aid, u["id"], inp, model), daemon=True).start()
    return {"id": aid}


@app.get("/api/assist/{aid}")
def assist_get(aid: str, u=Depends(user)):
    a = _ASSIST.get(aid)
    if not a or a["owner"] != u["id"]: raise HTTPException(404)
    return {k: a.get(k) for k in ("status", "result", "error")}


# ---------------- runs ----------------
def _epoch(t):
    try: return datetime.fromisoformat(str(t)).timestamp()
    except ValueError: return None


def _num(v) -> float:
    try: f = float(v); return f if math.isfinite(f) else 0.0
    except (TypeError, ValueError): return 0.0


def _yaml(rd: Path) -> dict:
    try: c = yaml.safe_load(safeio.read_text(rd, "bonrs.yaml", 1_000_000) or "")
    except yaml.YAMLError: return {}
    return c if isinstance(c, dict) else {}


def _json(rd: Path, rel: str, limit=2_000_000):
    try: return json.loads(safeio.read_text(rd, rel, limit) or "null")
    except ValueError: return None


def _event(rd: Path, typ: str, actor="system", **payload):
    line = json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "type": typ, "actor": actor, **payload}, ensure_ascii=False) + "\n"
    try: safeio.write_text(rd, "events.jsonl", line, append=True)
    except OSError: pass


def _gate_open(rd: Path):
    w = _json(rd, "hitl/waiting.json", 100_000)
    return w if isinstance(w, dict) and not safeio.exists(rd, "hitl/response.json") else None


def _gate_due(rd: Path) -> bool:
    w = _gate_open(rd)
    if not w or w.get("gate") in pipeline.ALWAYS_WAIT: return False
    h = _num(_yaml(rd).get("gate_timeout_hours", 12))
    since = _epoch(w.get("since"))
    return bool(h) and since is not None and time.time() > since + h * 3600


def _p(v) -> float: return round(min(1.0, max(0.0, _num(v))), 3)


def _hypotheses(rd: Path):
    """hypotheses.json is agent-written: keep known fields, cap sizes, coerce numbers."""
    h = _json(rd, "hypotheses.json", 300_000)
    if not isinstance(h, dict) or not isinstance(h.get("hypotheses"), list): return None
    t = lambda v, n=600: str(v or "")[:n]
    out = []
    for x in h["hypotheses"][:8]:
        if not isinstance(x, dict): continue
        ps, pa = _p(x.get("p_success")), _p(x.get("p_accept_if_success"))
        out.append({"id": t(x.get("id"), 10), "title": t(x.get("title"), 200), "statement": t(x.get("statement")), "improvement": t(x.get("improvement")),
                    "grounded_in": [t(g, 20) for g in (x.get("grounded_in") or [])][:8] if isinstance(x.get("grounded_in"), list) else [],
                    "novelty": t(x.get("novelty")), "feasibility": t(x.get("feasibility")), "p_success": ps, "p_accept_if_success": pa, "overall": round(ps * pa, 3),
                    "effort_weeks": _num(x.get("effort_weeks")), "risks": [t(r, 200) for r in (x.get("risks") or [])][:6] if isinstance(x.get("risks"), list) else [],
                    "minimal_experiment": t(x.get("minimal_experiment")), "falsified_if": t(x.get("falsified_if"))})
    base = [{"id": t(b.get("id"), 10), "title": t(b.get("title"), 300), "source": t(b.get("source"), 300)} for b in (h.get("base_papers") or [])[:20] if isinstance(b, dict)] \
        if isinstance(h.get("base_papers"), list) else []
    verdict = h.get("verdict") if h.get("verdict") in ("go", "pivot", "no_go") else None
    return {"recommended": t(h.get("recommended"), 10), "verdict": verdict, "reason": t(h.get("reason"), 1500), "base_papers": base, "hypotheses": out}


def _summary(slug):
    rd = RUNS / slug
    cfg, st = _yaml(rd), _json(rd, "state.json")
    if not cfg or not isinstance(st, dict): return None
    job = db.one("SELECT id,status,args FROM jobs WHERE slug=? AND kind='run' ORDER BY id DESC LIMIT 1", slug)
    gate = _gate_open(rd)
    info, current = {}, None  # per-stage cost/seconds/attempts aggregated from events; stage still open = current
    for line in (safeio.read_text(rd, "events.jsonl", 4_000_000, tail=True) or "").splitlines():
        try: e = json.loads(line)
        except json.JSONDecodeError: continue
        if not isinstance(e, dict): continue
        s = str(e.get("actor") or "").removeprefix("agent:")
        if e.get("type") == "stage_start": current = s if s in pipeline.STAGES else current
        elif e.get("type") == "stage_end" and s in pipeline.STAGES:
            i = info.setdefault(s, {"cost": 0, "seconds": 0, "runs": 0, "error": False})
            i["cost"] += _num(e.get("cost")); i["seconds"] += _num(e.get("seconds")); i["runs"] += 1; i["error"] = bool(e.get("error"))
            if current == s: current = None
    if not (job and job["status"] == "running"): current = None
    if gate: gate = {"gate": str(gate.get("gate", ""))[:40], "stage": str(gate.get("stage", ""))[:40], "since": _epoch(gate.get("since"))}
    done = [s for s in st.get("done", []) if s in pipeline.STAGES] if isinstance(st.get("done"), list) else []
    return {"slug": slug, "idea": str(cfg.get("idea") or ""), "journal": str(cfg.get("target_journal") or ""), "domain": str(cfg.get("domain") or ""),
            "done": done, "cost": _num(st.get("cost")),
            "reviews": [{"round": int(_num(v.get("round"))), "score": _num(v.get("score")), "decision": str(v.get("decision") or "")[:20],
                         "open_major": int(_num(v.get("open_major")))} for v in (st.get("reviews") or []) if isinstance(v, dict)][:20],
            "job": job, "gate": gate, "stages": pipeline.ORDER, "config": cfg, "stage_info": info, "current": current, "gates_map": pipeline.GATES,
            "always_wait": sorted(pipeline.ALWAYS_WAIT)}


@app.get("/api/runs")
def runs(u=Depends(user)):
    rows = db.q("SELECT r.*, u.email FROM runs r LEFT JOIN users u ON u.id=r.owner " + ("" if u["role"] == "admin" else "WHERE owner=? ") + "ORDER BY created DESC",
                *(() if u["role"] == "admin" else (u["id"],)))
    return [{**r, **sm} for r in rows if (sm := _summary(r["slug"]))]  # skip runs whose folder is gone


@app.post("/api/runs")
async def new_run(request: Request, u=Depends(user)):
    b = await body(request)
    idea, journal = _str(b, "idea", 5000), _str(b, "journal", 300)
    if not idea or not journal: raise HTTPException(400, "idea and journal required")
    model = _str(b, "model", 80) or db.setting("default_model") or DEFAULTS["default_model"]
    if model and not re.fullmatch(r"[A-Za-z0-9._\-\[\]]{1,80}", str(model)): raise HTTPException(400, "bad model name")
    try:
        budget = float(b.get("budget") or num_setting("max_budget_usd"))
        timeout = None if b.get("gate_timeout_hours") in (None, "") else float(b["gate_timeout_hours"])
    except (TypeError, ValueError): raise HTTPException(400, "budget and gate timeout must be numbers")
    if not (0 < budget <= 1000) or (timeout is not None and not (0 <= timeout <= 24 * 60)): raise HTTPException(400, "budget or gate timeout out of range")
    want = b.get("hosts") if isinstance(b.get("hosts"), list) else []
    try: sel = ([remote.check_host({"name": "local", "type": "local"})] if "local" in want else []) + \
               [remote.check_host({"name": h["name"], "type": h["type"], **h["config"]}) for h in hosts(u) if h["id"] in want]
    except ValueError as e: raise HTTPException(400, f"host: {e}")
    ascii_ = unicodedata.normalize("NFKD", (_str(b, "slug", 80) or idea).replace("đ", "d").replace("Đ", "D")).encode("ascii", "ignore").decode()
    base = (re.sub(r"[^a-z0-9]+", "-", ascii_.lower())[:40].strip("-") or "run") + "-" + datetime.now().strftime("%m%d%H%M")
    slug = next((c for c in [base] + [f"{base}-{i}" for i in range(2, 100)] if not (RUNS / c).exists()), None)
    if not slug: raise HTTPException(409, "too many runs with this name right now")
    refs = [x.strip()[:500] for x in _str(b, "base_papers", 20000).splitlines() if x.strip()][:30]  # DOIs, links or titles of base papers
    rd = pipeline.new_run(idea, journal, slug, domain=_str(b, "domain", 40) or None, article_type=None,
                          fmt=_str(b, "format", 20) or None, model=model, budget=budget, user_id=str(u["id"]), base_papers=refs)
    cfg = _yaml(rd)
    if isinstance(b.get("gates"), list): cfg["gates"] = {g: g in b["gates"] for g in pipeline.GATES.values()}
    cfg["gate_timeout_hours"] = timeout if timeout is not None else num_setting("default_gate_timeout_hours")  # 0 = wait forever
    if b.get("backup_journals"): cfg["backup_journals"] = [x.strip()[:300] for x in _str(b, "backup_journals", 1000).split(",") if x.strip()][:5]
    if sel: cfg["remote"]["hosts"] = sel
    safeio.write_text(rd, "bonrs.yaml", yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    db.ex("INSERT INTO runs VALUES (?,?,?,?,?)", slug, u["id"], idea, journal, time.time())
    _event(rd, "run_created", actor=f"user:{u['email']}")
    sandbox.hand_over(u["id"], rd)
    if b.get("start", True): enqueue("run", slug, {}, u["id"])
    return {"slug": slug}


@app.get("/api/runs/{slug}")
def get_run(slug: str, u=Depends(user)):
    rd = run_of(slug, u); s = _summary(slug)
    if s is None: raise HTTPException(404, "run folder missing")
    s["events"] = []
    for l in (safeio.read_text(rd, "events.jsonl", 1_000_000, tail=True) or "").splitlines()[-1000:]:
        try: e = json.loads(l)
        except json.JSONDecodeError: continue
        if isinstance(e, dict): e["ts"] = _epoch(e.get("ts")); s["events"].append(e)
    files = safeio.listing(rd, 5000)
    s["requests"] = [p for p, _, _ in files if "REQUEST" in Path(p).name and p.endswith(".md")]
    s["base_files"] = [p for p, _, _ in files if p.startswith("lit/base/") and not p.endswith(".txt")][:50]
    s["hypotheses"] = _hypotheses(rd)
    s["jobs"] = db.q("SELECT id,kind,status,created,started,finished,exit,note FROM jobs WHERE slug=? ORDER BY id DESC LIMIT 20", slug)
    return s


def _clean_cfg(c, owner: int) -> dict:
    """Validate a member-edited bonrs.yaml. Ownership and host access are server facts, not config."""
    if not isinstance(c, dict): raise HTTPException(400, "bonrs.yaml must be a mapping")
    c = dict(c); c["user_id"] = str(owner)
    bp = c.get("base_papers") or []
    c["base_papers"] = [str(x)[:500] for x in bp][:30] if isinstance(bp, list) else []
    if c.get("model") is not None and not re.fullmatch(r"[A-Za-z0-9._\-\[\]]{1,80}", str(c["model"])): raise HTTPException(400, "bad model name")
    for k, lo, hi in (("max_budget_usd", 0, 1000), ("gate_timeout_hours", 0, 24 * 60)):
        if c.get(k) is not None:
            v = _num(c[k])
            if not (lo <= v <= hi): raise HTTPException(400, f"{k} must be between {lo} and {hi}")
            c[k] = v
    rv = c.get("review") or {}
    if not isinstance(rv, dict): raise HTTPException(400, "review must be a mapping")
    c["review"] = {"max_rounds": int(min(6, max(1, _num(rv.get("max_rounds", 3))))), "accept_score": min(10.0, max(0.0, _num(rv.get("accept_score", 7.5))))}
    g = c.get("gates") or {}
    if not isinstance(g, dict): raise HTTPException(400, "gates must be a mapping")
    c["gates"] = {k: bool(g.get(k)) for k in pipeline.GATES.values()}
    hs = (c.get("remote") or {}).get("hosts") if isinstance(c.get("remote"), dict) else None
    try: c["remote"] = {"hosts": [remote.check_host(h) for h in (hs or [{"name": "local", "type": "local"}]) if isinstance(h, dict)][:10]}
    except (ValueError, TypeError) as e: raise HTTPException(400, f"remote.hosts: {e}")
    return c


@app.put("/api/runs/{slug}/config")
async def put_config(slug: str, request: Request, u=Depends(user)):
    rd = run_of(slug, u); text = (await request.body()).decode("utf8", "replace")
    if len(text) > 200_000: raise HTTPException(413, "too large")
    try: c = yaml.safe_load(text)
    except yaml.YAMLError as e: raise HTTPException(400, f"invalid YAML: {e}")
    safeio.write_text(rd, "bonrs.yaml", yaml.safe_dump(_clean_cfg(c, owner_of(slug)), allow_unicode=True, sort_keys=False))
    _user_commit(rd, slug, u, "edit bonrs.yaml"); _event(rd, "config_change", actor=f"user:{u['email']}"); return {"ok": True}


@app.post("/api/runs/{slug}/start")
async def start(slug: str, request: Request, u=Depends(user)):
    run_of(slug, u); b = await body(request)
    a = {k: b[k] for k in ("from", "to") if b.get(k)}
    if any(v not in pipeline.ORDER for v in a.values()): raise HTTPException(400, "unknown stage")
    if b.get("force"): a["force"] = True
    if db.one("SELECT id FROM jobs WHERE slug=? AND status='queued'", slug): raise HTTPException(409, "already queued")  # a running job is fine: worker runs this one after it
    return {"job": enqueue("run", slug, a, owner_of(slug))}  # credentials of the run's owner, whoever clicks


def _stop_job(j: dict):
    if j.get("pid") and j["status"] == "running":
        try:
            if sandbox.ON: os.kill(j["pid"], signal.SIGTERM)  # sudo relays it to the job's process group
            else: os.killpg(j["pid"], signal.SIGTERM)
        except (ProcessLookupError, PermissionError): pass
    db.ex("UPDATE jobs SET status='stopped', finished=? WHERE id=? AND status IN ('queued','running')", time.time(), j["id"])


@app.post("/api/runs/{slug}/stop")
def stop(slug: str, u=Depends(user)):
    run_of(slug, u)
    for j in db.q("SELECT * FROM jobs WHERE slug=? AND status IN ('queued','running')", slug): _stop_job(j)
    return {"ok": True}


@app.post("/api/runs/{slug}/gate")
async def gate(slug: str, request: Request, u=Depends(user)):
    rd = run_of(slug, u); b = await body(request)
    w = _gate_open(rd)
    if not w:
        if safeio.exists(rd, "hitl/response.json"): raise HTTPException(409, "gate already answered")
        raise HTTPException(400, "no open gate")
    act, note = _str(b, "action", 20, "approve"), _str(b, "note", 5000) or None
    if act not in ("approve", "guide", "reject", "redo"): raise HTTPException(400, "action must be approve, guide, reject or redo")
    if act == "reject":  # close the gate and stay paused; "Tiếp tục" later resumes from the next stage
        safeio.unlink(rd, "hitl/waiting.json")
        _event(rd, "gate_answered", actor=f"user:{u['email']}", gate=str(w.get("gate")), action="reject", note=note); return {"ok": True}
    if act == "redo" and not note: raise HTTPException(400, "redo needs a note")
    hid = _str(b, "hypothesis", 10)
    if hid and act in ("approve", "guide"):
        hs = _hypotheses(rd) or {"hypotheses": []}; h = next((x for x in hs["hypotheses"] if x["id"] == hid), None)
        if not h: raise HTTPException(400, "unknown hypothesis")
        note = f"The author chose hypothesis {h['id']} ({h['title']}). Pursue only this hypothesis from now on; drop the others." + (f" {note}" if note else "")
        act = "guide"
    resp = json.dumps({"action": "guide" if act == "redo" else act, "note": note, "user": u["email"], "ts": datetime.now().isoformat()})
    try: safeio.write_text(rd, "hitl/response.json", resp, exclusive=True)
    except FileExistsError: raise HTTPException(409, "gate already answered")  # two tabs answering at once
    stage = w.get("stage")  # redo = rerun the gated stage with the note as guidance (the review loop's gate just continues with the note)
    args = {"from": stage, "force": True} if act == "redo" and stage in pipeline.STAGES and stage != "07_revise" else {}
    if not db.one("SELECT id FROM jobs WHERE slug=? AND status='queued'", slug): enqueue("run", slug, args, owner_of(slug))
    return {"ok": True}


@app.get("/api/runs/{slug}/tree")
def tree(slug: str, u=Depends(user)):
    rd = run_of(slug, u)
    return sorted(p for p, size, _ in safeio.listing(rd, skip=(".git", ".bonrs")) if "pdf" not in Path(p).parts[:2] and size < 30_000_000)


INLINE = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}


@app.get("/api/runs/{slug}/file")
def get_file(slug: str, path: str, raw: int = 0, u=Depends(user)):
    rd = run_of(slug, u); rel = rel_ok(path); suf = Path(rel).suffix.lower()
    try:
        if raw or suf in INLINE or suf in (".docx", ".zip"):
            f = safeio.open_read(rd, rel); name = Path(rel).name
            if suf in INLINE:  # images and PDFs are shown inline; everything else downloads (an .html/.svg never renders on our origin)
                hdr = {"Content-Disposition": f'inline; filename="{name}"'}
                if suf != ".pdf": hdr["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
                media = INLINE[suf]
            else: hdr, media = {"Content-Disposition": f'attachment; filename="{name}"', "Content-Security-Policy": "default-src 'none'; sandbox"}, "application/octet-stream"
            return StreamingResponse(iter(lambda: f.read(65536), b""), media_type=media, headers=hdr, background=BackgroundTask(f.close))
        return PlainTextResponse(safeio.read_bytes(rd, rel, 2_000_000).decode("utf8", "ignore"))
    except FileNotFoundError: raise HTTPException(404)
    except (OSError, ValueError): raise HTTPException(404, "not a regular file")


MANAGED = re.compile(r"^(state\.json|events\.jsonl|bonrs\.yaml|hitl/|logs/|\.git|\.bonrs/|\.claude|\.mcp\.json|CLAUDE\.md|proposals/)")


@app.put("/api/runs/{slug}/file")
async def put_file(slug: str, path: str, request: Request, u=Depends(user)):
    rd = run_of(slug, u); rel = "/".join(x for x in rel_ok(path).split("/") if x not in ("", "."))
    if MANAGED.match(rel): raise HTTPException(403, "this file is managed by bonrs")
    new = (await request.body())
    if len(new) > 5_000_000: raise HTTPException(413, "too large")
    try:
        old = len(safeio.read_bytes(rd, rel)) if safeio.exists(rd, rel) else 0
        safeio.write_bytes(rd, rel, new)
    except (OSError, ValueError): raise HTTPException(400, "cannot write this path")
    _user_commit(rd, slug, u, f"user edit {rel}")
    db.ex("INSERT INTO comments(slug,user,ts,path,anchor,quote,body,kind,status) VALUES (?,?,?,?,?,?,?,?,?)", slug, u["id"], time.time(), rel, "",
          "", f"Sửa trực tiếp tệp ({old}→{len(new)} byte). Agent coi đây là văn phong/ý muốn của tác giả.", "edit", "applied")
    _event(rd, "user_edit", actor=f"user:{u['email']}", path=rel); return {"ok": True}


def _save_upload(f: UploadFile, base: Path, rel: str):
    """Stream an upload to base/rel with the size cap enforced while reading."""
    n = 0
    with safeio.open_write(base, rel) as out:
        while chunk := f.file.read(1 << 20):
            n += len(chunk)
            if n > MAX_UPLOAD: raise HTTPException(413, f"too large: {Path(rel).name}")
            out.write(chunk)


def _upload_name(f: UploadFile) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", f.filename or "file").lstrip(".")[:120] or "file"
    if Path(name).suffix.lower() not in ALLOWED_UPLOAD: raise HTTPException(400, f"type not allowed: {name}")
    return name


@app.post("/api/runs/{slug}/upload")
def upload(slug: str, where: str = Form("lit/uploads"), files: list[UploadFile] = File(...), u=Depends(user)):
    rd = run_of(slug, u)
    if where not in ("lit/uploads", "lit/base", "journal/accepted", "exp/data", "knowledge"): raise HTTPException(400, "bad target")
    if len(files) > MAX_FILES: raise HTTPException(400, f"at most {MAX_FILES} files per upload")
    saved = []
    for f in files:
        rel = f"{where}/{_upload_name(f)}"
        try: _save_upload(f, rd, rel)
        except (OSError, ValueError): raise HTTPException(400, f"cannot write {rel}")
        saved.append(rel)
    owner = owner_of(slug); sandbox.hand_over(owner, rd)
    for rel in saved:  # untrusted PDFs are parsed as the owner's sandboxed uid, never by the server itself
        if rel.endswith(".pdf"):
            try: sandbox.run(owner, ["pdftotext", "-layout", rel, rel[:-4] + ".txt"], rd, capture_output=True, timeout=180)
            except subprocess.TimeoutExpired: pass
    _event(rd, "upload", actor=f"user:{u['email']}", files=saved); _user_commit(rd, slug, u, f"upload {len(saved)} file(s)")
    return {"saved": saved}


@app.get("/api/runs/{slug}/log")
def log(slug: str, stage: str | None = None, u=Depends(user)):
    rd = run_of(slug, u); out = []
    if stage and stage not in pipeline.STAGES: raise HTTPException(400, "unknown stage")
    logs = sorted((x for x in safeio.listing(rd / "logs", 500) if x[0].endswith(".jsonl") and "/" not in x[0]), key=lambda x: x[2]) if safeio.exists(rd, "logs") else []
    files = [f"{stage}.jsonl"] if stage else [x[0] for x in logs[-1:]]
    for f in files:
        for line in (safeio.read_text(rd, f"logs/{f}", 6_000_000, tail=True) or "").splitlines()[-3000:]:
            try: ev = json.loads(line)
            except json.JSONDecodeError: continue
            if not isinstance(ev, dict): continue
            if ev.get("type") == "bonrs_attempt": out.append({"t": "attempt", "v": str(ev.get("ts"))[:30]}); continue
            if ev.get("type") == "assistant":
                msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
                for c in msg.get("content") if isinstance(msg.get("content"), list) else []:
                    if not isinstance(c, dict): continue
                    if c.get("type") == "text": out.append({"t": "say", "v": str(c.get("text"))[:2000]})
                    elif c.get("type") == "tool_use": out.append({"t": "tool", "v": f"{str(c.get('name'))[:40]}: {json.dumps(c.get('input'))[:300]}"})
            elif ev.get("type") == "result": out.append({"t": "result", "v": f"cost ${_num(ev.get('total_cost_usd')):.2f} — {str(ev.get('result'))[:1500]}"})
    return {"events": out[-1500:], "pipeline": safeio.read_text(rd, "logs/pipeline.log", 5000, tail=True) or ""}


def _user_commit(rd: Path, slug: str, u: dict, msg: str):
    o = owner_of(slug); email = re.sub(r"[^A-Za-z0-9@._+-]", "", u["email"])[:100]
    sandbox.git(o, rd, "add", "-A", chown=True)
    sandbox.git(o, rd, "-c", f"user.name={email}", "-c", f"user.email={email}", "commit", "-qm", msg[:200])


@app.get("/api/runs/{slug}/history")
def history(slug: str, u=Depends(user)):
    rd = run_of(slug, u)
    out = sandbox.git(owner_of(slug), rd, "log", "--format=%h\x1f%an\x1f%ad\x1f%s", "--date=iso", "-200")
    return [dict(zip(("hash", "author", "date", "msg"), l.split("\x1f"))) for l in out.splitlines()]


@app.get("/api/runs/{slug}/diff")
def diff(slug: str, a: str, b: str = "HEAD", path: str = "", u=Depends(user)):
    rd = run_of(slug, u)
    rev = r"^([0-9a-fA-F]{4,40}|HEAD)(~\d{1,3})?$"
    if not re.match(rev, a) or not re.match(rev, b): raise HTTPException(400, "bad rev")
    args = ["diff", "--no-ext-diff", "--no-textconv", "--stat", a, b] if not path else ["-c", "core.quotePath=false", "diff", "--no-ext-diff", "--no-textconv", a, b, "--", rel_ok(path)]
    return PlainTextResponse(sandbox.git(owner_of(slug), rd, *args)[:500_000])


@app.get("/api/runs/{slug}/changes")
def changes(slug: str, a: str, b: str = "HEAD", u=Depends(user)):
    """Files that differ between two commits, with added/removed line counts (None for binary files)."""
    rd = run_of(slug, u); o = owner_of(slug)
    rev = r"^([0-9a-fA-F]{4,40}|HEAD)(~\d{1,3})?$"
    if not re.match(rev, a) or not re.match(rev, b): raise HTTPException(400, "bad rev")
    base = ["-c", "core.quotePath=false", "diff", "--no-ext-diff", "--no-textconv", "--no-renames"]
    st = dict(reversed(l.split("\t", 1)) for l in sandbox.git(o, rd, *base, "--name-status", a, b).splitlines() if "\t" in l)
    out = []
    for l in sandbox.git(o, rd, *base, "--numstat", a, b).splitlines()[:2000]:
        p = l.split("\t", 2)
        if len(p) != 3: continue
        out.append({"path": p[2], "add": None if p[0] == "-" else int(p[0]), "del": None if p[1] == "-" else int(p[1]), "status": st.get(p[2], "M")[:1]})
    return out


@app.get("/api/runs/{slug}/export")
def export(slug: str, u=Depends(user)):
    """Zip built by the owner's uid into the owner's own folder, streamed once, then deleted."""
    rd = run_of(slug, u); o = owner_of(slug); td = sandbox.tenant_dir(o); (td / "exports").mkdir(exist_ok=True)
    name = f"{slug}-{secrets.token_hex(4)}.zip"
    sandbox.git(o, rd, "bundle", "create", "history.bundle", "--all", chown=True)
    sandbox.run(o, ["zip", "-qry", str(td / "exports" / name), ".", "-x", ".git/*", ".bonrs/*"], rd, timeout=600, capture_output=True)
    try: f = safeio.open_read(td / "exports", name)
    except OSError: raise HTTPException(500, "export failed")

    def done(): f.close(); safeio.unlink(td / "exports", name)
    return StreamingResponse(iter(lambda: f.read(65536), b""), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'}, background=BackgroundTask(done))


# ---------------- comments ----------------
KINDS, CSTATUS = ("suggest", "question", "must_fix", "style", "edit"), ("open", "applied", "rejected")


@app.get("/api/runs/{slug}/comments")
def comments(slug: str, u=Depends(user)):
    run_of(slug, u); return db.q("SELECT c.*, u.email FROM comments c LEFT JOIN users u ON u.id=c.user WHERE slug=? ORDER BY ts DESC", slug)


@app.post("/api/runs/{slug}/comments")
async def add_comment(slug: str, request: Request, u=Depends(user)):
    rd = run_of(slug, u); b = await body(request); text = _str(b, "body", 20000)
    if not text: raise HTTPException(400, "empty comment")
    kind = _str(b, "kind", 20, "suggest")
    if kind not in KINDS: kind = "suggest"
    cid = db.ex("INSERT INTO comments(slug,user,ts,path,anchor,quote,body,kind) VALUES (?,?,?,?,?,?,?,?)", slug, u["id"], time.time(),
                _str(b, "path", 300), _str(b, "anchor", 300), _str(b, "quote", 2000), text, kind)
    _event(rd, "comment", actor=f"user:{u['email']}", id=cid, path=_str(b, "path", 300)); return {"id": cid}


@app.patch("/api/runs/{slug}/comments/{cid}")
async def patch_comment(slug: str, cid: int, request: Request, u=Depends(user)):
    run_of(slug, u); b = await body(request); st = b.get("status")
    if st is not None and st not in CSTATUS: raise HTTPException(400, "bad status")
    db.ex("UPDATE comments SET status=COALESCE(?,status), reply=COALESCE(?,reply) WHERE id=? AND slug=?", st, _str(b, "reply", 5000) or None, cid, slug)
    return {"ok": True}


def export_comments(slug: str):
    """Write comments/open.md (for stage 07) and comments/all.md (for stage 09)."""
    rd = RUNS / slug; rows = db.q("SELECT c.*, u.email FROM comments c LEFT JOIN users u ON u.id=c.user WHERE slug=? ORDER BY ts", slug)
    if not rows: return
    fmt = lambda c: f"## #{c['id']} [{c['kind']}] {c['status']} — {c['email']} on `{c['path'] or 'general'}` {c['anchor'] or ''}\n" + \
                    (f"> {c['quote']}\n\n" if c["quote"] else "") + f"{c['body']}\n" + (f"\nReply: {c['reply']}\n" if c["reply"] else "")
    opened = [c for c in rows if c["status"] == "open"]
    if opened: safeio.write_text(rd, "comments/open.md", "# Open author comments (highest priority; answer each in response_letter.md)\n\n" + "\n".join(map(fmt, opened)))
    else: safeio.unlink(rd, "comments/open.md")
    safeio.write_text(rd, "comments/all.md", "# All author comments and edits\n\n" + "\n".join(map(fmt, rows)))


# ---------------- knowledge ----------------
SHARED_TIERS = ("00-general", "10-domain", "20-article-type", "30-journal", "40-experience")


def _kb_readable(u: dict, rel: str) -> bool:
    return u["role"] == "admin" or rel.split("/")[0] in SHARED_TIERS or rel.startswith(f"50-user/{u['id']}/")


def _kb_writable(u: dict, rel: str) -> bool:
    return u["role"] == "admin" or (rel.startswith(f"50-user/{u['id']}/") and rel.endswith(".md"))


@app.get("/api/kb")
def kb_index(u=Depends(user)): return [r for r in kb.index() if _kb_readable(u, r["path"])]


@app.get("/api/kb/file")
def kb_file(path: str, u=Depends(user)):
    if not _kb_readable(u, rel_ok(path)): raise HTTPException(403, "not visible to you")
    p = safe_path(KNOWLEDGE, path)
    if not p.is_file(): raise HTTPException(404)
    return PlainTextResponse(p.read_text(errors="ignore")[:2_000_000])


@app.put("/api/kb/file")
async def kb_put(path: str, request: Request, u=Depends(user)):
    if not _kb_writable(u, rel_ok(path)): raise HTTPException(403, "only admins edit shared skills; members may edit 50-user/<their id>/*.md or propose via ingest")
    data = await request.body()
    if len(data) > 300_000: raise HTTPException(413, "too large")
    p = safe_path(KNOWLEDGE, path); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(data.decode("utf8", "replace")); kb.index(); return {"ok": True}


@app.post("/api/kb/ingest")
def kb_ingest(url: str = Form(""), hint: str = Form(""), files: list[UploadFile] | None = File(None), u=Depends(user)):
    if len(files or []) > 5: raise HTTPException(400, "at most 5 files per request")
    work_root = sandbox.tenant_dir(u["id"]) / "work"
    srcs = []
    if url:
        if not url.startswith(("http://", "https://")) or len(url) > 2000: raise HTTPException(400, "url must be http(s)")
        srcs.append(url)
    jobs = []
    for s in srcs + list(files or []):
        w = f"ingest-{int(time.time())}-{secrets.token_hex(4)}"
        if isinstance(s, str): (work_root / w).mkdir(parents=True, exist_ok=True)
        else: name = _upload_name(s); _save_upload(s, work_root, f"{w}/{name}"); s = str(work_root / w / name)
        jobs.append(enqueue("ingest", None, {"src": s, "hint": hint[:500], "user": u["email"], "work": str(work_root / w)}, u["id"]))
    if not jobs: raise HTTPException(400, "give a url or a file")
    return {"jobs": jobs}


@app.get("/api/kb/drafts")
def kb_drafts(u=Depends(user)):
    return [d for d in kb.drafts() if u["role"] == "admin" or d.get("submitted_by") == u["email"]]


@app.post("/api/kb/drafts/{file}/approve")
async def kb_approve(file: str, request: Request, u=Depends(admin)):
    b = await body(request)
    try: return {"path": str(kb.approve(file, b.get("meta") if isinstance(b.get("meta"), dict) else None,
                                        b.get("body") if isinstance(b.get("body"), str) else None).relative_to(KNOWLEDGE))}
    except ValueError as e: raise HTTPException(400, f"cannot approve: {e}")


@app.post("/api/kb/drafts/{file}/reject")
async def kb_reject(file: str, request: Request, u=Depends(admin)):
    try: kb.reject(file, _str(await body(request), "reason", 500)); return {"ok": True}
    except ValueError as e: raise HTTPException(400, str(e))


def _crawl_state() -> dict:
    f = KNOWLEDGE / "sources.state.json"
    try: return json.loads(f.read_text()) if f.exists() else {}
    except (OSError, json.JSONDecodeError): return {}


def _all_sources() -> list[dict]:
    try: srcs = (yaml.safe_load((KNOWLEDGE / "sources.yaml").read_text()) or {}).get("sources", []) if (KNOWLEDGE / "sources.yaml").exists() else []
    except (OSError, yaml.YAMLError, AttributeError): srcs = []
    return [s for s in srcs if isinstance(s, dict)]


@app.get("/api/kb/sources")
def kb_sources(_=Depends(user)):
    every, last = num_setting("crawl_every_hours"), _num(db.setting("last_crawl_at"))
    return {"sources": _all_sources(), "state": _crawl_state(), "every_hours": every, "last": last or None,
            "next": (last + every * 3600) if every and last else None, "auto_approve": db.setting("auto_approve_confidence"),
            "has_key": bool(_api_key(0)), "levels": list(kb.LEVELS)}


@app.put("/api/kb/sources")
async def kb_put_sources(request: Request, _=Depends(admin)):
    b = await body(request); out = []
    for x in b.get("sources") if isinstance(b.get("sources"), list) else []:
        if not isinstance(x, dict): continue
        url, name = str(x.get("url") or "").strip()[:500], str(x.get("name") or "").strip()[:100]
        if not url.startswith(("http://", "https://")): raise HTTPException(400, f"{name or url}: link must start with http:// or https://")
        s = {"name": name or url, "url": url, "level": x.get("level") if x.get("level") in kb.LEVELS else "general"}
        if str(x.get("domain") or "").strip(): s["domain"] = str(x["domain"]).strip()[:40]
        if x.get("enabled") is False: s["enabled"] = False
        out.append(s)
    if len(out) > 200: raise HTTPException(400, "at most 200 sources")
    (KNOWLEDGE / "sources.yaml").write_text("# Sources crawled on a schedule (Kho tri thức → Nguồn tự động). New or changed pages become draft skills.\n"
                                            + yaml.safe_dump({"sources": out}, allow_unicode=True, sort_keys=False))
    return {"ok": True}


def _enqueue_crawl(only: str | None = None) -> list[int]:
    state = _crawl_state()
    return [enqueue("ingest", None, {"src": s["url"], "user": "crawler", "crawl": True, "work": str(sandbox.tenant_dir(0) / "work" / f"crawl-{secrets.token_hex(6)}"),
                                     "skip_sha": (state.get(s["url"]) or {}).get("hash") or "",
                                     "hint": f"level={s.get('level', 'general')} domain={s.get('domain', '')} source_name={s.get('name')}"[:500]}, 0, cap=False)
            for s in kb.sources() if only in (None, s["url"])]


@app.post("/api/kb/crawl")
async def kb_crawl(request: Request, u=Depends(admin)):
    only = _str(await body(request), "url", 500) or None
    if not only: db.set_setting("last_crawl_at", time.time())
    return {"jobs": _enqueue_crawl(only)}


@app.post("/api/kb/promote")
async def kb_promote(request: Request, u=Depends(user)):
    """Member proposes a run-local or personal skill for the shared base: queued for admin review."""
    b = await body(request); rel = rel_ok(_str(b, "path", 300))
    if b.get("slug"):
        rd = run_of(_str(b, "slug", 90), u); text = safeio.read_text(rd, rel, 300_000)
    else:
        if not _kb_readable(u, rel): raise HTTPException(403, "not visible to you")
        p = safe_path(KNOWLEDGE, rel); text = p.read_text(errors="ignore")[:300_000] if p.is_file() else None
    if text is None: raise HTTPException(404)
    meta, md = kb.parse_text(text, Path(rel).stem); meta.pop("confidence", None)  # promoted drafts are never auto-approved
    return {"file": kb.queue_draft(meta, md, Path(rel).stem, u["email"], u["id"], "promote")}


# ---------------- LLM proxy: jobs get a short-lived token, never the API key ----------------
_LLM_TOKENS: dict[str, int] = {}
_OAUTH_OWNERS: set[int] = set()  # owners whose jobs hold their own subscription token: the API-key proxy is closed to them


def _api_key(owner: int):
    u = db.one("SELECT api_key FROM users WHERE id=? AND disabled=0", owner) or {}
    return u.get("api_key") or db.setting("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")


@app.api_route("/api/llm/{path:path}", methods=["GET", "POST"])
async def llm_proxy(path: str, request: Request):
    tok = request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    owner = _LLM_TOKENS.get(tok) if tok else None
    if owner is None or not re.fullmatch(r"v1/[a-z0-9_/\-]{1,100}", path): raise HTTPException(401, "invalid job token")
    if owner in _OAUTH_OWNERS: raise HTTPException(403, "this user runs Claude on their own subscription")
    key = _api_key(owner)
    if not key: raise HTTPException(503, "no Anthropic API key configured (Quản trị → Khoá API)")
    hdr = {k: v for k, v in request.headers.items() if k.lower() in ("content-type", "anthropic-version", "anthropic-beta", "accept")}
    hdr["x-api-key"] = key
    data = await request.body()
    r = await run_in_threadpool(requests.request, request.method, f"{UPSTREAM}/{path}", params=dict(request.query_params), data=data,
                                headers=hdr, stream=True, timeout=(15, 900))
    keep = {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "request-id", "retry-after") or k.lower().startswith("anthropic-ratelimit")}
    return StreamingResponse(iterate_in_threadpool(r.iter_content(chunk_size=None)), status_code=r.status_code, headers=keep, background=BackgroundTask(r.close))


DATA_UP = {"openalex": ("https://api.openalex.org", "openalex_api_key", "param"), "s2": ("https://api.semanticscholar.org", "s2_api_key", "header")}


@app.api_route("/api/data/{svc}/{path:path}", methods=["GET", "POST"])
async def data_proxy(svc: str, path: str, request: Request):
    """OpenAlex / Semantic Scholar for jobs: the server adds its keys, the job only holds its short-lived token."""
    if request.headers.get("x-bonrs-job") not in _LLM_TOKENS or svc not in DATA_UP or not re.fullmatch(r"[A-Za-z0-9_/\-.:]{1,200}", path) or ".." in path:
        raise HTTPException(401, "invalid job token")
    base, k, how = DATA_UP[svc]; params = {k2: v for k2, v in request.query_params.items() if k2 != "api_key"}
    hdr = {h: v for h, v in request.headers.items() if h.lower() in ("accept", "content-type", "user-agent")}
    if db.setting(k): (params.__setitem__("api_key", db.setting(k)) if how == "param" else hdr.__setitem__("x-api-key", db.setting(k)))
    r = await run_in_threadpool(requests.request, request.method, f"{base}/{path}", params=params, data=await request.body(), headers=hdr, timeout=60)
    return PlainTextResponse(r.content[:20_000_000].decode("utf8", "replace"), status_code=r.status_code, media_type=r.headers.get("content-type", "application/json").split(";")[0])


# ---------------- jobs / worker ----------------
def enqueue(kind: str, slug: str | None, args: dict, owner: int, cap=True) -> int:
    if cap and owner and (db.one("SELECT COUNT(*) n FROM jobs WHERE owner=? AND status='queued'", owner) or {}).get("n", 0) >= 30:
        raise HTTPException(429, "too many queued jobs; wait for some to finish")
    return db.ex("INSERT INTO jobs(kind,slug,args,status,owner,created) VALUES (?,?,?,?,?,?)", kind, slug, json.dumps(args), "queued", owner, time.time())


@app.get("/api/jobs")
def my_jobs(u=Depends(user)): return db.q("SELECT * FROM jobs WHERE owner=? ORDER BY id DESC LIMIT 50", u["id"])


def _oauth(owner: int):
    return (db.one("SELECT oauth_token FROM users WHERE id=? AND disabled=0", owner) or {}).get("oauth_token") if owner else None


def _job_env(j: dict) -> dict:
    """API keys stay on the server (jobs get a short-lived token for the proxies). A user's own Claude subscription is
    the exception: Claude Code must hold that token itself, so it goes into this user's own sandboxed job only."""
    extra, oauth = {"BONRS_EMAIL": db.setting("contact_email")}, _oauth(j["owner"])
    if oauth: _OAUTH_OWNERS.add(j["owner"])
    else: _OAUTH_OWNERS.discard(j["owner"])
    if sandbox.ON or os.environ.get("BONRS_SELF_URL"):
        tok = "bonrs-job-" + secrets.token_urlsafe(32); _LLM_TOKENS[tok] = j["owner"]; j["_token"] = tok
        extra.update({"BONRS_DATA_PROXY": f"{SELF_URL}/api/data", "BONRS_JOB_TOKEN": tok})
        extra.update({"CLAUDE_CODE_OAUTH_TOKEN": oauth} if oauth else {"ANTHROPIC_BASE_URL": f"{SELF_URL}/api/llm", "ANTHROPIC_API_KEY": tok})
    else:  # local single-user dev without a proxy
        extra.update({"OPENALEX_API_KEY": db.setting("openalex_api_key"), "S2_API_KEY": db.setting("s2_api_key")})
        extra.update({"CLAUDE_CODE_OAUTH_TOKEN": oauth} if oauth else {"ANTHROPIC_API_KEY": _api_key(j["owner"])})
    return sandbox.base_env(j["owner"], extra)


def _launch(j: dict):
    a = json.loads(j["args"] or "{}"); py = [sandbox.python(), str(ROOT / "bonrs.py")]
    hours = num_setting("job_timeout_hours", 24.0)
    if j["kind"] == "run":
        rd = RUNS / j["slug"]; export_comments(j["slug"])
        cfg = {**_yaml(rd), "user_id": str(j["owner"])}
        safeio.write_text(rd, ".bonrs/knowledge.md", kb.select(cfg, None))  # shared tiers, selected by the server for this owner
        if (KNOWLEDGE / "INDEX.json").exists(): safeio.write_text(rd, ".bonrs/INDEX.json", (KNOWLEDGE / "INDEX.json").read_text())
        cmd = py + ["run", j["slug"]] + (["--from", a["from"]] if a.get("from") in pipeline.ORDER else []) + \
              (["--to", a["to"]] if a.get("to") in pipeline.ORDER else []) + (["--force"] if a.get("force") else [])
        logf, chown, cwd = safeio.open_write(rd, "logs/pipeline.log", append=True), [rd], rd
    else:  # ingest (member upload/URL, or one crawl source)
        w = Path(a["work"]); w.mkdir(parents=True, exist_ok=True)
        if (KNOWLEDGE / "INDEX.json").exists(): shutil.copyfile(KNOWLEDGE / "INDEX.json", w / "INDEX.json")
        cmd = py + ["kb", "ingest", a["src"], "--user", str(a.get("user", ""))[:254], "--hint", str(a.get("hint", ""))[:500], "--work", str(w)]
        if re.fullmatch(r"[0-9a-f]{64}", str(a.get("skip_sha") or "")): cmd += ["--skip-sha", a["skip_sha"]]  # unchanged page: no Claude call
        logf, chown, cwd, hours = safeio.open_write(w, "job.log", append=True), [], w, min(hours, 2.0)
    logf.write(f"\n===== job {j['id']} {j['kind']} {datetime.now():%Y-%m-%d %H:%M} =====\n".encode()); logf.flush()
    env = _job_env(j)
    try: p = sandbox.popen(j["owner"], cmd, cwd, env, chown=chown, timeout=hours * 3600, stdout=logf, stderr=subprocess.STDOUT)
    finally: logf.close()
    p.token = j.get("_token")
    db.ex("UPDATE jobs SET status='running', pid=?, started=? WHERE id=? AND status='queued'", p.pid, time.time(), j["id"])
    if j["slug"]: db.ex("UPDATE jobs SET status='done' WHERE slug=? AND status='waiting' AND id<?", j["slug"], j["id"])  # earlier pause is over
    return p


def _finish(j: dict, rc: int):
    """Server-side follow-up of a finished job: queue what it proposed (an admin reviews every draft)."""
    a = json.loads(j["args"] or "{}"); email = (db.one("SELECT email FROM users WHERE id=?", j["owner"]) or {}).get("email", "system")
    if j["kind"] == "run":
        rd = RUNS / j["slug"]
        if not safeio.exists(rd, "proposals"): return
        names = kb.import_drafts(rd / "proposals", email, j["owner"], f"run:{j['slug']}")
        for rel, _, _ in safeio.listing(rd / "proposals", 300): safeio.unlink(rd / "proposals", rel)
        if names: _event(rd, "kb_proposed", drafts=names)
        return
    w = Path(a.get("work", ""))
    if not str(w).startswith(str(DATA / "tenants") + "/") or not w.is_dir() or w.is_symlink(): return
    raw = safeio.read_text(w, "raw.txt", 400_000) or ""
    sha = (re.search(r"^SHA: ([0-9a-f]{64})$", raw, re.M) or [None, ""])[1]
    state_f = KNOWLEDGE / "sources.state.json"; state = json.loads(state_f.read_text()) if state_f.exists() else {}
    if a.get("crawl") and sha and state.get(a["src"], {}).get("hash") == sha: names = []  # page unchanged since last crawl
    else:
        names = kb.import_drafts(w / "drafts", "crawler" if a.get("crawl") else email, None if a.get("crawl") else j["owner"],
                                 f"crawl:{a['src']}" if a.get("crawl") else "ingest")
        if raw: (KNOWLEDGE / "inbox/raw").mkdir(parents=True, exist_ok=True); (KNOWLEDGE / "inbox/raw" / f"{(sha or secrets.token_hex(8))[:16]}.txt").write_text(raw)
    if a.get("crawl"):
        state[a["src"]] = {"hash": sha, "at": datetime.now().isoformat(timespec="seconds")} if sha else {"error": f"exit {rc}"}
        state_f.write_text(json.dumps(state, indent=1))
        thr = num_setting("auto_approve_confidence", 0.0)
        for n in names if thr else []:  # only admin-curated crawl sources, only drafts this very job produced
            d = next((x for x in kb.drafts() if x["file"] == n), None)
            try:
                if d and kb._f(d.get("confidence"), 0) >= thr: kb.approve(n)
            except ValueError: continue
    db.ex("UPDATE jobs SET note=? WHERE id=?", json.dumps({"drafts": names})[:500], j["id"])
    shutil.rmtree(w, ignore_errors=True)


def worker():
    running: dict[int, subprocess.Popen] = {}
    last_gate_scan = time.time()
    if not db.setting("last_crawl_at"): db.set_setting("last_crawl_at", time.time())  # first start: first crawl one period later
    while True:
        try:
            if time.time() - last_gate_scan > 60:  # gates past their timeout: resume so the pipeline auto-continues
                last_gate_scan = time.time()
                for rd in RUNS.iterdir():
                    if not SLUG.match(rd.name) or rd.is_symlink(): continue
                    try: due = _gate_due(rd)
                    except Exception: continue
                    if due and not db.one("SELECT id FROM jobs WHERE slug=? AND status IN ('queued','running')", rd.name):
                        enqueue("run", rd.name, {}, owner_of(rd.name), cap=False)
            for jid, p in list(running.items()):
                rc = p.poll()
                if rc is None: continue
                del running[jid]; _LLM_TOKENS.pop(getattr(p, "token", None), None)
                j = db.one("SELECT * FROM jobs WHERE id=?", jid)
                if j and j["status"] == "running":
                    st = "done" if rc == 0 else ("waiting" if rc == pipeline.WAITING else "failed")
                    db.ex("UPDATE jobs SET status=?, exit=?, finished=? WHERE id=?", st, rc, time.time(), jid)
                if j:
                    try: _finish(j, rc)
                    except Exception: traceback.print_exc()
            limit = num_setting("max_parallel_jobs", 2)
            per_owner: dict[int, int] = {}
            busy_slugs = set()
            for i in running:
                r = db.one("SELECT slug, owner FROM jobs WHERE id=?", i) or {}
                busy_slugs.add(r.get("slug")); per_owner[r.get("owner")] = per_owner.get(r.get("owner"), 0) + 1
            queued = db.q("SELECT * FROM jobs WHERE status='queued' ORDER BY id")
            queued.sort(key=lambda j: (per_owner.get(j["owner"], 0), j["id"]))  # fair share: owners with fewer running jobs first
            for j in queued:
                if len(running) >= limit: break
                if j["slug"] and j["slug"] in busy_slugs: continue
                if sandbox.ON and per_owner.get(j["owner"], 0) >= 1: continue  # one long job per user: its end reaps every process of that uid
                if per_owner.get(j["owner"], 0) >= max(1, limit - 1) and any(q["owner"] != j["owner"] for q in queued): continue
                try:
                    running[j["id"]] = _launch(j); busy_slugs.add(j["slug"]); per_owner[j["owner"]] = per_owner.get(j["owner"], 0) + 1
                except Exception as e: db.ex("UPDATE jobs SET status='failed', note=? WHERE id=?", str(e)[:500], j["id"])
            hours = num_setting("crawl_every_hours")
            if hours and time.time() - _num(db.setting("last_crawl_at")) > hours * 3600 and _api_key(0):  # crawls use the shared key
                db.set_setting("last_crawl_at", time.time()); _enqueue_crawl()
        except Exception:  # one bad record must never stop the queue for everyone
            traceback.print_exc()
        time.sleep(2)


@app.on_event("startup")
def startup():
    db.ensure_admin()
    if sandbox.ON:
        os.umask(0o077)
        for d, m in ((DATA, 0o711), (RUNS, 0o711), (DATA / "tenants", 0o711), (KNOWLEDGE, 0o700)):
            d.mkdir(parents=True, exist_ok=True); os.chmod(d, m)
        for f in DATA.glob("bonrs.db*"): os.chmod(f, 0o600)
        r = sandbox.run(0, ["true"], DATA / "tenants", timeout=30, capture_output=True, text=True)
        if r.returncode != 0: raise RuntimeError(f"BONRS_SANDBOX=1 but the sandbox helper failed: {r.stderr.strip()[:300]}")
    legacy = DATA / "ssh/id_ed25519"  # the old server-wide key goes to the first admin only
    adm = db.one("SELECT id FROM users WHERE role='admin' AND disabled=0 ORDER BY id")
    if legacy.exists() and adm and not (sandbox.tenant_dir(adm["id"]) / "ssh/id_ed25519").exists():
        dst = sandbox.tenant_dir(adm["id"]) / "ssh"
        for n in ("id_ed25519", "id_ed25519.pub"):
            if (legacy.parent / n).exists(): shutil.copyfile(legacy.parent / n, dst / n); os.chmod(dst / n, 0o600 if n == "id_ed25519" else 0o644)
    for j in db.q("SELECT id,pid FROM jobs WHERE status='running'"):  # server restarted mid-job: stop orphans, user can resume
        try: os.kill(j["pid"], signal.SIGTERM) if sandbox.ON else os.killpg(j["pid"], signal.SIGTERM)
        except (ProcessLookupError, PermissionError, TypeError): pass
    cut = db.q("SELECT * FROM jobs WHERE status='running'")
    db.ex("UPDATE jobs SET status='interrupted' WHERE status='running'")
    for j in cut:  # restart/update of the server: continue where the run stopped (done stages are skipped), at most 3 times in a row
        a = json.loads(j["args"] or "{}"); n = int(a.get("resumed", 0))
        if j["kind"] == "run" and n < 3 and not db.one("SELECT id FROM jobs WHERE slug=? AND status='queued'", j["slug"]):
            a["resumed"] = n + 1  # same args: a forced rerun stays forced, a normal run skips finished stages
            enqueue("run", j["slug"], a, j["owner"], cap=False)
    for rd in RUNS.iterdir():  # adopt runs created via CLI: they belong to the first admin (bonrs.yaml cannot pick an owner)
        if SLUG.match(rd.name) and not rd.is_symlink() and safeio.exists(rd, "bonrs.yaml") and adm and not db.one("SELECT slug FROM runs WHERE slug=?", rd.name):
            c = _yaml(rd)
            db.ex("INSERT INTO runs VALUES (?,?,?,?,?)", rd.name, adm["id"], str(c.get("idea") or "")[:5000], str(c.get("target_journal") or "")[:300], rd.stat().st_mtime)
    if os.environ.get("BONRS_WORKER", "1") == "1": threading.Thread(target=worker, daemon=True).start()


app.mount("/", StaticFiles(directory=str(ROOT / "web"), html=True), name="static")

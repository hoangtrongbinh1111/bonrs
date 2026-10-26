#!/usr/bin/env python3
"""Security regression checks against a running bonrs (throwaway data dir!).

    python3 tools/security_smoke.py http://127.0.0.1:8771 <BONRS_DATA of that server> admin@local <admin password>

The server should run with BONRS_CLAUDE_BIN pointing at a fake agent that writes env_seen.json / proxy_reply.json and plants
symlinks, BONRS_SELF_URL set, and BONRS_ANTHROPIC_UPSTREAM pointing at a fake upstream that echoes the key it receives.
"""
import json, sys, time
from pathlib import Path
import requests

B, DATA, AE, AP = sys.argv[1].rstrip("/"), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
ok, bad = [], []


def check(name, cond, detail=""):
    (ok if cond else bad).append(name + ("" if cond else f"  <-- {detail}"))


def login(email, pw):
    s = requests.Session(); s.headers["Origin"] = B
    r = s.post(B + "/api/login", json={"email": email, "password": pw}); r.raise_for_status(); return s


A = login(AE, AP)
A.put(B + "/api/admin/settings", json={"anthropic_api_key": "sk-real-admin-key", "openalex_api_key": "oa-secret", "s2_api_key": "s2-secret"}).raise_for_status()
for e in ("m1@local", "m2@local"): A.post(B + "/api/admin/users", json={"email": e, "password": "member12345", "role": "member"})
M1, M2 = login("m1@local", "member12345"), login("m2@local", "member12345")
me1 = M1.get(B + "/api/me").json()

# headers
h = requests.get(B + "/").headers
check("CSP on pages", "script-src 'self'" in h.get("content-security-policy", "") and "frame-ancestors 'none'" in h.get("content-security-policy", ""), h.get("content-security-policy"))
check("nosniff", h.get("x-content-type-options") == "nosniff")

# runs: one per member; the fake agent runs once for member 1
s1 = M1.post(B + "/api/runs", json={"idea": "member one secret idea", "journal": "J", "start": False}).json()["slug"]
s2 = M2.post(B + "/api/runs", json={"idea": "member two secret idea", "journal": "J", "start": False}).json()["slug"]
M1.put(B + f"/api/runs/{s1}/file", params={"path": "others.txt"}, data=s2)  # a hostile agent that somehow learned another slug
M1.post(B + f"/api/runs/{s1}/start", json={"from": "00_scope", "to": "00_scope"}).raise_for_status()
for _ in range(60):
    j = M1.get(B + f"/api/runs/{s1}").json()["jobs"]
    if j and j[0]["status"] not in ("queued", "running"): break
    time.sleep(1)
time.sleep(3)
env = json.loads(M1.get(B + f"/api/runs/{s1}/file", params={"path": "env_seen.json"}).text or "{}")
check("job env: no admin credentials", "BONRS_ADMIN_PASSWORD" not in env and "BONRS_ADMIN_EMAIL" not in env, sorted(env))
check("job env: no foreign secrets", "AWS_SECRET_ACCESS_KEY" not in env)
check("job env: no provider keys", not any(v in ("oa-secret", "s2-secret") for v in env.values()), [k for k, v in env.items() if v in ("oa-secret", "s2-secret")])
check("data proxy rejects bad token", requests.get(B + "/api/data/openalex/works", headers={"x-bonrs-job": "nope"}).status_code == 401)
check("job env: API key is a proxy token", env.get("ANTHROPIC_API_KEY", "").startswith("bonrs-job-"), env.get("ANTHROPIC_API_KEY"))
reply = json.loads(M1.get(B + f"/api/runs/{s1}/file", params={"path": "proxy_reply.json"}).text or "{}")
check("LLM proxy injects the real key upstream", reply.get("key_seen_by_upstream") == "sk-real-admin-key", reply)
esc = M1.get(B + f"/api/runs/{s1}/file", params={"path": "escape.json"})
if esc.status_code == 200:  # sandbox mode: the fake agent tried to break out (see fake_claude_sbx)
    e = esc.json(); check("agent runs as its own uid", e.get("uid", 0) >= 20000 and e.get("groups") == [], e)
    for k, v in e.items():
        if isinstance(v, str) and (v.startswith("ALLOWED") or v.startswith("denied")): check(f"sandbox blocks: {k}", v.startswith("denied"), v)
tok = env.get("ANTHROPIC_API_KEY", "x")
r = requests.post(B + "/api/llm/v1/messages", headers={"x-api-key": tok}, json={}); check("job token dies with the job", r.status_code == 401, (r.status_code, r.text[:200]))
check("LLM proxy rejects bad token", requests.post(B + "/api/llm/v1/messages", headers={"x-api-key": "nope"}, json={}).status_code == 401)

# planted symlinks (what a hostile agent would do) never let the server read outside the run
for p in ("leak_db.json", "leakdir/bonrs.db"):
    r = M1.get(B + f"/api/runs/{s1}/file", params={"path": p, "raw": 1})
    check(f"symlink {p} not served", r.status_code == 404 and b"SQLite" not in r.content, r.status_code)
check("tree hides symlinks", not any("leak" in x for x in M1.get(B + f"/api/runs/{s1}/tree").json()))
rd1 = DATA / "runs" / s1
(rd1 / "state.json").rename(rd1 / "state.real"); (rd1 / "state.json").symlink_to(DATA / "runs" / s2 / "state.json")
check("symlinked state.json is ignored", all(x["slug"] != s1 for x in M1.get(B + "/api/runs").json()))
(rd1 / "state.json").unlink(); (rd1 / "state.real").rename(rd1 / "state.json")

# tenant isolation
check("member cannot open another run", M1.get(B + f"/api/runs/{s2}").status_code == 403)
r = M1.get(B + f"/api/runs/{s1}/log", params={"stage": f"../../{s2}/logs/00_scope"})
check("log stage traversal blocked", r.status_code == 400, r.status_code)
check("file path traversal blocked", M1.get(B + f"/api/runs/{s1}/file", params={"path": f"../{s2}/bonrs.yaml"}).status_code == 400)

# active content never renders on our origin
M1.put(B + f"/api/runs/{s1}/file", params={"path": "x.html"}, data="<script>alert(1)</script>").raise_for_status()
r = M1.get(B + f"/api/runs/{s1}/file", params={"path": "x.html", "raw": 1})
check("raw .html downloads, sandboxed", "attachment" in r.headers.get("content-disposition", "") and r.headers.get("content-type") == "application/octet-stream"
      and "sandbox" in r.headers.get("content-security-policy", ""), dict(r.headers))
M1.put(B + f"/api/runs/{s1}/file", params={"path": "y.svg"}, data="<svg onload=alert(1)>").raise_for_status()
check("raw .svg downloads", "attachment" in M1.get(B + f"/api/runs/{s1}/file", params={"path": "y.svg", "raw": 1}).headers.get("content-disposition", ""))
for p in (".claude/settings.json", "CLAUDE.md", "proposals/x.md", ".bonrs/knowledge.md", ".git/config", "state.json"):
    check(f"managed file {p} not editable", M1.put(B + f"/api/runs/{s1}/file", params={"path": p}, data="x").status_code == 403)

# config cannot pick an owner or inject ssh options
r = M1.put(B + f"/api/runs/{s1}/config", data="idea: x\ntarget_journal: J\nuser_id: '1'\nremote:\n  hosts:\n  - {name: h, type: ssh, ssh: '-oProxyCommand=touch /tmp/pwn'}\n")
check("config with ssh option rejected", r.status_code == 400, r.status_code)
M1.put(B + f"/api/runs/{s1}/config", data="idea: x\ntarget_journal: J\nuser_id: '1'\n").raise_for_status()
check("config user_id forced to owner", f"user_id: '{me1['id']}'" in M1.get(B + f"/api/runs/{s1}/file", params={"path": "bonrs.yaml"}).text)
check("host ssh option rejected", M1.post(B + "/api/hosts", json={"name": "h", "type": "ssh", "ssh": "-oProxyCommand=x"}).status_code == 400)
check("host workdir injection rejected", M1.post(B + "/api/hosts", json={"name": "h", "type": "ssh", "ssh": "u@h", "workdir": "x;id"}).status_code == 400)

# knowledge base
A.put(B + "/api/kb/file", params={"path": f"50-user/{me1['id']}/private.md"}, data="---\nname: p\n---\nM1 PRIVATE")
check("member cannot read other's personal skill", M2.get(B + "/api/kb/file", params={"path": f"50-user/{me1['id']}/private.md"}).status_code == 403)
check("member cannot read inbox", M2.get(B + "/api/kb/file", params={"path": "inbox/jobs.log"}).status_code == 403)
check("index hides other users' tier", not any(r["path"].startswith(f"50-user/{me1['id']}/") for r in M2.get(B + "/api/kb").json()))
M1.put(B + "/api/kb/file", params={"path": f"50-user/{me1['id']}/evil.md"}, data="---\nlevel: user\nuser_id: '../00-general'\nconfidence: 1\n---\nEVIL").raise_for_status()
f = M1.post(B + "/api/kb/promote", json={"path": f"50-user/{me1['id']}/evil.md"}).json()["file"]
d = next(x for x in A.get(B + "/api/kb/drafts").json() if x["file"] == f)
check("promoted draft target stays in own tier", d["target"] == f"50-user/{me1['id']}/{f}" and "confidence" not in d, d)
check("member sees only own drafts", all(x.get("submitted_by") == "m2@local" for x in M2.get(B + "/api/kb/drafts").json()))
check("member cannot approve", M1.post(B + f"/api/kb/drafts/{f}/approve", json={}).status_code == 403)
r = A.post(B + f"/api/kb/drafts/{f}/approve", json={}); check("approve lands in own tier", r.json().get("path", "").startswith(f"50-user/{me1['id']}/"), r.text)

# sessions
check("cookie works", requests.get(B + "/api/me", cookies={"bonrs": M2.cookies.get("bonrs")}).status_code == 200)
stolen = M2.cookies.get("bonrs"); M2.post(B + "/api/logout")
check("logout revokes copied cookie", requests.get(B + "/api/me", cookies={"bonrs": stolen}).status_code == 401)
uid1 = [u for u in A.get(B + "/api/admin/users").json() if u["email"] == "m1@local"][0]["id"]
c1 = M1.cookies.get("bonrs"); A.delete(B + f"/api/admin/users/{uid1}")
new = A.post(B + "/api/admin/users", json={"email": "m3@local", "password": "member12345"}).json()["id"]
check("deleted user's id is never reused", new != uid1, (new, uid1))
check("deleted user's cookie is dead", requests.get(B + "/api/me", cookies={"bonrs": c1}).status_code == 401)
for _ in range(9): requests.post(B + "/api/login", json={"email": "m3@local", "password": "wrong"}, headers={"Origin": B})
check("login rate limit", requests.post(B + "/api/login", json={"email": "m3@local", "password": "member12345"}, headers={"Origin": B}).status_code == 429)
check("weak password refused", A.post(B + "/api/admin/users", json={"email": "w@local", "password": "123"}).status_code == 400)
check("bad role refused", A.post(B + "/api/admin/users", json={"email": "r@local", "password": "member12345", "role": "root"}).status_code == 400)

# request guards
check("oversized body refused before reading", A.put(B + f"/api/runs/{s2}/file", params={"path": "big.txt"}, data=b"x" * (9 << 20)).status_code == 413)
check("chunked body without length refused", A.put(B + f"/api/runs/{s2}/file", params={"path": "c.txt"}, data=iter([b"a" * 10])).status_code == 411)
check("cross-origin POST refused", requests.post(B + "/api/login", json={}, headers={"Origin": "https://evil.example"}).status_code == 403)
r = requests.post(B + f"/api/runs/{s1}/upload", files={"files": ("a.txt", b"x")}, headers={"Origin": B})
check("multipart without login refused before parsing", r.status_code == 401, r.status_code)
check("unknown stage refused", A.post(B + f"/api/runs/{s1}/start", json={"from": "../../x"}).status_code == 400)
check("bad numeric setting refused", A.put(B + "/api/admin/settings", json={"max_parallel_jobs": "abc"}).status_code == 400)

print("\n".join("PASS " + x for x in ok)); print("\n".join("FAIL " + x for x in bad))
print(f"\n{len(ok)} passed, {len(bad)} failed"); sys.exit(1 if bad else 0)

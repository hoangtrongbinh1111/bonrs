"""Smoke test: drive a full bonrs flow through the web API against the mock agent.

Start a server first, e.g.
  BONRS_DATA=/tmp/bonrs-mock BONRS_CLAUDE_BIN=$PWD/tools/mock_claude BONRS_MOCK_DELAY=0.3 \
  BONRS_ADMIN_EMAIL=admin@local BONRS_ADMIN_PASSWORD=admin123 .venv/bin/uvicorn bonrs.web:app --port 8767
then: python3 tools/smoke_web.py [http://127.0.0.1:8767]
"""
import json, sys, time, urllib.request, urllib.error, http.cookiejar, uuid
B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8767"
cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def call(m, p, body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    rq = urllib.request.Request(B + "/api" + p, data=data, method=m, headers={"Origin": B, **({"Content-Type": ctype} if data else {})})
    with op.open(rq) as r: t = r.read().decode(); return json.loads(t) if r.headers.get_content_type() == "application/json" else t
def run(slug): return call("GET", f"/runs/{slug}")
def wait(slug, until, tmo=600):
    t0 = time.time()
    while time.time() - t0 < tmo:
        r = run(slug)
        if until(r): return r
        time.sleep(1.5)
    sys.exit(f"timeout {slug}: done={r['done']} job={r['job']} gate={r['gate']}")
call("POST", "/login", {"email": "admin@local", "password": "admin123"})
try: call("POST", "/admin/users", {"email": "member@local", "password": "member123", "role": "member"})
except urllib.error.HTTPError as e:  # rerun on the same data dir: the member already exists
    if e.code != 400: raise
idea = "Physics-informed neural networks for lithium-ion battery state-of-health estimation with very few labelled cycles"
A = call("POST", "/runs", {"idea": idea, "journal": "Journal of Energy Storage", "backup_journals": "Applied Energy, eTransportation", "domain": "ml",
     "article_type": "research", "format": "auto", "gates": ["after_scope", "after_literature", "after_plan", "after_results", "before_submission"], "start": True})["slug"]
print("run A", A)
notes = {"after_scope": None, "after_literature": "Ưu tiên dữ liệu XJTU và MIT; bỏ NASA vì quá ít tế bào.", "after_plan": None}
step = 0; paused = redone = False
while True:
    r = wait(A, lambda r: r["gate"] or (r["job"] and r["job"]["status"] in ("done", "failed")))
    if r["job"]["status"] == "failed": sys.exit("FAILED " + json.dumps(r["job"]))
    if not r["gate"]: break
    g = r["gate"]["gate"]; n = notes.get(g)
    print(f"  gate {g} after {r['gate']['stage']} done={len(r['done'])} cost=${r['cost']:.2f}")
    if g == "after_scope":
        call("POST", f"/runs/{A}/comments", {"path": "scope.md", "quote": "under 2% RMSE using only 10% of labelled cycles", "body": "Nêu rõ tập dữ liệu nào cho con số 2% này.", "kind": "must_fix"})
        call("POST", f"/runs/{A}/comments", {"body": "Văn phong nên ngắn gọn, tránh câu bị động dài.", "kind": "style"})
    if g == "after_literature":
        bnd = uuid.uuid4().hex; pdf = b"%PDF-1.4\n% mock upload\n"
        body = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"where\"\r\n\r\nlit/uploads\r\n--{bnd}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"plett2015_ch3.pdf\"\r\nContent-Type: application/pdf\r\n\r\n").encode() + pdf + f"\r\n--{bnd}--\r\n".encode()
        call("POST", f"/runs/{A}/upload", raw=body, ctype=f"multipart/form-data; boundary={bnd}")
    if g == "after_scope" and not paused:  # pause, then resume with the header button
        call("POST", f"/runs/{A}/gate", {"action": "reject", "note": "xem lại sau"}); paused = True
        r = run(A); assert not r["gate"] and r["job"]["status"] != "queued", "pause must not queue a job"
        call("POST", f"/runs/{A}/start", {}); step += 1; continue
    if g == "after_plan" and not redone:  # redo the stage with guidance; the same gate must reopen
        call("POST", f"/runs/{A}/gate", {"action": "redo", "note": "Thêm baseline bán giám sát (mean teacher)."}); redone = True
        try: call("POST", f"/runs/{A}/gate", {"action": "approve"}); sys.exit("double answer was accepted")
        except urllib.error.HTTPError as e: assert e.code in (400, 409), e.code
        step += 1; continue
    call("POST", f"/runs/{A}/gate", {"action": "guide" if n else "approve", "note": n})
    step += 1
r = run(A); print(f"A finished: done={len(r['done'])}/10 cost=${r['cost']:.2f} reviews={[(x['round'], x['score'], x['decision']) for x in r['reviews']]} gates_answered={step}")
assert len(r["done"]) == 10 and len(set(r["done"])) == 10, r["done"]
assert r["stage_info"]["03_plan"]["runs"] == 2, "redo must rerun the plan stage"
assert any(e["type"] == "gate_answered" and e.get("action") == "reject" for e in r["events"]), "pause not logged"
# run B: paused at the literature gate
Bs = call("POST", "/runs", {"idea": "Federated learning for early sepsis prediction across hospitals with heterogeneous EHR schemas", "journal": "npj Digital Medicine",
     "domain": "biomed", "article_type": "research", "gates": ["after_scope", "after_literature"], "start": True})["slug"]
wait(Bs, lambda r: r["gate"]); call("POST", f"/runs/{Bs}/gate", {"action": "approve"})
r = wait(Bs, lambda r: r["gate"] and r["gate"]["gate"] == "after_literature"); print("run B waiting at", r["gate"]["gate"])
# run C: created, not started
C = call("POST", "/runs", {"idea": "Remittances and household education spending in Vietnam: evidence from VHLSS 2010-2022", "journal": "World Development",
     "domain": "socsci", "article_type": "research", "start": False})["slug"]; print("run C created", C)
s1 = call("POST", "/runs", {"idea": "同一个想法", "journal": "J", "start": False})["slug"]; s2 = call("POST", "/runs", {"idea": "同一个想法", "journal": "J", "start": False})["slug"]
assert s1 != s2 and not s1.startswith("-"), (s1, s2)  # same idea twice in a minute, non-Latin title
try: call("PUT", f"/runs/{A}/file?path=state.json", raw=b"{}", ctype="text/plain"); sys.exit("state.json edit was allowed")
except urllib.error.HTTPError as e: assert e.code == 403, e.code
# concurrency: parallel requests used to segfault the server through one shared sqlite connection
from concurrent.futures import ThreadPoolExecutor
paths = ["/runs", f"/runs/{A}", f"/runs/{A}/history", f"/runs/{A}/comments", f"/runs/{A}/tree", "/kb", "/hosts"]
with ThreadPoolExecutor(16) as ex: list(ex.map(lambda i: call("GET", paths[i % len(paths)]), range(400)))
assert call("GET", "/me")["email"] == "admin@local"
print("SMOKE OK")

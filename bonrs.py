#!/usr/bin/env python3
"""bonrs CLI (internal; the web UI calls the same functions)."""
import argparse, json, os, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from bonrs import pipeline, lit, journal, remote, audit, registry, kb
from bonrs.pipeline import ORDER

ap = argparse.ArgumentParser(prog="bonrs"); sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("new", help="create a run"); p.add_argument("idea"); p.add_argument("--journal", required=True); p.add_argument("--slug")
p.add_argument("--domain", default="other"); p.add_argument("--type", dest="article_type", default="research"); p.add_argument("--format", dest="fmt", default="auto")
p.add_argument("--model"); p.add_argument("--budget", type=float); p.add_argument("--user")
p = sub.add_parser("run", help="run pipeline (resumes; exit 3 = waiting at a gate)"); p.add_argument("slug")
p.add_argument("--from", dest="start", choices=ORDER); p.add_argument("--to", dest="stop", choices=ORDER); p.add_argument("--force", action="store_true")
p = sub.add_parser("approve", help="answer an open gate"); p.add_argument("slug"); p.add_argument("--action", default="approve", choices=["approve", "guide", "reject"]); p.add_argument("--note")
p = sub.add_parser("status"); p.add_argument("slug", nargs="?")
p = sub.add_parser("upload", help="add PDFs you downloaded manually"); p.add_argument("slug"); p.add_argument("pdf", nargs="+")
p = sub.add_parser("lit"); p.add_argument("slug"); p.add_argument("queries", nargs="+"); p.add_argument("-n", type=int, default=20); p.add_argument("--biomed", action="store_true")
p = sub.add_parser("journal"); p.add_argument("slug"); p.add_argument("--name"); p.add_argument("--topic", default=""); p.add_argument("-n", type=int, default=12)
p = sub.add_parser("remote"); p.add_argument("slug"); p.add_argument("action", choices=["push", "run", "tail", "status", "pull", "doctor"])
p.add_argument("--host", help="host name, or auto = least busy host of this run"); p.add_argument("--cmd"); p.add_argument("--tag", default="job"); p.add_argument("-n", type=int, default=80)
p.add_argument("--gpu", action="store_true", help="with --host auto: only hosts that have a GPU")
p = sub.add_parser("registry", help="build exp/results/registry.json; --table keys..."); p.add_argument("slug"); p.add_argument("--table", nargs="*"); p.add_argument("--md", action="store_true")
p = sub.add_parser("audit"); p.add_argument("slug"); p.add_argument("--final", action="store_true")
p = sub.add_parser("learn", help="propose a lesson/rule (goes to the admin review queue)"); p.add_argument("text")
p.add_argument("--level", default="experience", choices=list(kb.LEVELS)); p.add_argument("--category", default="WRITING")
p.add_argument("--severity", type=int, default=2); p.add_argument("--domain"); p.add_argument("--journal")
p = sub.add_parser("kb", help="index | select <slug> | ingest <file|url> | crawl | drafts")
p.add_argument("action", choices=["index", "select", "ingest", "crawl", "drafts"]); p.add_argument("target", nargs="?"); p.add_argument("--user", default="admin"); p.add_argument("--hint", default="")
p.add_argument("--work", help="ingest: folder for raw.txt and drafts/ (the server imports drafts/ afterwards)")
p.add_argument("--skip-sha", default="", help="ingest: skip distilling when the page text has this sha256 (unchanged)")

a = ap.parse_args()
if a.cmd == "new":
    rd = pipeline.new_run(a.idea, a.journal, a.slug, domain=a.domain, article_type=a.article_type, fmt=a.fmt, model=a.model, budget=a.budget, user_id=a.user)
    print(f"created {rd}\nedit {rd}/bonrs.yaml (hosts, budget, gates), then: python3 bonrs.py run {rd.name}")
elif a.cmd == "run": pipeline.run(a.slug, a.start, a.stop, a.force)
elif a.cmd == "approve": pipeline.approve(a.slug, a.action, a.note)
elif a.cmd == "status":
    for rd in ([pipeline.RUNS / a.slug] if a.slug else sorted(pipeline.RUNS.iterdir())):
        if (rd / "state.json").exists():
            st = json.loads((rd / "state.json").read_text()); gate = (rd / "hitl/waiting.json").exists()
            print(f"{rd.name:40} done={len(st['done'])}/{len(ORDER)} cost=${st.get('cost', 0):.2f} {'WAITING' if gate else ''} reviews={st.get('reviews', [])}")
elif a.cmd == "upload":
    rd, *_ = pipeline.load(a.slug)
    for f in a.pdf:
        dst = rd / "lit/uploads" / Path(f).name; shutil.copy(f, dst); lit.pdf_text(dst); pipeline.event(rd, "upload", actor="user", file=dst.name); print("added", dst)
elif a.cmd == "lit": rd, *_ = pipeline.load(a.slug); lit.search(rd, a.queries, a.n, a.biomed)
elif a.cmd == "journal": rd, cfg, _ = pipeline.load(a.slug); journal.profile(rd, a.name or cfg["target_journal"], a.topic or cfg["idea"], a.n)
elif a.cmd == "remote":
    rd, cfg, _ = pipeline.load(a.slug)
    {"push": lambda: remote.push(cfg, rd, a.host), "run": lambda: remote.run(cfg, rd, a.cmd, a.host, a.tag, a.gpu), "tail": lambda: remote.tail(cfg, rd, a.host, a.tag, a.n),
     "status": lambda: remote.status(cfg, rd, a.host), "pull": lambda: remote.pull(cfg, rd, a.host), "doctor": lambda: remote.doctor(cfg, rd, a.host)}[a.action]()
elif a.cmd == "registry":
    rd, *_ = pipeline.load(a.slug); reg = registry.build(rd)
    print(registry.table(reg, a.table, fmt="md" if a.md else "latex") if a.table else f"{len(reg)} values -> exp/results/registry.json")
elif a.cmd == "audit": rd, *_ = pipeline.load(a.slug); sys.exit(audit.cli(rd, a.final))
elif a.cmd == "learn":  # inside a run: proposals/ of that run; the server queues them for admin review after the job
    out = Path(os.environ["BONRS_RUN"]) / "proposals" if os.environ.get("BONRS_RUN") else None
    print("proposed (admin reviews before it is used):", kb.learn(a.text, a.level, a.category, a.severity, a.domain, a.journal, out=out))
elif a.cmd == "kb":
    if a.action == "index": print(len(kb.index()), "skills indexed")
    elif a.action == "select": rd, cfg, _ = pipeline.load(a.target); print(kb.select(cfg, rd)[:3000], "...")
    elif a.action == "ingest": print("drafts:", [p.name for p in kb.ingest(a.target, a.user, a.hint, Path(a.work) if a.work else None, a.skip_sha)])
    elif a.action == "crawl":  # local admin use; the web app enqueues one ingest job per source instead
        for s in kb.sources():
            w = Path(tempfile.mkdtemp())
            try: kb.ingest(s["url"], "crawler", f"level={s.get('level', 'general')} source_name={s.get('name')}", w); print("queued:", kb.import_drafts(w / "drafts", "crawler", None, s["url"]))
            except Exception as e: print("skip", s["url"], e)
    else: print(json.dumps([{k: d.get(k) for k in ("file", "level", "name", "source")} for d in kb.drafts()], indent=1))

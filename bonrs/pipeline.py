"""Stages + state + HITL gates + git history. Each stage: run agent, check the files it was supposed to produce, commit."""
import json, os, re, subprocess
from datetime import datetime, timedelta
from pathlib import Path
import yaml
from . import RUNS
from .agent import run_stage

STAGES = {  # stage -> files that must exist afterwards
    "00_scope": ["scope.md", "hypotheses.json"],
    "01_literature": ["lit/review.md", "lit/gaps.md", "lit/key_papers.md", "lit/novelty.md"],
    "02_journal": ["journal/style_guide.md", "journal/compliance_checklist.md"],
    "03_plan": ["plan.md", "plan/evaluator.md", "paper/outline.md"],
    "04_experiment": ["exp/results/summary.md", "exp/results/registry.json", "exp/analysis_contract.md"],
    "05_draft": ["paper/claims.yaml"],      # + main.tex or main.md (checked specially)
    "06_review": [], "07_revise": ["paper/response_letter.md"],
    "08_submission": ["submission/cover_letter.md", "submission/checklist.md"],
    "09_retro": ["retro.md"],
}
ORDER = list(STAGES)
GATES = {"00_scope": "after_scope", "01_literature": "after_literature", "03_plan": "after_plan", "07_revise": "after_results", "08_submission": "before_submission"}
WAITING = 3  # exit code when paused at a gate
ALWAYS_WAIT = {"after_scope"}  # go/no-go on the hypotheses: always on, never auto-continues


def _git(rd: Path, *args): return subprocess.run(["git", "-C", str(rd), *args], capture_output=True, text=True)


def event(rd: Path, typ: str, actor="system", **payload):
    with (rd / "events.jsonl").open("a") as fh:
        fh.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "type": typ, "actor": actor, **payload}, ensure_ascii=False) + "\n")


def new_run(idea: str, journal: str, slug: str | None = None, **o) -> Path:
    slug = slug or re.sub(r"[^a-z0-9]+", "-", idea.lower())[:40].strip("-")
    rd = RUNS / slug; rd.mkdir(parents=True, exist_ok=False)
    cfg = {"idea": idea, "target_journal": journal, "backup_journals": [], "domain": o.get("domain") or "other",
           "article_type": o.get("article_type") or "auto",  # "auto": stage 02 decides from the journal
           "language": "en", "paper_format": o.get("fmt") or "auto",
           "model": o.get("model") or "claude-opus-5-5", "max_budget_usd": o.get("budget") or 30,
           "review": {"max_rounds": 3, "accept_score": 7.5},
           "gates": {g: True for g in GATES.values()}, "gate_timeout_hours": 12,
           "remote": {"hosts": [{"name": "local", "type": "local", "setup": "auto"}]},
           "user_id": o.get("user_id"), "base_papers": list(o.get("base_papers") or [])}
    (rd / "bonrs.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    (rd / "state.json").write_text(json.dumps({"slug": slug, "done": [], "created": datetime.now().isoformat(), "cost": 0.0}))
    (rd / "decisions.md").write_text("# Decisions log\n")
    for d in ("lit/base", "lit/uploads", "exp/results", "paper", "reviews", "hitl", "knowledge", "logs"): (rd / d).mkdir(parents=True, exist_ok=True)
    (rd / ".gitignore").write_text("lit/pdf/\n*.pt\nexp/data/\nexp/.venv/\n__pycache__/\n.bonrs/\n")
    _git(rd, "init", "-q"); _git(rd, "add", "-A"); _git(rd, "-c", "user.name=bonrs", "-c", "user.email=bonrs@local", "commit", "-qm", "new run")
    event(rd, "run_created", idea=idea, journal=journal)
    return rd


def load(slug: str):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", slug or ""): raise SystemExit(f"bad run slug: {slug!r}")
    rd = RUNS / slug
    return rd, yaml.safe_load((rd / "bonrs.yaml").read_text()), json.loads((rd / "state.json").read_text())


def _save(rd, st): (rd / "state.json").write_text(json.dumps(st, indent=1))


def _commit(rd, msg): _git(rd, "add", "-A"); _git(rd, "-c", "user.name=bonrs", "-c", "user.email=bonrs@local", "commit", "-qm", msg)


def _missing(rd, stage):
    miss = [f for f in STAGES[stage] if not (rd / f).exists()]
    if stage == "05_draft" and not ((rd / "paper/main.tex").exists() or (rd / "paper/main.md").exists()): miss.append("paper/main.tex|main.md")
    return miss


def _gate_check(rd, cfg, st) -> str | None:
    """Return guidance text if a gate was answered; raise SystemExit(WAITING) if still waiting."""
    w = rd / "hitl/waiting.json"
    if not w.exists(): return None
    wait = json.loads(w.read_text()); resp = rd / "hitl/response.json"
    if resp.exists():
        r = json.loads(resp.read_text()); resp.unlink(); w.unlink()
        event(rd, "gate_answered", actor=r.get("user", "user"), gate=wait["gate"], action=r.get("action"), note=r.get("note"))
        if r.get("action") == "reject": raise SystemExit(f"gate {wait['gate']} rejected: {r.get('note')}")
        if r.get("note"):
            with (rd / "decisions.md").open("a") as fh: fh.write(f"\n- {datetime.now():%Y-%m-%d %H:%M} [user @ {wait['gate']}] {r['note']}\n")
            return f"USER GUIDANCE at gate {wait['gate']}: {r['note']}"
        return None
    if gate_due(rd):
        w.unlink(); event(rd, "gate_timeout", gate=wait["gate"]); return None
    print(f"waiting at gate {wait['gate']} since {wait['since']} (python3 bonrs.py approve {rd.name} [--note ...])")
    raise SystemExit(WAITING)


def gate_due(rd: Path) -> bool:
    """Open, unanswered gate whose timeout has passed (gate_timeout_hours 0 = wait forever)."""
    w = rd / "hitl/waiting.json"
    if not w.exists() or (rd / "hitl/response.json").exists(): return False
    if json.loads(w.read_text()).get("gate") in ALWAYS_WAIT: return False
    h = float((yaml.safe_load((rd / "bonrs.yaml").read_text()) or {}).get("gate_timeout_hours", 12) or 0)
    return bool(h) and datetime.now() > datetime.fromisoformat(json.loads(w.read_text())["since"]) + timedelta(hours=h)


def _open_gate(rd, cfg, stage):
    g = GATES.get(stage)
    if g and (g in ALWAYS_WAIT or cfg.get("gates", {}).get(g)):
        (rd / "hitl/waiting.json").write_text(json.dumps({"gate": g, "stage": stage, "since": datetime.now().isoformat()}))
        event(rd, "gate_opened", gate=g, stage=stage)


def _run_one(rd, cfg, st, stage, extra=""):
    print(f"==> {stage}"); event(rd, "stage_start", actor=f"agent:{stage}")
    out = run_stage(rd, stage, cfg, extra)
    cost = float(out.get("total_cost_usd") or 0); st["cost"] = round(st.get("cost", 0) + cost, 4)
    print(f"    {out.get('seconds')}s cost=${cost:.2f} total=${st['cost']:.2f} {str(out.get('result', ''))[:160]}")
    event(rd, "stage_end", actor=f"agent:{stage}", cost=cost, seconds=out.get("seconds"), error=bool(out.get("is_error")))
    _commit(rd, f"{stage} cost=${cost:.2f}")
    return out


def run(slug: str, start: str | None = None, stop: str | None = None, force=False):
    rd, cfg, st = load(slug)
    guidance = _gate_check(rd, cfg, st) or ""
    i0 = ORDER.index(start) if start else 0
    i1 = ORDER.index(stop) + 1 if stop else len(ORDER)
    for stage in ORDER[i0:i1]:
        if stage in st["done"] and not force and stage != "07_revise": print(f"skip {stage} (done)"); continue  # 07 runs inside the review loop
        if stage == "07_revise": continue
        if stage == "06_review": _review_loop(rd, cfg, st, guidance, fresh=force); guidance = ""
        else:
            out = _run_one(rd, cfg, st, stage, guidance); guidance = ""
            miss = _missing(rd, stage)
            if out.get("is_error") or miss:
                _save(rd, st); raise SystemExit(f"stage {stage} failed. missing={miss}. see logs/{stage}.stderr.txt")
            if stage not in st["done"]: st["done"].append(stage)
            st[stage] = {"cost": out.get("total_cost_usd"), "at": datetime.now().isoformat()}
        _save(rd, st); _open_gate(rd, cfg, stage)
        if (rd / "hitl/waiting.json").exists() and stage != ORDER[i1 - 1]: _gate_check(rd, cfg, st)  # pauses here unless answered
    print(f"done. total cost ${st['cost']:.2f}")


def _latest_review(rd):
    rs = sorted((rd / "reviews").glob("round_*.json"))
    return json.loads(rs[-1].read_text()) if rs else None


def _review_loop(rd, cfg, st, guidance="", fresh=False):
    mx, thr = cfg["review"]["max_rounds"], cfg["review"]["accept_score"]
    k = len(list((rd / "reviews").glob("round_*.json")))
    if fresh and "06_review" in st["done"]: mx += k  # a forced rerun gets a full new budget of rounds
    while k < mx:
        k += 1
        out = _run_one(rd, cfg, st, "06_review", f"This is review round {k}. Write reviews/round_{k}.md and reviews/round_{k}.json. {guidance}")
        rv = _latest_review(rd)
        if out.get("is_error") or not rv or not (rd / f"reviews/round_{k}.json").exists(): _save(rd, st); raise SystemExit("review failed; see logs/06_review.stderr.txt")
        st.setdefault("reviews", []).append({"round": k, "score": rv.get("score"), "decision": rv.get("decision"), "open_major": rv.get("open_major")}); _save(rd, st)
        print(f"    score={rv.get('score')} decision={rv.get('decision')} open_major={rv.get('open_major')}")
        prev = st["reviews"][-2] if len(st["reviews"]) > 1 else None
        if rv.get("decision") in ("accept", "minor") and float(rv.get("score") or 0) >= thr and not rv.get("open_major") and (prev is None or float(prev.get("score") or 0) >= thr or k == mx): break
        comments = rd / "comments/open.md"
        extra = f"Address reviews/round_{k}.md (only items the Area Chair upheld)" + (f" and user comments in {comments}." if comments.exists() else ".")
        out = _run_one(rd, cfg, st, "07_revise", extra + " Update paper/ and write paper/response_letter.md.")
        if out.get("is_error") or _missing(rd, "07_revise"): _save(rd, st); raise SystemExit("revise failed; see logs/07_revise.stderr.txt")
        _open_gate(rd, cfg, "07_revise")
        if (rd / "hitl/waiting.json").exists(): _save(rd, st); _gate_check(rd, cfg, st)
    for s in ("06_review", "07_revise"):
        if s not in st["done"]: st["done"].append(s)
    _save(rd, st)


def approve(slug: str, action="approve", note: str | None = None, user="user"):
    rd = RUNS / slug
    with open(rd / "hitl/response.json", "x") as fh:  # "x": a second answer to the same gate fails instead of overwriting
        fh.write(json.dumps({"action": action, "note": note, "user": user, "ts": datetime.now().isoformat()}))
    print("recorded; resume with: python3 bonrs.py run", slug)

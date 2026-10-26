"""Thin wrapper around `claude -p`. One call = one pipeline stage. Full transcript kept as stream-json."""
import json, os, signal, subprocess, time
from pathlib import Path
from . import PROMPTS, ROOT
from . import kb

TOOLS = "Read,Write,Edit,Glob,Grep,Bash,WebFetch,WebSearch,Agent,Skill"


def system_prompt(run_dir: Path, cfg: dict) -> str:
    goal = {k: cfg.get(k) for k in ("idea", "target_journal", "domain", "article_type", "paper_format", "language")}
    return ("You are bonrs, an autonomous research agent. There is no human to ask: decide, log the decision in decisions.md, continue.\n"
            f"GOAL ANCHOR (never drift from this): {json.dumps(goal, ensure_ascii=False)}\n"
            f"Working directory: {run_dir}\nRun config (bonrs.yaml):\n{json.dumps(cfg, indent=1, ensure_ascii=False, default=str)}\n"
            f"Helper CLI via Bash: `python3 {ROOT / 'bonrs.py'} <cmd>` (lit, journal, remote, registry, audit, learn; see --help). Run slug: {run_dir.name}\n"
            "Everything under '# knowledge/' below is mandatory and overrides defaults.\n" + knowledge(run_dir, cfg))


def knowledge(run_dir: Path, cfg: dict) -> str:
    """Shared tiers come from the snapshot the server wrote before launching this job (the job itself cannot read
    the shared knowledge base); run-local knowledge/*.md is appended. Without a snapshot (CLI use) select directly."""
    snap = run_dir / ".bonrs/knowledge.md"
    if not snap.exists(): return kb.select(cfg, run_dir)
    local = kb.select({}, run_dir, root=run_dir / ".bonrs/empty") if (run_dir / "knowledge").exists() else ""
    return snap.read_text(errors="ignore") + local


def run_stage(run_dir: Path, stage: str, cfg: dict, extra: str = "") -> dict:
    prompt = (PROMPTS / f"{stage}.md").read_text() + ("\n\n" + extra if extra else "")
    cmd = [os.environ.get("BONRS_CLAUDE_BIN", "claude"), "-p", prompt, "--append-system-prompt", system_prompt(run_dir, cfg), "--allowedTools", TOOLS,
           "--permission-mode", "bypassPermissions", "--output-format", "stream-json", "--verbose", "--no-session-persistence", "--add-dir", str(ROOT)]
    if cfg.get("model"): cmd += ["--model", cfg["model"]]
    if cfg.get("max_budget_usd"): cmd += ["--max-budget-usd", str(cfg["max_budget_usd"])]
    log = run_dir / "logs"; log.mkdir(exist_ok=True)
    t0, result = time.time(), {"is_error": True, "result": ""}
    with open(log / f"{stage}.jsonl", "a") as fh, open(log / f"{stage}.stderr.txt", "w") as eh:
        fh.write(json.dumps({"type": "bonrs_attempt", "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")  # every attempt stays in the log
        proc = subprocess.Popen(cmd, cwd=run_dir, stdout=subprocess.PIPE, stderr=eh, text=True, start_new_session=True,
                                env={**os.environ, "BONRS_RUN": str(run_dir), "BONRS_ROOT": str(ROOT)})
        for line in proc.stdout:
            fh.write(line)
            try: ev = json.loads(line)
            except json.JSONDecodeError: continue
            if isinstance(ev, dict) and ev.get("type") == "result": result = ev; break  # final event: a leftover background child must not hold the stage open
        try: proc.wait(timeout=30)
        except subprocess.TimeoutExpired: pass
        try: os.killpg(proc.pid, signal.SIGTERM)  # end whatever the agent left running in its process group
        except (ProcessLookupError, PermissionError): pass
        proc.stdout.close(); proc.wait()
    if proc.returncode != 0 and result.get("is_error", True):
        result = {"is_error": True, "result": (log / f"{stage}.stderr.txt").read_text()[-2000:], **{k: v for k, v in result.items() if k != "is_error"}}
    result["seconds"] = round(time.time() - t0)
    return result

"""bonrs: idea -> journal-ready paper, autonomously, with Claude as the agent."""
import os, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("BONRS_DATA", ROOT))        # docker: /data volume
PROMPTS = ROOT / "prompts"
RUNS = DATA / "runs"
KNOWLEDGE = DATA / "knowledge"
if not KNOWLEDGE.exists() and (ROOT / "knowledge").exists():  # first start on a fresh volume: seed the shared knowledge base
    shutil.copytree(ROOT / "knowledge", KNOWLEDGE)
RUNS.mkdir(parents=True, exist_ok=True)

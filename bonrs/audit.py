"""Paper integrity audit = definition of done (generic verify-phm + writing-audit + VerifiedRegistry + claim ledger).

LaTeX contract (preamble):
    \\newcommand{\\ph}[1]{#1}        provisional number (invented) — must be gone before submission
    \\newcommand{\\phm}[2][]{#2}     measured: \\phm[exp/results/x.json:runs.main.acc]{87.3}
    \\newcommand{\\prov}[2]{#2}      sentence provenance: \\prov{claim-id}{sentence}
Markdown (docx route) uses {ph:v}, {phm:file:key:v}, {prov:id: sentence}.
"""
import json, re
from pathlib import Path
import yaml
from . import registry as R

OVERCLAIM = re.compile(r"state[- ]of[- ]the[- ]art|\bSOTA\b|\blossless\b|first (ever|study|work) to|outperforms all|"
                       r"\bnovel\b|\bsignificant(ly)?\b(?![^.]{0,40}(p\s*[<=]|CI|confidence))|unprecedented|paradigm[- ]shift|very unique|\bprove[sd]?\b", re.I)
PLACEHOLDER = re.compile(r"\\lipsum|\\blindtext|\bTODO\b|\bTBD\b|\bXXX\b|placeholder|\?\?|\[CLAIM NEEDS EVIDENCE\]|\[CITATION NEEDED\]", re.I)
STRONG = {"shows": 3, "demonstrates": 3, "establishes": 3, "confirms": 3, "proves": 4, "suggests": 2, "indicates": 2,
          "is consistent with": 1, "may": 1, "appears": 1}
LEVEL = {"shows": 3, "suggests": 2, "consistent_with": 1}
NUM = re.compile(r"(?<![\w.\\-])[-+−]?\d+(?:[.,]\d+)?(?=\s*(?:%|\\%)?)(?![\w.-]*[}\]])")


def _docs(paper: Path) -> dict[str, str]:
    return {str(p.relative_to(paper)): p.read_text(errors="ignore") for p in list(paper.rglob("*.tex")) + list(paper.glob("*.md"))
            if p.name not in ("outline.md", "wordcount.md", "response_letter.md", "claims.yaml")}


def _lookup(run_dir: Path, ref: str):
    f, _, key = ref.partition(":")
    data = json.loads((run_dir / f).read_text())
    for part in key.split(".") if key else []:
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def _same(written: str, actual) -> bool:
    w = written.replace("$", "").replace("\\%", "").replace("+", "").replace("−", "-").strip()
    try:
        dec = len(w.split(".")[1]) if "." in w else 0
        return abs(float(actual) - float(w)) <= 0.5 * 10 ** -dec + 1e-9 or abs(float(actual) * 100 - float(w)) <= 0.5 * 10 ** -dec
    except (ValueError, TypeError):
        return str(actual).strip() == w


def _sections(t: str) -> dict[str, str]:
    """Split LaTeX/Markdown into named sections (lowercase title -> text)."""
    out, cur = {}, "preamble"
    for line in t.splitlines():
        m = re.match(r"\\(?:sub)?section\*?\{([^}]*)\}|^#{1,3}\s+(.+)$|\\begin\{abstract\}", line)
        if m: cur = (m.group(1) or m.group(2) or "abstract").lower()
        out[cur] = out.get(cur, "") + line + "\n"
    return out


def audit(run_dir: Path, final=False) -> list[str]:
    paper = run_dir / "paper"; fails = []
    docs = _docs(paper)
    if not docs: return ["no paper/main.tex or paper/main.md"]
    body = "\n".join(docs.values())
    # 1 build log
    log = paper / "main.log"
    if log.exists():
        u = len(re.findall(r"undefined (citation|reference)", log.read_text(errors="ignore"), re.I))
        if u: fails.append(f"{u} undefined citation/reference warnings in main.log")
    elif any(f.endswith(".tex") for f in docs): fails.append("no paper/main.log — compile with latexmk -pdf main.tex")
    # 2 placeholders, \ph, \phm
    for f, t in docs.items():
        for m in PLACEHOLDER.finditer(t): fails.append(f"{f}: placeholder '{m.group(0)}'")
        ph = re.findall(r"\\ph\{([^}]*)\}|\{ph:([^}]*)\}", t)
        if ph and final: fails.append(f"{f}: {len(ph)} provisional numbers still present")
        for src, val in re.findall(r"\\phm\[([^\]]+)\]\{([^}]*)\}", t) + re.findall(r"\{phm:([^:}]+:[^:}]+):([^}]*)\}", t):
            try:
                actual = _lookup(run_dir, src)
                if not _same(val, actual): fails.append(f"{f}: \\phm {val} != {actual} ({src})")
            except Exception as e: fails.append(f"{f}: \\phm[{src}] unresolvable: {type(e).__name__}")
    # 3 numbers in Abstract/Results must exist in registry
    regf = run_dir / "exp/results/registry.json"
    if regf.exists():
        vals = R.values(json.loads(regf.read_text()))
        for f, t in docs.items():
            for name, sec in _sections(t).items():
                if not re.search(r"abstract|result", name): continue
                clean = re.sub(r"\\(?:phm|ph|cite[tp]?|ref|Cref|label|includegraphics)(\[[^\]]*\])?\{[^}]*\}|\\begin\{tabular\}.*?\\end\{tabular\}|\$[^$]*\$|\{phm:[^}]*\}", " ", sec, flags=re.S)
                for n in set(NUM.findall(clean)):
                    if re.fullmatch(r"[12]\d{3}|[0-9]|1[0-9]|20", n): continue  # years, small counts
                    if not R.matches(n, vals): fails.append(f"{f} [{name}]: number {n} not in exp/results/registry.json")
    # 4 citations
    bib = "".join(p.read_text(errors="ignore") for p in paper.glob("*.bib"))
    keys = set(re.findall(r"@\w+\{([^,]+),", bib))
    cited = set(k.strip() for m in re.findall(r"\\cite[tp]?\*?(?:\[[^\]]*\])*\{([^}]*)\}|\[@([^\]]+)\]", body) for grp in m for k in grp.split(",") if k.strip().lstrip("@"))
    cited = {k.lstrip("@") for k in cited}
    for k in sorted(cited - keys): fails.append(f"cited key not in .bib: {k}")
    known = (run_dir / "lit/papers.jsonl").read_text().lower() if (run_dir / "lit/papers.jsonl").exists() else ""
    known += "".join(p.read_text(errors="ignore").lower() for p in (run_dir / "lit/uploads").glob("*.txt")) if (run_dir / "lit/uploads").exists() else ""
    for entry in re.split(r"(?=@\w+\{)", bib):
        m = re.match(r"@\w+\{([^,]+),", entry)
        if not m: continue
        if not re.search(r"doi\s*=|eprint\s*=|arxiv|url\s*=", entry, re.I): fails.append(f"bib entry without doi/arxiv/url: {m.group(1)}")
        tm = re.search(r"title\s*=\s*[{\"](.+?)[}\"]\s*,", entry, re.S)
        if known and tm:
            t = re.sub(r"[{}]", "", tm.group(1)); t = re.sub(r"\W+", " ", t).strip().lower()[:50]
            if t and t not in re.sub(r"\W+", " ", known) and t not in known:
                fails.append(f"bib title not found in lit corpus (possible hallucination): {t}")
    # 5 overclaims / style
    for f, t in docs.items():
        for m in OVERCLAIM.finditer(t): fails.append(f"{f}: overclaim/dead-wood '{m.group(0)}'")
        if re.search(r"\\cite\{", t): fails.append(f"{f}: bare \\cite{{}} (use \\citep/\\citet)")
    # 6 claim ledger
    cl = paper / "claims.yaml"
    if cl.exists():
        try: claims = yaml.safe_load(cl.read_text()) or []
        except yaml.YAMLError as e: claims = []; fails.append(f"claims.yaml invalid: {e}")
        for c in claims:
            ev, cid = str(c.get("evidence", "")), c.get("id", "?")
            if ":" in ev and not ev.startswith("fig"):
                try: _lookup(run_dir, ev)
                except Exception: fails.append(f"claim {cid}: evidence {ev} unresolvable")
            elif ev and not ev.startswith("fig") and ev not in keys: fails.append(f"claim {cid}: evidence '{ev}' is neither file:key nor bib key nor fig")
            if c.get("text") and c["text"][:40] not in body: fails.append(f"claim {cid}: text not found in paper")
            lvl = LEVEL.get(str(c.get("strength", "suggests")), 2)
            for verb, s in STRONG.items():
                if s > lvl and c.get("text") and re.search(rf"\b{verb}\b", c["text"]): fails.append(f"claim {cid}: verb '{verb}' stronger than allowed '{c.get('strength')}'")
        ids = {c.get("id") for c in claims}
        for pid in set(re.findall(r"\\prov\{([^}]*)\}|\{prov:([^:}]*):", body)):
            pid = pid[0] or pid[1]
            if pid not in ids: fails.append(f"\\prov{{{pid}}} has no entry in claims.yaml")
    elif final: fails.append("paper/claims.yaml missing")
    return fails


def cli(run_dir: Path, final: bool) -> int:
    fails = audit(run_dir, final)
    for x in fails: print("FAIL", x)
    print(f"{'OK' if not fails else 'FAIL'} — {len(fails)} issues")
    return 1 if fails else 0

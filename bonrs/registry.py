"""VerifiedRegistry: flatten every numeric leaf under exp/results/*.json into file:key -> value."""
import json, re
from pathlib import Path


def _flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items(): yield from _flatten(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj): yield from _flatten(v, f"{prefix}.{i}" if prefix else str(i))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield prefix, obj


def build(run_dir: Path) -> dict:
    res = run_dir / "exp" / "results"; reg = {}
    for f in sorted(res.glob("*.json")):
        if f.name == "registry.json": continue
        try: data = json.loads(f.read_text())
        except json.JSONDecodeError: continue
        for k, v in _flatten(data): reg[f"exp/results/{f.name}:{k}"] = v
    tsv = run_dir / "exp" / "results.tsv"
    if tsv.exists():
        for i, line in enumerate(tsv.read_text().splitlines()[1:]):
            cells = line.split("\t")
            if len(cells) > 1:
                try: reg[f"exp/results.tsv:{i}.metric"] = float(cells[1])
                except ValueError: pass
    (res / "registry.json").write_text(json.dumps(reg, indent=1))
    return reg


def values(reg: dict) -> list[float]:
    return [float(v) for v in reg.values()]


def matches(written: str, reg_values: list[float]) -> bool:
    """A written numeral matches if some registry value rounds to it (or ×100 for %)."""
    w = written.replace(",", "").replace("+", "").replace("−", "-")
    try: x = float(w)
    except ValueError: return False
    dec = len(w.split(".")[1]) if "." in w else 0
    for v in reg_values:
        for cand in (v, v * 100, v / 100):
            if abs(cand - x) <= 0.5 * 10 ** -dec + 1e-9: return True
    return False


def table(reg: dict, keys: list[str], headers: list[str] | None = None, fmt="latex") -> str:
    rows = [(k, reg[k]) for k in keys if k in reg]
    if fmt == "latex":
        body = "\n".join(f"{k.split(':')[-1]} & \\phm[{k}]{{{v}}} \\\\" for k, v in rows)
        return "\\begin{tabular}{lr}\n\\toprule\nKey & Value \\\\\n\\midrule\n" + body + "\n\\bottomrule\n\\end{tabular}"
    return "| Key | Value |\n|---|---|\n" + "\n".join(f"| {k.split(':')[-1]} | {{phm:{k}:{v}}} |" for k, v in rows)

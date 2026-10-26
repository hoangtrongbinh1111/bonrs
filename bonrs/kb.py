"""Knowledge base: tiered markdown skills with frontmatter, selected per run."""
import json, math, re, datetime
from pathlib import Path
import yaml
from . import KNOWLEDGE, RUNS

TIERS = ["00-general", "10-domain", "20-article-type", "30-journal", "40-experience", "50-user"]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:60]


def parse_text(t: str, stem: str = "skill") -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", t, re.S)
    if not m: return {"name": stem, "status": "active"}, t
    try: meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError: meta = None
    meta = {str(k): v for k, v in meta.items()} if isinstance(meta, dict) else {}  # frontmatter that is not a mapping is ignored
    meta.setdefault("name", stem); meta.setdefault("status", "active")
    return meta, m.group(2)


def parse(path: Path) -> tuple[dict, str]:
    return parse_text(path.read_text(errors="ignore")[:2_000_000], path.stem)


def _files(root: Path):
    for p in sorted(root.rglob("*.md")):
        if "inbox" in p.parts or p.is_symlink() or not p.is_file(): continue
        try: yield p, *parse(p)
        except (OSError, ValueError): continue  # one unreadable file must not break the whole knowledge base


def index(root: Path = KNOWLEDGE) -> list[dict]:
    rows = []
    for p, meta, body in _files(root):
        tier = next((t for t in TIERS if t in p.parts), None)
        rows.append({**meta, "path": str(p.relative_to(root)), "tier": tier, "chars": len(body)})
    (root / "INDEX.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False, default=str))
    return rows


def _f(v, d):
    try: f = float(v); return f if math.isfinite(f) else d
    except (TypeError, ValueError): return d


def _weight(meta: dict) -> float:
    sev = _f(meta.get("severity"), 2); conf = _f(meta.get("confidence"), 0.7)
    added = meta.get("added")
    try: age = (datetime.date.today() - datetime.date.fromisoformat(str(added)[:10])).days
    except (ValueError, TypeError): age = 0
    return sev * conf * math.exp(-math.log(2) * age / 30) if meta.get("level") == "experience" else sev * conf


def select(cfg: dict, run_dir: Path | None = None, limit: int = 60000, root: Path = KNOWLEDGE) -> str:
    """Return the knowledge text to inject for this run."""
    dom, art = cfg.get("domain", "other"), cfg.get("article_type", "research")
    jslug, uid = slug(str(cfg.get("target_journal") or "")), str(cfg.get("user_id") or "")
    picked = []
    for p, meta, body in _files(root):
        if meta.get("status") != "active": continue
        parts = p.relative_to(root).parts; tier = parts[0]
        ok = (tier == "00-general" or
              (tier == "10-domain" and (meta.get("domain") == dom or dom in parts)) or
              (tier == "20-article-type" and (meta.get("article_type") in (None, art) or art in parts or p.name == "README.md")) or
              (tier == "30-journal" and (jslug and (jslug in p.stem or slug(str(meta.get("journal", ""))) == jslug))) or
              (tier == "40-experience" and (not meta.get("domain") or meta.get("domain") == dom)) or
              (tier == "50-user" and uid and uid in parts))
        if ok: picked.append((0 if tier != "40-experience" else 1, -_weight(meta), p.relative_to(root), body))
    if run_dir and (run_dir / "knowledge").exists():  # run-local skills (member-created); only read by the run's own job
        for p in sorted((run_dir / "knowledge").glob("*.md")):
            if p.is_symlink() or not p.is_file(): continue
            meta, body = parse(p)
            if meta.get("status", "active") == "active": picked.append((0, 0, Path("run") / p.name, body))
    picked.sort(key=lambda x: (x[0], x[1]))
    out, n = [], 0
    for _, _, rel, body in picked:
        chunk = f"\n\n# knowledge/{rel}\n{body.strip()}"
        if n + len(chunk) > limit: break
        out.append(chunk); n += len(chunk)
    return "".join(out)


LEVELS = {"general": "00-general", "domain": "10-domain", "article_type": "20-article-type", "journal": "30-journal",
          "experience": "40-experience", "user": "50-user"}


def learn(text: str, level="experience", category="WRITING", severity=2, domain=None, journal=None, source=None, out: Path | None = None) -> Path:
    """Propose a lesson. It is written as a draft into `out` (the run's proposals/ folder when called by an agent);
    the server copies it into the review queue. Nothing becomes an active shared skill without an admin."""
    if level not in LEVELS: raise ValueError(f"level must be one of {sorted(LEVELS)}")
    out = out or (KNOWLEDGE / "inbox/drafts"); out.mkdir(parents=True, exist_ok=True)
    name = slug(text[:50]) or "lesson"; p = out / f"{datetime.date.today().isoformat()}-{name}.md"
    meta = {"name": name, "level": level, "category": category, "severity": severity, "added": datetime.date.today().isoformat(), "status": "draft"}
    if domain: meta["domain"] = domain
    if journal: meta["journal"] = journal
    if source: meta["source"] = source
    p.write_text("---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n" + text.strip()[:6000] + "\n")
    return p


# ---------- ingest / crawl / review queue ----------
import hashlib, html as _html, os, shutil, subprocess, tempfile, zipfile
import requests
from . import PROMPTS

UA = {"User-Agent": "Mozilla/5.0 (bonrs knowledge crawler)"}


MAX_FETCH = 30 * 1024 * 1024


def _public_url(url: str) -> str:
    """Refuse URLs that resolve to private, loopback, link-local or otherwise non-public addresses (SSRF)."""
    import ipaddress, socket
    from urllib.parse import urlsplit
    u = urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname: raise ValueError("only http(s) URLs")
    if u.port not in (None, 80, 443): raise ValueError("only ports 80/443")
    for info in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP):
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast: raise ValueError(f"address not allowed: {ip}")
    return url


def fetch(url: str) -> requests.Response:
    """GET with SSRF checks on every redirect hop and a size cap."""
    for _ in range(5):
        r = requests.get(_public_url(url), headers=UA, timeout=(10, 60), stream=True, allow_redirects=False)
        if r.is_redirect: url = requests.compat.urljoin(url, r.headers.get("location", "")); r.close(); continue
        r.raise_for_status(); buf = bytearray()
        for chunk in r.iter_content(65536):
            buf += chunk
            if len(buf) > MAX_FETCH: r.close(); raise ValueError("document too large")
        r._content = bytes(buf); return r
    raise ValueError("too many redirects")


def raw_text(src: str, work: Path | None = None) -> str:
    """Text from a URL or a local file (pdf/docx/html/md/txt)."""
    if src.startswith(("http://", "https://")):
        r = fetch(src)
        if r.content[:4] == b"%PDF":
            tmp = (work or Path(tempfile.mkdtemp())) / "_dl.pdf"; tmp.write_bytes(r.content); return raw_text(str(tmp), work)
        t = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", r.text)
        return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))).strip()
    p = Path(src); suf = p.suffix.lower()
    if suf == ".pdf": return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, timeout=300).stdout
    if suf == ".docx":
        with zipfile.ZipFile(p) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > 50 * 1024 * 1024: raise ValueError("docx too large")
            x = z.read(info).decode("utf8", "ignore")
        return _html.unescape(re.sub(r"<[^>]+>", " ", x.replace("</w:p>", "\n")))
    if suf in (".html", ".htm"): return _html.unescape(re.sub(r"<[^>]+>", " ", p.read_text(errors="ignore")))
    return p.read_text(errors="ignore")


def ingest(src: str, user: str = "admin", hint: str = "", work: Path | None = None, skip_sha: str = "") -> list[Path]:
    """Distill a document into draft skills inside `work` (work/raw.txt, work/drafts/). Runs as the submitter's
    sandboxed uid; the server imports work/drafts afterwards. The agent sees only this folder."""
    work = Path(work or tempfile.mkdtemp()); (work / "drafts").mkdir(parents=True, exist_ok=True)
    text = raw_text(src, work)
    if len(text.strip()) < 200: raise ValueError(f"too little text extracted from {src}")
    sha = hashlib.sha256(text.encode()).hexdigest()
    (work / "raw.txt").write_text(f"SOURCE: {src}\nSUBMITTED_BY: {user}\nHINT: {hint}\nSHA: {sha}\n\n{text[:200000]}")
    if skip_sha and sha == skip_sha: print("unchanged since last crawl: nothing to distill"); return []
    prompt = (PROMPTS / "kb_distill.md").read_text().replace("{RAW}", "raw.txt").replace("{DRAFTS}", "drafts").replace("{USER}", user)
    subprocess.run([os.environ.get("BONRS_CLAUDE_BIN", "claude"), "-p", prompt, "--allowedTools", "Read,Write,Glob,Grep",
                    "--permission-mode", "acceptEdits", "--output-format", "json", "--no-session-persistence",
                    "--model", os.environ.get("BONRS_KB_MODEL", "claude-opus-5-5")], cwd=work, capture_output=True, text=True, timeout=1800)
    return sorted((work / "drafts").glob("*.md"))


SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}\.md$")
META_KEYS = ("name", "level", "domain", "article_type", "journal", "tags", "source", "source_date", "added", "category", "severity", "confidence", "supersedes")


def clean_meta(meta: dict) -> dict:
    """Keep only known fields with sane types; the rest of a draft's frontmatter is attacker-controlled text."""
    out = {}
    for k in META_KEYS:
        v = meta.get(k)
        if v is None: continue
        if k == "tags": out[k] = [str(x)[:40] for x in (v if isinstance(v, list) else [v])][:10]
        elif k == "severity": out[k] = int(min(3, max(1, _f(v, 2))))
        elif k == "confidence": out[k] = round(min(1.0, max(0.0, _f(v, 0.5))), 2)
        elif k == "level": out[k] = v if v in LEVELS else "general"
        else: out[k] = str(v)[:200]
    return out


def queue_draft(meta: dict, body: str, base_name: str, submitted_by: str, uid: int | None, origin: str, root: Path = KNOWLEDGE) -> str:
    """Put one draft into the admin review queue. Provenance fields are set here, never taken from the draft."""
    q = root / "inbox/drafts"; q.mkdir(parents=True, exist_ok=True)
    meta = clean_meta(meta)
    if meta.get("level") == "user": meta["user_id"] = int(uid or 0)
    meta.update({"status": "draft", "submitted_by": submitted_by, "origin": origin})
    base = slug(base_name) or "skill"; name = f"{base}.md"; i = 2
    while (q / name).exists(): name = f"{base}-{i}.md"; i += 1
    (q / name).write_text("---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n" + body.strip()[:20000] + "\n")
    return name


def import_drafts(src_dir: Path, submitted_by: str, uid: int | None, origin: str, root: Path = KNOWLEDGE, limit: int = 20) -> list[str]:
    """Queue the *.md a job produced in src_dir (a folder the job could write). Returns queue file names."""
    from . import safeio
    names = []
    if not src_dir.is_dir() or src_dir.is_symlink(): return names
    for rel, size, _ in sorted(safeio.listing(src_dir, max_files=200)):
        if "/" in rel or not rel.endswith(".md") or size > 200_000 or len(names) >= limit: continue
        meta, body = parse_text(safeio.read_text(src_dir, rel) or "", Path(rel).stem)
        names.append(queue_draft(meta, body, Path(rel).stem, submitted_by, uid, origin, root))
    return names


def drafts(root: Path = KNOWLEDGE) -> list[dict]:
    out = []
    for p in sorted((root / "inbox/drafts").glob("*.md")) if (root / "inbox/drafts").exists() else []:
        if p.is_symlink(): continue
        meta, body = parse(p)
        try: tgt = str(target_path(meta, p.name, root).relative_to(root))
        except ValueError: tgt = None
        out.append({**meta, "file": p.name, "body": body, "target": tgt})
    return out


def target_path(meta: dict, name: str, root: Path = KNOWLEDGE) -> Path:
    """Where an approved draft goes. Every component is slugged or numeric, and the result must stay under root."""
    if not SAFE_NAME.match(name): raise ValueError("bad draft name")
    lvl = meta.get("level", "general")
    if lvl == "domain": d = root / "10-domain" / (slug(str(meta.get("domain") or "other")) or "other") / name
    elif lvl == "article_type": d = root / "20-article-type" / name
    elif lvl == "journal": d = root / "30-journal" / f"{slug(str(meta.get('journal') or name[:-3])) or 'journal'}.md"
    elif lvl == "experience": d = root / "40-experience" / name
    elif lvl == "user":
        uid = meta.get("user_id")
        if isinstance(uid, bool) or not re.fullmatch(r"\d{1,9}", str(uid)): raise ValueError("user_id must be a number")
        d = root / "50-user" / str(int(uid)) / name
    else: d = root / "00-general" / name
    d.resolve().relative_to(root.resolve())  # raises ValueError if anything escaped
    return d


def approve(file: str, edits: dict | None = None, body: str | None = None, root: Path = KNOWLEDGE) -> Path:
    src = root / "inbox/drafts" / Path(file).name
    if src.is_symlink() or not src.is_file(): raise ValueError("no such draft")
    meta, old = parse(src)
    keep = {k: meta[k] for k in ("user_id", "submitted_by", "origin") if k in meta}
    meta = {**clean_meta({**meta, **(edits or {})}), **keep, "status": "active"}
    if meta.get("level") == "user" and "user_id" in (edits or {}): meta["user_id"] = edits["user_id"]
    dst = target_path(meta, src.name, root); dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and meta.get("level") == "journal":  # merge journal rules into the existing journal file
        m0, b0 = parse(dst); text = b0.rstrip() + "\n\n" + (body or old).strip() + "\n"; meta = {**m0, **meta}
    else: text = (body or old).strip() + "\n"
    dst.write_text("---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n" + text)
    src.unlink(); index(root); return dst


def reject(file: str, reason: str = "", root: Path = KNOWLEDGE):
    src = root / "inbox/drafts" / Path(file).name
    if src.is_symlink() or not src.is_file(): raise ValueError("no such draft")
    dst = root / "inbox/rejected" / src.name
    dst.parent.mkdir(parents=True, exist_ok=True); shutil.move(src, dst)
    with dst.open("a") as fh: fh.write(f"\n<!-- rejected: {str(reason)[:500]} -->\n")


def sources(root: Path = KNOWLEDGE) -> list[dict]:
    """Enabled http(s) crawl sources from sources.yaml (local paths are not allowed)."""
    try: srcs = (yaml.safe_load((root / "sources.yaml").read_text()) or {}).get("sources", [])
    except (OSError, yaml.YAMLError, AttributeError): return []
    return [s for s in srcs if isinstance(s, dict) and s.get("enabled") is not False and str(s.get("url", "")).startswith(("http://", "https://"))]

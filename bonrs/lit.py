"""Free literature sources with polite rate limits + sqlite cache. Paywalled -> ask user to upload."""
import json, os, re, sqlite3, subprocess, threading, time, xml.etree.ElementTree as ET
from pathlib import Path
import requests
from . import ROOT, DATA

EMAIL = os.environ.get("BONRS_EMAIL", "bonrs@example.org")
UA = {"User-Agent": f"bonrs/0.2 (mailto:{EMAIL})"}
OA_KEY = os.environ.get("OPENALEX_API_KEY")  # local CLI use; jobs get no keys and go through the server's data proxy
S2_KEY = os.environ.get("S2_API_KEY")
PROXY, JOB = os.environ.get("BONRS_DATA_PROXY"), os.environ.get("BONRS_JOB_TOKEN")
_VIA = {"api.openalex.org": "openalex", "api.semanticscholar.org": "s2"}


def _route(url: str, headers: dict | None = None) -> tuple[str, dict]:
    """Inside a job, OpenAlex/Semantic Scholar calls go to the server, which adds the server's API keys."""
    host = url.split("/")[2] if "://" in url else ""
    if PROXY and JOB and host in _VIA:
        return f"{PROXY}/{_VIA[host]}/" + url.split("/", 3)[3], {**(headers or {}), "x-bonrs-job": JOB}
    return url, headers or {}
NS = {"a": "http://www.w3.org/2005/Atom"}
_RATE = {"export.arxiv.org": 3.1, "api.crossref.org": 0.4, "api.semanticscholar.org": 1.1, "api.openalex.org": 0.1,
         "api.unpaywall.org": 0.1, "www.ebi.ac.uk": 0.2}
_last, _lock = {}, threading.Lock()
_db = sqlite3.connect(os.environ.get("BONRS_CACHE") or str(DATA / "cache.sqlite"), check_same_thread=False)  # per-user cache in jobs
_db.execute("CREATE TABLE IF NOT EXISTS http(k TEXT PRIMARY KEY, t REAL, body TEXT)")


def get(url: str, params=None, ttl=30 * 86400, headers=None) -> str | None:
    """Rate-limited, cached GET. Returns text or None."""
    key = url + "?" + json.dumps(params or {}, sort_keys=True)
    row = _db.execute("SELECT t, body FROM http WHERE k=?", (key,)).fetchone()
    if row and time.time() - row[0] < ttl: return row[1]
    dom = url.split("/")[2]
    with _lock:
        wait = _RATE.get(dom, 0.2) - (time.time() - _last.get(dom, 0))
        if wait > 0: time.sleep(wait)
        _last[dom] = time.time()
    for attempt in range(3):
        try:
            u, h = _route(url, headers)
            r = requests.get(u, params=params, headers={**UA, **h}, timeout=60)
            if r.status_code == 429: time.sleep(5 * (attempt + 1)); continue
            if not r.ok: return None
            _db.execute("INSERT OR REPLACE INTO http VALUES (?,?,?)", (key, time.time(), r.text)); _db.commit()
            return r.text
        except requests.RequestException:
            time.sleep(2)
    return None


def arxiv(query: str, n=25) -> list[dict]:
    t = get("http://export.arxiv.org/api/query", {"search_query": query if query.startswith(("ti:", "au:", "abs:")) else f"all:{query}", "max_results": n, "sortBy": "relevance"})
    out = []
    for e in (ET.fromstring(t).findall("a:entry", NS) if t else []):
        aid = e.find("a:id", NS).text.rsplit("/", 1)[-1]
        out.append({"id": f"arxiv:{aid}", "title": " ".join(e.find("a:title", NS).text.split()), "year": e.find("a:published", NS).text[:4],
                    "authors": [a.find("a:name", NS).text for a in e.findall("a:author", NS)][:6],
                    "abstract": " ".join(e.find("a:summary", NS).text.split()), "pdf": f"https://arxiv.org/pdf/{aid}", "oa": True, "source": "arXiv",
                    "doi": next((l.get("href") for l in e.findall("a:link", NS) if "doi.org" in (l.get("href") or "")), None)})
    return out


def openalex(query: str, n=25, oa_only=False, issn=None, since=None, extra_filter=None) -> list[dict]:
    flt = ["type:article"]
    if oa_only: flt.append("is_oa:true")
    if issn: flt.append(f"primary_location.source.issn:{issn}")
    if since: flt.append(f"from_publication_date:{since}")
    if extra_filter: flt.append(extra_filter)
    params = {"per-page": n, "filter": ",".join(flt), "sort": "cited_by_count:desc" if issn and not query else "relevance_score:desc",
              "select": "id,doi,title,publication_year,cited_by_count,authorships,primary_location,best_oa_location,abstract_inverted_index,open_access,is_retracted"}
    if query: params["search"] = query
    if OA_KEY: params["api_key"] = OA_KEY
    t = get("https://api.openalex.org/works", params); out = []
    for w in (json.loads(t).get("results", []) if t else []):
        loc = w.get("best_oa_location") or {}; inv = w.get("abstract_inverted_index") or {}
        words = sorted((pos, tok) for tok, ps in inv.items() for pos in ps)
        out.append({"id": w["id"].rsplit("/", 1)[-1], "doi": (w.get("doi") or "").replace("https://doi.org/", "") or None, "title": w.get("title"),
                    "year": w.get("publication_year"), "cited": w.get("cited_by_count"),
                    "authors": [a["author"]["display_name"] for a in w.get("authorships", [])][:6],
                    "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name"),
                    "abstract": " ".join(tok for _, tok in words), "pdf": loc.get("pdf_url"), "landing": loc.get("landing_page_url"),
                    "oa": bool((w.get("open_access") or {}).get("is_oa")), "retracted": w.get("is_retracted"), "source": "OpenAlex"})
    return out


def crossref(query: str, n=20) -> list[dict]:
    t = get("https://api.crossref.org/works", {"query.bibliographic": query, "rows": n, "mailto": EMAIL,
                                              "select": "DOI,title,author,issued,container-title,abstract,is-referenced-by-count"})
    out = []
    for it in (json.loads(t)["message"]["items"] if t else []):
        out.append({"id": "doi:" + it["DOI"], "doi": it["DOI"], "title": (it.get("title") or [""])[0],
                    "year": (it.get("issued", {}).get("date-parts") or [[None]])[0][0], "cited": it.get("is-referenced-by-count"),
                    "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in it.get("author", [])][:6],
                    "venue": (it.get("container-title") or [None])[0], "abstract": re.sub(r"<[^>]+>", "", it.get("abstract", "")),
                    "pdf": None, "oa": None, "source": "Crossref"})
    return out


def europepmc(query: str, n=25) -> list[dict]:
    t = get("https://www.ebi.ac.uk/europepmc/webservices/rest/search", {"query": query, "format": "json", "pageSize": n, "resultType": "lite"})
    out = []
    for r in (json.loads(t).get("resultList", {}).get("result", []) if t else []):
        pmcid = r.get("pmcid")
        out.append({"id": r.get("id"), "doi": r.get("doi"), "title": r.get("title"), "year": r.get("pubYear"), "cited": r.get("citedByCount"),
                    "authors": (r.get("authorString") or "").split(", ")[:6], "venue": r.get("journalTitle"), "abstract": "",
                    "pdf": None, "pmcid": pmcid, "oa": r.get("isOpenAccess") == "Y", "source": "EuropePMC",
                    "fulltext_xml": f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML" if pmcid else None})
    return out


def unpaywall(doi: str) -> str | None:
    t = get(f"https://api.unpaywall.org/v2/{doi}", {"email": EMAIL})
    return ((json.loads(t).get("best_oa_location") or {}).get("url_for_pdf") if t else None)


def s2_recommend(paper_ids: list[str], n=20) -> list[dict]:
    """Semantic Scholar recommendations from positive seeds (arXiv:ID or DOI:...)."""
    try:
        u, h = _route("https://api.semanticscholar.org/recommendations/v1/papers", {"x-api-key": S2_KEY} if S2_KEY else {})
        r = requests.post(u, params={"fields": "title,year,externalIds,abstract,openAccessPdf,citationCount", "limit": n},
                          json={"positivePaperIds": paper_ids[:20]}, headers={**UA, **h}, timeout=60)
        if not r.ok: return []
    except requests.RequestException: return []
    return [{"id": "s2:" + p["paperId"], "doi": (p.get("externalIds") or {}).get("DOI"), "title": p.get("title"), "year": p.get("year"),
             "cited": p.get("citationCount"), "authors": [], "abstract": p.get("abstract") or "", "pdf": (p.get("openAccessPdf") or {}).get("url"),
             "oa": bool(p.get("openAccessPdf")), "source": "S2-rec"} for p in r.json().get("recommendedPapers", [])]


def fetch_pdf(url: str, dest: Path) -> Path | None:
    try:
        r = requests.get(url, headers=UA, timeout=120, allow_redirects=True)
        if r.ok and r.content[:4] == b"%PDF": dest.write_bytes(r.content); return dest
    except requests.RequestException: pass
    return None


def pdf_text(pdf: Path) -> str:
    txt = pdf.with_suffix(".txt")
    if not txt.exists(): subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)], capture_output=True)
    return txt.read_text(errors="ignore") if txt.exists() else ""


def search(run_dir: Path, queries: list[str], n=20, biomed=False) -> Path:
    lit = run_dir / "lit"; (lit / "pdf").mkdir(parents=True, exist_ok=True)
    seen, papers = set(), []
    for q in queries:
        batch = arxiv(q, n) + openalex(q, n) + crossref(q, n // 2) + (europepmc(q, n) if biomed else [])
        for p in batch:
            key = re.sub(r"\W+", "", (p.get("title") or "").lower())[:80]
            if not key or key in seen: continue
            seen.add(key); papers.append(p)
    seeds = [p["id"] for p in papers if p["id"].startswith("arxiv:")][:10]
    for p in s2_recommend(seeds) if seeds else []:
        key = re.sub(r"\W+", "", (p.get("title") or "").lower())[:80]
        if key and key not in seen: seen.add(key); papers.append(p)
    for p in papers:
        if p.get("retracted"): p["note"] = "RETRACTED — do not cite as evidence"
        if not p.get("pdf") and p.get("doi"): p["pdf"] = unpaywall(p["doi"])
        if p.get("pdf"):
            f = fetch_pdf(p["pdf"], lit / "pdf" / (re.sub(r"\W+", "_", p["id"]) + ".pdf"))
            p["local_pdf"] = str(f) if f else None
            if f: p["fulltext_chars"] = len(pdf_text(f))
        elif p.get("fulltext_xml"):
            x = get(p["fulltext_xml"], ttl=365 * 86400)
            if x:
                tf = lit / "pdf" / (re.sub(r"\W+", "_", p["id"]) + ".txt"); tf.write_text(re.sub(r"<[^>]+>", " ", x))
                p["local_pdf"] = str(tf); p["fulltext_chars"] = tf.stat().st_size
    (lit / "papers.jsonl").write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in papers))
    needs = [p for p in papers if not p.get("local_pdf")]
    (lit / "NEED_UPLOAD.md").write_text("# Not downloadable (paywalled or no OA copy). Upload PDFs via the web UI or `bonrs upload`.\n\n" +
                                        "\n".join(f"- [{p['id']}] {p.get('title')} ({p.get('year')}) {p.get('doi') or ''}" for p in needs))
    print(f"{len(papers)} papers, {len(papers) - len(needs)} with fulltext, {len(needs)} need upload")
    return lit / "papers.jsonl"

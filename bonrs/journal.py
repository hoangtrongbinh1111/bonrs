"""Target-journal profile: OpenAlex source + DOAJ + recent accepted OA papers (shape + LLM-marker vocabulary baseline)."""
import json, re, statistics
from collections import Counter
from pathlib import Path
from .lit import get, openalex, arxiv, fetch_pdf, pdf_text, unpaywall, OA_KEY

SECTION_RE = re.compile(r"^\s*(\d+\.?\s+)?(Abstract|Introduction|Related Work|Background|Literature Review|Theoretical Background|"
                        r"Methods?|Methodology|Materials and Methods|Data|Experiments?|Results?|Discussion|Results and Discussion|"
                        r"Conclusions?|Limitations|Future Work|Implications|Acknowledg\w+|References)\s*$", re.I | re.M)
# LLM-marker vocabulary (Kobak et al. 2024, Liang et al. 2024); compared per 1000 words vs this journal's own papers
MARKERS = ["delve", "delves", "delving", "underscore", "underscores", "showcase", "showcasing", "intricate", "intricacies", "pivotal",
           "crucial", "meticulous", "meticulously", "notably", "comprehensive", "insights", "enhancing", "realm", "tapestry", "testament",
           "landscape", "interplay", "garner", "bolster", "boasts", "leverage", "multifaceted", "robust", "nuanced", "commendable",
           "innovative", "noteworthy", "invaluable", "seamless", "seamlessly", "holistic", "foster", "fostering", "additionally",
           "moreover", "furthermore"]


def marker_rates(text: str) -> dict:
    words = re.findall(r"[a-z]+", text.lower()); n = max(len(words), 1); c = Counter(words)
    return {m: round(1000 * c[m] / n, 3) for m in MARKERS}


def resolve(name: str) -> dict:
    params = {"search": name, "per-page": 5, "filter": "type:journal"}
    if OA_KEY: params["api_key"] = OA_KEY
    t = get("https://api.openalex.org/sources", params)
    res = json.loads(t)["results"] if t else []
    if not res: raise SystemExit(f"journal not found on OpenAlex: {name}")
    s = max(res[:2], key=lambda x: x.get("works_count") or 0) if len(res) > 1 and res[0]["display_name"].lower() != name.lower() else res[0]
    meta = {"openalex_id": s["id"], "name": s["display_name"], "issn_l": s.get("issn_l"), "issn": s.get("issn") or [],
            "publisher": s.get("host_organization_name"), "homepage": s.get("homepage_url"), "is_oa": s.get("is_oa"),
            "is_in_doaj": s.get("is_in_doaj"), "apc_usd": s.get("apc_usd"), "works_count": s.get("works_count"),
            "h_index": (s.get("summary_stats") or {}).get("h_index"), "two_year_citedness": (s.get("summary_stats") or {}).get("2yr_mean_citedness"),
            "topics": [t.get("display_name") for t in (s.get("topics") or [])[:5]],
            "alternatives": [r["display_name"] for r in res[1:4]]}
    if meta["issn_l"]:
        d = get(f"https://doaj.org/api/search/journals/issn:{meta['issn_l']}")
        hits = json.loads(d).get("results", []) if d else []
        if hits:
            b = hits[0].get("bibjson", {})
            meta["doaj"] = {"apc": b.get("apc"), "license": [l.get("type") for l in b.get("license", [])],
                            "review_process": (b.get("editorial") or {}).get("review_process"),
                            "publication_time_weeks": b.get("publication_time_weeks"),
                            "author_instructions": (b.get("ref") or {}).get("author_instructions"), "aims_scope": (b.get("ref") or {}).get("aims_scope")}
    return meta


def shape(text: str) -> dict:
    secs = [m.group(2).title() for m in SECTION_RE.finditer(text)]
    refs = text.rsplit("References", 1)[-1] if "References" in text else ""
    abs_m = re.search(r"Abstract\s*(.{200,3000}?)\n\s*\n", text, re.S | re.I)
    sents = [s for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text[:60000])) if 3 < len(s.split()) < 120]
    lens = [len(s.split()) for s in sents]
    return {"words": len(text.split()), "sections": secs,
            "n_refs": len(re.findall(r"^\s*\[?\d+[\].]\s", refs, re.M)) or len(re.findall(r"\(\d{4}[a-z]?\)\.", refs)),
            "abstract_words": len(abs_m.group(1).split()) if abs_m else None,
            "n_figures": len(set(re.findall(r"Fig(?:ure)?\.?\s*(\d+)", text))), "n_tables": len(set(re.findall(r"Table\s*(\d+)", text))),
            "sent_len_mean": round(statistics.mean(lens), 1) if lens else None, "sent_len_sd": round(statistics.pstdev(lens), 1) if lens else None,
            "em_dash_per_1000": round(1000 * text.count("—") / max(len(text.split()), 1), 2), "markers": marker_rates(text)}


def profile(run_dir: Path, name: str, topic: str = "", n=12, since="2023-01-01", want=8) -> Path:
    jd = run_dir / "journal"; (jd / "accepted").mkdir(parents=True, exist_ok=True)
    meta = resolve(name); issn = meta["issn_l"]
    # topic-near papers first, then any recent OA paper; hybrid journals have few OA PDFs, so over-fetch
    papers = (openalex(topic, n=max(n, 25), oa_only=True, issn=issn, since=since) + openalex("", n=50, oa_only=True, issn=issn, since=since)) if issn else []
    seen, shapes = set(), []
    for p in papers:
        if p["id"] in seen or len(shapes) >= want: continue
        seen.add(p["id"])
        url = p.get("pdf") or (unpaywall(p["doi"]) if p.get("doi") else None)
        f = fetch_pdf(url, jd / "accepted" / (p["id"] + ".pdf")) if url else None
        if not f and p.get("title"):  # publisher PDF blocked -> same paper's arXiv preprint (exact title match)
            norm = lambda x: re.sub(r"\W+", "", (x or "").lower())
            hit = next((a for a in arxiv(f'ti:"{p["title"][:120]}"', 3) if norm(a["title"]) == norm(p["title"])), None)
            if hit: f = fetch_pdf(hit["pdf"], jd / "accepted" / (p["id"] + ".pdf")); p["via"] = "arXiv"
        if not f: continue
        t = pdf_text(f)
        if len(t) < 5000: continue
        p["local_pdf"] = str(f); p["shape"] = shape(t); shapes.append(p["shape"])
    measured = {Path(p["local_pdf"]).name for p in papers if p.get("local_pdf")}
    for f in sorted((jd / "accepted").glob("*.pdf")):  # PDFs uploaded by the user count too
        if f.name in measured: continue
        t = pdf_text(f)
        if len(t) > 5000:
            sh = shape(t); shapes.append(sh); papers.append({"id": f.stem, "title": f.stem, "local_pdf": str(f), "shape": sh, "via": "upload"})
    meta["sample_size"] = len(shapes)
    if shapes:
        def med(k):
            xs = [s[k] for s in shapes if s.get(k) is not None]
            return statistics.median(xs) if xs else None
        meta["typical"] = {k: med(k) for k in ("words", "n_refs", "abstract_words", "n_figures", "n_tables", "sent_len_mean", "sent_len_sd", "em_dash_per_1000")}
        meta["common_sections"] = [s for s, _ in Counter(x for s in shapes for x in dict.fromkeys(s["sections"])).most_common(12)]
        meta["marker_baseline_per_1000"] = {m: round(statistics.mean(s["markers"][m] for s in shapes), 3) for m in MARKERS}
    meta["papers"] = [p for p in papers if p.get("local_pdf")]
    if len(shapes) < 3: meta["warning"] = "few open-access accepted papers; upload 3-5 recent accepted PDFs to journal/accepted/ and rerun"
    (jd / "profile.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in meta.items() if k not in ("papers", "marker_baseline_per_1000")}, indent=1, ensure_ascii=False))
    return jd / "profile.json"

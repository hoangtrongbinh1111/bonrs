# Stage 01 — Literature
1. Run `python3 $BONRS_ROOT/bonrs.py lit <slug> "<q1>" "<q2>" ...` with the queries from scope.md (add `--biomed` for biomedical domains). It writes lit/papers.jsonl (arXiv, OpenAlex, Crossref, Europe PMC, Semantic Scholar recommendations, Unpaywall PDFs), lit/pdf/*.txt and lit/NEED_UPLOAD.md. Also read every file in lit/uploads/ (run `pdftotext` if no .txt).
2. Perspectives (STORM): from 3–5 central papers, list the perspectives they take; generate 2–3 questions per perspective; run extra `lit` queries if a perspective is uncovered.
3. Triage all abstracts. For the 15–25 most relevant, read full text and write a query-specific summary per paper with a relevance score 0–10 (PaperQA2 style); keep score ≥6. Skip retracted papers.
4. `lit/review.md`: synthesis by theme (agreed / contested / methods / strengths and weaknesses), citations as [AuthorYear]. `lit/refs.bib`: BibTeX for every cited paper, DOI or arXiv id mandatory, only papers present in papers.jsonl or uploads. Never invent a reference.
5. `lit/gaps.md`: known → unknown → needed; each gap with evidence papers, why it matters, how scope addresses it. If scope no longer holds, revise scope.md and log it.
6. `lit/key_papers.md`: 5–10 direct baselines/competitors with their reported metrics and setups.
7. `lit/novelty.md`: the 3 closest works, exactly what differs, verdict clear / incremental / already-done (→ pivot from scope.md).
8. `lit/REQUEST_FULLTEXT.md`: up to 5 paywalled papers from NEED_UPLOAD.md whose abstract looks essential, one line each on why. Continue without them.

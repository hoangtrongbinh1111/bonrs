# Stage 08 — Submission package
Produce `submission/`:
- `editor_letter.md` FIRST: one page for the human author — decision-level summary, remaining CRITICAL/MAJOR/MINOR items (what/where/fix), what the human must check or sign (authorship, CRediT, ethics, COI, data), and a list of sentences flagged in claims.yaml as `suggests` or weaker.
- `cover_letter.md`: problem, main contribution, why this journal (concrete), originality and single-submission statements; one sentence on AI assistance.
- `ai_disclosure.md`: generated from paper/provenance.json and knowledge/00-general/ai_policy.md for this publisher (exact heading and location); also insert it into the paper where the publisher requires.
- `checklist.md`: walk journal/compliance_checklist.md item by item with evidence (file/line) PASS/FAIL; plus CRediT, COI, ethics, data/code availability (repository + DOI, never "upon request"), third-party permissions, reporting checklist, and a similarity self-check (8-gram overlap of paper text vs lit/pdf/*.txt and lit/uploads/*.txt; rewrite passages with ≥3 consecutive overlapping 8-grams unless quoted).
- Artifact hygiene: remove zero-width characters (U+200B–U+200D, U+FEFF, U+2060), stray Markdown (`**`, `#`), normalise quotes/dashes to the journal style. Do not remove any AI provenance label.
- `highlights.md`, `keywords.md`, graphical abstract description if required; `backup_plan.md` per backup journal; final build of paper/main.pdf or main.docx; `README.md` listing upload order.
`python3 $BONRS_ROOT/bonrs.py audit <slug> --final` must pass; otherwise list the failures at the top of editor_letter.md.

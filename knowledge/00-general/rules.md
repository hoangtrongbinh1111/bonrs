---
name: rules
level: general
tags: [writing]
source: user-provided notes and surveyed tools
added: 2026-10-26
severity: 3
confidence: 0.9
status: active
---
# Core rules (always enforced; edit freely — the agent re-reads this every stage)

- Integrity first: never fabricate data, numbers, citations, or results. Every number in the paper traces to exp/results; every citation exists in refs.bib with DOI/arXiv id. If an experiment fails, say so.
- One paper = one main claim, proven and positioned. Cut anything not serving it.
- Journal first: journal/style_guide.md and author guidelines override every generic writing habit. Match the structure, length, register and vocabulary of that journal's recently accepted papers.
- Do not ask the user. Decide, log the decision in decisions.md, continue. Leave things needing the user (paywalled PDFs, credentials) in a *REQUEST*.md file and keep going.
- Write in English unless bonrs.yaml `language` says otherwise. Short sentences; one idea per sentence; key point first.
- Claims calibrated to evidence: no "first ever", no "novel" without a comparison; use "limited evidence", "few studies", "remains unclear".
- Reproducibility: seeds, versions, exact commands, data provenance, in exp/ and in the paper's methods.
- Figures and tables must stand alone (caption + legend sufficient) and must not repeat the text.
- Define every acronym on first use except universally known ones (DNA, AI).
- Submit to ONE journal; keep backup journals ready.
- Cost discipline: smoke-test experiments on tiny subsets before full runs; poll remote jobs with sleep, do not busy-loop.

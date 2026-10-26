# Stage 00 — Base papers, improvement hypotheses, go/no-go
Input: `idea`, `target_journal`, `domain` and `base_papers` (DOIs, links or titles) in bonrs.yaml (the Goal Anchor), and the author's base papers in `lit/base/` (PDF, DOCX, MD; run `pdftotext -layout` on a PDF without a .txt). A short idea is rarely enough: ground every direction in concrete papers.

1. Base papers. Read every file in lit/base/ in full. For each entry of `base_papers`, fetch the paper (open-access full text, else abstract) with `python3 $BONRS_ROOT/bonrs.py lit <slug> "<DOI or title>" -n 3` and WebFetch. If there are no base papers at all, choose the 3–5 strongest recent papers closest to the idea yourself and say so. Write `lit/base_notes.md`, one section per paper (B1, B2, …): problem, method, data, key numbers, stated limitations, future work, and what a reviewer would attack.
2. Improvement discussion: spawn four subagents in parallel, each given lit/base_notes.md and the idea:
   - Builder: 3–5 improvement directions, each tied to a specific weakness or limitation of named base papers (B#).
   - Skeptical reviewer of the target journal: attacks each direction (already published? weak baseline? data leakage? too incremental?).
   - Pragmatist: data availability, compute, time and skills each direction needs.
   - Editor of the target journal: fit with the journal's scope and recently accepted papers.
   Synthesise 3–5 candidate hypotheses. Merge duplicates, drop directions that do not survive the skeptic.
3. Novelty check per hypothesis: 2–3 targeted searches (`bonrs.py lit <slug> "<query>" -n 10`). Name the closest existing work and the margin that is still new.
4. Score each hypothesis with calibrated, reasoned numbers (never inflate; say what the number rests on):
   - `p_success`: the core result holds and the study is feasible with the data, compute and time available.
   - `p_accept_if_success`: the target journal accepts the paper if the result holds. Start from the journal's base rate (most selective journals accept 10–30%; desk rejection is common), then adjust for novelty margin over the base papers, strength of evidence, scope fit and the risks the skeptic raised.
   - `effort_weeks`, main `risks`, the `minimal_experiment` that would show early whether it works, and `falsified_if`.
5. Write `hypotheses.json` (valid JSON, this exact shape):
```json
{"recommended": "H2", "verdict": "go | pivot | no_go", "reason": "2-4 sentences",
 "base_papers": [{"id": "B1", "title": "...", "source": "lit/base/x.pdf or DOI"}],
 "hypotheses": [{"id": "H1", "title": "short", "statement": "testable hypothesis", "improvement": "what changes versus which base paper",
   "grounded_in": ["B1", "B3"], "novelty": "closest work and remaining margin", "feasibility": "data, compute, time",
   "p_success": 0.6, "p_accept_if_success": 0.3, "effort_weeks": 6, "risks": ["..."], "minimal_experiment": "...", "falsified_if": "..."}]}
```
   `verdict`: `no_go` when the best p_success × p_accept_if_success is below 0.1 or every direction is already published; `pivot` when it only works in a changed form (say which).
6. Write `scope.md` for the recommended hypothesis: a table of all hypotheses with their numbers first, then problem (known → unknown → needed), the main claim, research questions, variables, expected outcome and what would falsify it, `## Queries` (6–10 keyword-style literature queries as bullets), target journal plus 2 backup journals with one line on fit (also write them into bonrs.yaml `backup_journals`), feasibility, and `## Pivots` (the paper that still gets written for a positive, null, negative or infeasible outcome).
7. The run stops after this stage: the author picks one hypothesis or stops (go/no-go). Later stages pursue only the hypothesis named in USER GUIDANCE, or the recommended one.
8. ≤2000 words in scope.md. Log assumptions in decisions.md. If `domain` is `other`, set it in bonrs.yaml to the best fit (ml | biomed | socsci | other).

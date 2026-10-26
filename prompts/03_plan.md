# Stage 03 — Plan
Read scope.md, lit/gaps.md, lit/key_papers.md, lit/novelty.md, journal/style_guide.md.
1. `plan.md`: final RQs; design (data, baselines from key_papers.md, metrics, ablations, statistical tests, seeds/repeats, compute estimate); every planned table and figure with its purpose (planned BEFORE writing); risks and fallbacks.
2. `plan/evaluator.md` — sealed before any experiment: the exact success criterion (metric, threshold, test, comparison) that decides `qualified: true|false`. Do not edit it after stage 04 starts.
3. `paper/outline.md`: single main claim at top; per section bullet points, where each table/figure goes, target word count from the style guide; a sentence-level plan for Introduction and Discussion naming which citation supports which sentence.
4. `exp/README.md`: code layout, how results are written (`exp/results/*.json` + `fig_*.pdf/png`), which host from bonrs.yaml `remote.hosts` (local by default), expected runtime.
If the paper needs no experiments (e.g. review, bibliometric), write a minimal exp plan that produces the analysis tables/figures from data instead.

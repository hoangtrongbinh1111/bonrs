---
name: experiment_loop
level: general
tags: [writing]
source: user-provided notes and surveyed tools
added: 2026-10-26
severity: 3
confidence: 0.9
status: active
---
# Experiment loop (from karpathy/autoresearch) — for any measurable objective

- Establish the **baseline first**: run the plan's reference config unchanged; log it.
- One change per run. Edit the experiment code, `git commit` in exp/, run with output redirected (`> run.log 2>&1`, never flood context), read only the metric lines (`grep "^metric:"`), `tail -50` on crash.
- Fixed budget per run (time or steps) so results are comparable; pilot on a tiny subset (10–15 min) before any full run.
- Log every run in `exp/results.tsv` (tab-separated): `commit  metric  status(keep|discard|crash)  description`.
- Improved → keep the commit. Equal/worse → `git reset` to the previous commit. Crash → fix if trivial, else log and move on.
- Simplicity criterion: a tiny gain that adds ugly complexity is not worth it; equal result with less code is a win.
- Never pause to ask whether to continue. Out of ideas → re-read key papers, combine near-misses, try a bolder change.
- A measured negative result is a success: report it instantly and honestly; never re-run until it "looks better", never round in your favour.
- Correctness before cleverness: before testing the idea, prove the harness is exact (reproduce a known number, sanity checks). A bug there produces a *plausible* wrong number that survives into the paper.
- Before any claim, lock `exp/analysis_contract.md`: unit of analysis, primary metric, seeds/folds, comparison family, statistical test, multiple-comparison correction.
- Every metric (mean, SD, per-seed) goes to `exp/results/*.json`; `bonrs registry <slug>` builds `exp/results/registry.json`, the only legal source of numbers for the paper.
- `plan/evaluator.md` was sealed before experiments: at the end state `qualified: true|false` against it. Not qualified → follow the pre-committed pivot and open the paper with that outcome.

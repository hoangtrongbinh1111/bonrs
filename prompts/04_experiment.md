# Stage 04 — Experiment
Follow plan.md and knowledge/00-general/experiment_loop.md.
- Code under `exp/` (`git init` inside exp/ for keep/discard). Reproducible: seeds, `requirements.txt`, one entry script `exp/run.sh`.
- Hosts (bonrs.yaml `remote.hosts`): first `python3 $BONRS_ROOT/bonrs.py remote <slug> doctor` (checks every host). Local host: runs in exp/ on the bonrs server. ssh hosts: `remote <slug> push` (copies exp/ to every host, one folder per run), then `remote <slug> run --cmd "bash run.sh" --tag main`, poll with `remote <slug> tail --tag main` using `sleep 120`–`sleep 600` between polls, fix and re-run on errors, then `remote <slug> pull` (collects results from every host). Never give up on transient failures.
- Environment: `setup: auto` creates exp/.venv on the host and installs exp/requirements.txt before each command, so keep requirements.txt complete and pinned.
- Several hosts: independent runs (seeds, folds, ablations, baselines) go out in parallel with `--host auto --tag <unique>` (add `--gpu` when a GPU is needed); each lands on the least busy reachable host and `tail --tag <same>` finds it again. One training job is never split across hosts.
- Pilot on a tiny subset first, then the full run. Keep `exp/notebook.md` (command, config, outcome, change, why).
- Write `exp/analysis_contract.md` before interpreting: unit of analysis, primary metric, seeds/folds, comparison family, test, multiple-comparison correction.
- All metrics (mean, SD, per seed, test statistic, p, CI, effect size) → `exp/results/*.json`; figures → `exp/results/fig_*.pdf` + .png (vector, Okabe-Ito palette, fonts ≥7 pt at final size); then `python3 $BONRS_ROOT/bonrs.py registry <slug>`.
- `exp/results/summary.md`: each table/figure with a 2–3 sentence factual description (no interpretation), numbers as in registry, negative or unexpected results stated plainly, and the line `qualified: true|false` against plan/evaluator.md with justification.
Never fabricate or estimate numbers. A failed experiment is reported as failed.

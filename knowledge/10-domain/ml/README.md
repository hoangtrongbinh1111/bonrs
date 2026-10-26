---
name: ml-readme
level: domain
domain: ml
tags: [writing]
source: user-provided notes and surveyed tools
added: 2026-10-26
severity: 2
confidence: 0.9
status: active
---
# ML / computational domain rules
- Report seeds, number of runs, mean±SD, compute budget, hardware, library versions, data splits and leakage checks.
- Re-run baselines under the same budget, or quote them with their exact reported setup; ablate every component you claim matters.
- Follow venue reproducibility checklists (NeurIPS/ICML) even for journals; code/data statements point to a repository with a commit hash.

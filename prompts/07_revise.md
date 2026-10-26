# Stage 07 — Revise
Read the latest reviews/round_<k>.md and, if present, comments/open.md (user comments: highest priority).
- Address only items the Area Chair UPHELD plus all user comments. For each: change the paper (and run new experiments per stage 04 rules if needed, then rebuild the registry), or rebut with evidence.
- Make changes as tracked changes: LaTeX via the `changes` package (`\added{}`, `\deleted{}`, `\replaced{new}{old}` with `\usepackage[final]{changes}` toggled off for review builds) or, for docx, keep `paper/main.prev.md` and let the UI diff it. Update paper/provenance.json (`origin: ai-rewrite`) for touched sections.
- Recompile; run `python3 $BONRS_ROOT/bonrs.py audit <slug>` until clean.
- Write `paper/response_letter.md`: each reviewer item and each user comment quoted, response, exact change (section/page). For user comments write a section "Author comments" and mark each as applied / not applied with reason.
- Never weaken claims below the evidence; never add claims beyond it. Log major decisions in decisions.md.

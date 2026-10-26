# Stage 06 — Review panel (blind, calibrated)
1. Run `python3 $BONRS_ROOT/bonrs.py audit <slug> --final`; every FAIL line becomes a CRITICAL item. If the `/paper-audit` skill exists, run it in review mode and merge.
2. Prepare `reviews/deframed.md`: the paper without abstract, title and contribution paragraph (for the Methodologist).
3. Run these seats as separate subagents IN PARALLEL; none sees another's output. Give each: the paper (or deframed copy), journal/style_guide.md, journal/compliance_checklist.md, lit/key_papers.md, and 3 accepted papers from journal/accepted/ closest in topic. System framing for every seat: "Be critical. If unsure, score low. Most submissions score 4–7; 9–10 is the top 2%."
   - Editor (desk-reject screen): scope fit, contribution visible from title+abstract+intro, guideline compliance, declarations.
   - Methodologist (deframed copy): design, baselines, statistics vs exp/analysis_contract.md, reproducibility, claims vs registry.
   - Domain expert: novelty vs key_papers, missing citations (only ones in lit/papers.jsonl), positioning, whether the gap is real.
   - Clarity reviewer: structure vs style guide, CARS moves, Discussion 5 parts, standalone figures/tables, tense, hedging, LLM-marker vocabulary, length.
   - Devil's advocate: alternative explanations, cherry-picking, overgeneralisation, any number not in registry, any claim stronger than claims.yaml allows.
   - Killer reviewer: the strongest possible case for rejection in ≤400 words.
   Each seat returns JSON: {summary, strengths[], weaknesses[{what, where (section/line/fig), fix, severity CRITICAL|MAJOR|MINOR, evidence_quote, confidence 1-5}], scores {soundness, presentation, contribution: 1-4, overall: 1-10}, pairwise: [{accepted_paper, verdict better|tie|worse, why}]}. Weaknesses without evidence_quote are dropped. Weaknesses must be at least as many as strengths.
4. Area Chair (you): adjudicate every CRITICAL/MAJOR and every killer-reviewer attack: UPHELD or DISMISSED with reason. Check each seat's overall score against its own weaknesses; if they disagree by >2, re-score with justification. Calibrate overall from the pairwise verdicts (worse than all 3 accepted papers ⇒ ≤5).
5. Write `reviews/round_<k>.md` (all seat reports, adjudication, numbered required changes tagged MUST/SHOULD with what/where/fix, minor items in a separate list) and `reviews/round_<k>.json`: {"score": overall 0-10, "decision": "accept|minor|major|reject", "open_major": <count of UPHELD CRITICAL+MAJOR>, "must_fix": [...], "should_fix": [...], "seat_scores": {...}}.

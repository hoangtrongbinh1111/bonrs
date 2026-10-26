# Stage 09 — Retrospective (learning)
Read reviews/, decisions.md, events.jsonl, exp/notebook.md, logs/*.stderr.txt, comments/ (all user comments, applied or not), and the diff between the agent's last version and any user edits (`git log -p -- paper/` commits by users).
1. Lessons: concise imperative rules that would have prevented a reviewer complaint, a user correction, a failure or a time sink. For each, run `python3 $BONRS_ROOT/bonrs.py learn "<rule>" --category <SYSTEM|EXPERIMENT|WRITING|ANALYSIS|PLANNING|LITERATURE|JOURNAL> --severity <1-3> [--domain D]`. Do not duplicate existing skills (check .bonrs/INDEX.json).
2. Journal rules discovered → `learn ... --level journal --journal "<name>"`.
3. User preferences (from comments and user edits: words they remove, sentence length, structure they prefer, tone) → write `proposals/user-preferences.md` with frontmatter (level: user). Everything in proposals/ and every `learn` call is queued for admin review; nothing you write becomes shared knowledge directly.
4. Write `retro.md`: total cost (state.json), rounds and scores, final decision, lessons added, preferences proposed.

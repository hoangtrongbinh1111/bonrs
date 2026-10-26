# Distill a document into knowledge-base skills

Read the raw document at {RAW} (first lines give SOURCE, SUBMITTED_BY and an optional HINT). Read `INDEX.json` in the current directory to see existing skills; open any that overlap.

Goal: turn the document into 1–5 reusable, checkable rules for writing, reviewing, or running research that leads to a publishable journal paper. Skip marketing, generic motivation, and anything already covered by an existing skill (unless the document adds a concrete new rule: then write only the new part and set `supersedes` or mention the related skill).

For each skill write one file `{DRAFTS}/<short-kebab-name>.md`:
```
---
name: <short-kebab-name>
level: general | domain | article_type | journal | experience
domain: <ml|biomed|socsci|...>        # only if level=domain or the rule is domain-specific
article_type: <research|review|bibliometric|case>   # only if level=article_type
journal: <journal name>              # only if level=journal
tags: [<3-6 tags>]
source: <SOURCE URL or file>
source_date: <date in the document if any>
added: <today YYYY-MM-DD>
submitted_by: {USER}
severity: 1-3        # 3 = desk-reject risk if ignored
confidence: 0-1      # how reliable/authoritative the source is
status: draft
---
# <Title>
- Imperative, checkable rules (≤400 words total). Each rule says what to do and how to verify it.
- Include one short good/bad example when it clarifies.
```
Choose the most general level that is still true (general → domain → article type → journal). Never copy long passages verbatim; paraphrase into rules and keep at most one short quotation. If the document has no usable rule, write nothing and print "NO_SKILL".

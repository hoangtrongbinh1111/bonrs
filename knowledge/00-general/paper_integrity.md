---
name: paper_integrity
level: general
tags: [writing]
source: user-provided notes and surveyed tools
added: 2026-10-26
severity: 3
confidence: 0.9
status: active
---
# Paper integrity (from writing-driven-autoresearch, AutoResearchClaw, claude-scholar)

- **Submittable at every stage.** From the first draft, the paper compiles to a complete document with no visible gaps. "placeholder", TODO, \lipsum never appear in the PDF.
- **Write the finished paper before results exist**, with expected numbers wrapped in `\ph{...}`. When a real number lands: `\phm[exp/results/<file>.json:<key>]{value}`. Preamble: `\newcommand{\ph}[1]{#1}` `\newcommand{\phm}[2][]{#2}` `\newcommand{\prov}[2]{#2}`. Markdown route: `{ph:v}`, `{phm:file:key:v}`, `{prov:id: sentence}`.
- A number not in `exp/results/registry.json` goes in `\ph{}` or does not go in the document. Before submission every `\ph{}` is replaced or the sentence is deleted. Fewer claims is fine; invented claims is misconduct.
- **Writer reads only artifacts**: registry.json, figures, summary.md, analysis_contract.md, claims.yaml, lit files. A missing result narrows the scope and becomes a limitation; it is never filled in.
- **Claim ledger** `paper/claims.yaml`: list of `{id, text, evidence: file:key | citekey | fig:<label>, strength: shows | suggests | consistent_with}`. Verb strength in prose may not exceed `strength`. Results/Discussion sentences carry `\prov{<claim-id>}{...}`; a sentence without provenance is marked `[CLAIM NEEDS EVIDENCE]`, never polished.
- Tables are generated from registry.json (`bonrs registry <slug> --table <keys>`), never typed by hand. The same number in abstract/intro/results uses the same source key.
- `bonrs audit <slug> [--final]` is the definition of done.
- Method name is a macro; `\citep`/`\citet` only; `\Cref` only; caption = bold lead-in + how to read + what bold means; booktabs, our method last row; compile after every edit and revert edits that break the build or exceed the section word budget.
- Decision ledger: every gate call, pivot, scope cut → one dated line in decisions.md (what, why, reversible?).
- Delegation to subagents: state objective, output file + schema, tools/sources, boundaries + stop condition. Fan out in parallel when units are independent.

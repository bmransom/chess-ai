---
paths:
  - "roadmap/specs/**/*.md"
  - "roadmap/specs/*.md"
  - "knowledge/glossary.md"
---

<!-- foundry-seed: spec-conventions v1 -->

# Spec conventions

Specs decide names and prose. Hold them to the repo contract.

## Names and prose

- Use the canonical terms in `knowledge/glossary.md`. When code and the glossary
  disagree, the glossary wins.
- Never introduce a term from the glossary's "Replaces (now debt)" column.
- Fit new public types and fields to the entity model in `knowledge/glossary.md`.
- Before coining a canonical name — a glossary term, a public type or field, a
  config knob — search the prior art: the domain's literature, the stack's naming
  conventions, comparable tools. Prefer the established term; record its
  provenance in the glossary, or why none fits.

Follow the writing style in `AGENTS.md`: omit needless words, lead with the point,
one idea per sentence, active and imperative, cut qualifiers; prefer a table or
list when denser than a sentence.

## Before finalizing a design

Dispatch the `spec-reviewer` agent on the changed spec files and apply its
findings before presenting `design.md` for approval.

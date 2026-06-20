---
paths:
  - "knowledge/**/*.md"
  - "knowledge/*.md"
---

<!-- foundry-seed: knowledge-conventions v1 -->

# Knowledge conventions

Concepts live in `knowledge/`, one per file. Reach a concept through the knowledge
tool — its catalog and sections — not by dumping the whole file.

## Frontmatter

Every concept opens with `title`, `description`, and one `type`:

- **reference** — evergreen lookup and contracts.
- **architecture** — how the system is built, and why.
- **guide** — task-oriented how-tos.
- **decision** — dated records: corrections of error, experiment plans.

`python3 scripts/knowledge.py check` lints this and runs in the quick gate; a
concept that fails it is not done.

## Navigate by structure

`knowledge.py list` (catalog by type) · `knowledge.py outline <concept>` (heading
tree) · `knowledge.py section <concept> <heading>` (one section). Read the whole
file only when the section view is not enough.

## Names and prose

Use the vocabulary of `knowledge/glossary.md`; when a concept and the glossary
disagree, the glossary wins. Never use a term from the glossary's "Replaces (now
debt)" column. Follow the `AGENTS.md` writing style — omit needless words, lead
with the point, prefer a table or list when denser than a sentence.

## Adding or changing a concept

- Regenerate the listing — `python3 scripts/knowledge.py index`.
- Log the change in `knowledge/log.md`, newest first.
- Record a real failure as a COE (a `decision` concept) from `knowledge/coe-template.md`.
- Keep planning out of `knowledge/` — the board and specs live in `roadmap/`.

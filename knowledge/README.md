---
title: Knowledge index
description: How the knowledge base is organized — the four types, the knowledge tool, the listing.
type: reference
---

<!-- foundry-seed: knowledge-readme v1 -->

# Knowledge

Browse by type from the terminal: `python3 scripts/knowledge.py list`.
Or run the site: `cd knowledge && npm install && npm run dev`.

## The four types

Every concept carries frontmatter — `title`, `description`, and one `type`:

- **reference** — evergreen lookup and contracts (the glossary, the validation gates).
- **architecture** — how the system is built, and why.
- **guide** — task-oriented how-tos.
- **decision** — dated engineering records: corrections of error, experiment
  plans, investigations.

## The knowledge tool

- `python3 scripts/knowledge.py list` — curated concepts, grouped by type.
- `python3 scripts/knowledge.py outline <concept>` — one concept's heading tree.
- `python3 scripts/knowledge.py section <concept> <heading>` — print one section.
- `python3 scripts/knowledge.py check` — lint frontmatter; runs in the quick gate.
- `python3 scripts/knowledge.py index` — regenerate the listing (`index.md`).

## Reserved files

`index.md` is the generated listing (the site home); `log.md` is the change log,
newest first. Both follow the Open Knowledge Format — no frontmatter.

## See also

The board and roadmap live in `../roadmap/`: `ROADMAP.md` (cross-spec status),
`BACKLOG.md` (the idea pool), and per-feature specs in `specs/` — see
`../roadmap/specs/README.md`.

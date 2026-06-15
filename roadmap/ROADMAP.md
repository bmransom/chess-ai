---
title: Roadmap
description: The tracked kanban board — the single source of truth for cross-spec status.
---

<!-- foundry-seed: roadmap v1 -->

# Roadmap

## Board conventions

Run `scripts/board.sh` to render the board; `scripts/board.sh "Epic 0"` filters to one epic.

- A **card** is one table row: `Work | Status | Spec | Depends on`. Claim a card by
  adding `(@<owner>)` to its Work cell; never take a card another agent owns.
  Respect the Depends-on column.
- A card's **status** is its column: `Backlog → Ready → In progress → Validating →
  Done` (+ `Superseded`, terminal). `Blocked` and the owner are flags, not columns.
- The dashboard groups cards by **epic**; the epic order is the priority order.
- **`Done` requires a recorded gate PASS** — the gate is the evaluator, not the
  author's assertion.
- The un-carded idea pool is `roadmap/BACKLOG.md`; an idea stays there until committed.

### Status taxonomy

Use these words in board tables and spec status headers.

| Status | Meaning |
|---|---|
| Done | Implemented and verified by a recorded gate PASS. |
| Validating | Code landed; the repo's canonical gate is running. |
| In progress | Partially implemented, being hardened, or recently landed with known follow-up. |
| Ready | Spec'd — `roadmap/specs/<feature>/` design and tasks approved, prerequisites met; claimable. |
| Planned | Accepted direction; not started, or scheduled behind prerequisites. |
| Backlog | Captured, not yet committed to build. |
| Blocked | Direction known; work waits on an external dependency or an earlier workstream. |
| Superseded | Preserved for history or rationale; no longer the forward plan. |

## Standing rules

**Naming.** `knowledge/glossary.md` is the vocabulary contract. Use `Done`, never "complete", for implementation state. Inline the most-violated glossary rules here as they emerge.
- The board wins over any per-feature spec.
- Every spec status header points here.

## Status Dashboard

### Epic 0 — Iterative deepening with principal variation

Replace fixed-depth search with iterative deepening that reuses the
transposition table and reports the principal variation — improving move
quality and enabling time management.

| Work | Status | Spec | Depends on |
|---|---|---|---|
| Iterative-deepening search loop in `Searcher` | Backlog | — | — |
| Principal variation reporting (`info pv` over UCI) | Backlog | — | Iterative-deepening search loop |
| Time-managed `go` (stop at a time budget) | Backlog | — | Iterative-deepening search loop |

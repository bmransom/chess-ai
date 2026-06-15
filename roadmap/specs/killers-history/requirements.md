---
title: Killers and history — requirements
description: User stories and EARS acceptance criteria for killer-move and history-heuristic ordering of quiet moves.
---

> **Status:** Planned (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Killers and history — requirements

Order quiet moves with two learned signals so alpha-beta cuts more and the search
reaches greater depth in the same time. Captures (MVV-LVA), checks, and the
transposition-table move (Epic 1) keep their place; only the quiet group changes.
Move ordering stays one composed function. The gain is measured with the
strength harness, not assumed.

## Story 1 — Killer moves

As the engine, I want the quiet moves that recently cut off at a ply tried first,
so similar positions prune sooner.

- AC-1.1 WHEN a quiet move causes a beta-cutoff at a ply, THE SYSTEM SHALL record it as a killer move for that ply.
- AC-1.2 WHEN the quiet group is ordered, THE SYSTEM SHALL place that ply's killer moves at its front.
- AC-1.3 WHEN a recorded killer equals the ply's first killer, THE SYSTEM SHALL leave the ply's killer slots unchanged.
- AC-1.4 WHEN a recorded killer differs from the ply's first killer, THE SYSTEM SHALL shift it into the first slot and keep the previous first as the second.

## Story 2 — History heuristic

As the engine, I want quiet moves that cut off often anywhere tried earlier, so
ordering improves as the search runs.

- AC-2.1 WHEN a quiet move causes a beta-cutoff, THE SYSTEM SHALL add `depth²` (the square of the remaining search depth) to that move's history score, indexed by side to move, from square, and to square.
- AC-2.2 WHEN the non-killer quiet moves are ordered, THE SYSTEM SHALL sort them by history score, highest first.
- AC-2.3 WHEN two quiet moves have equal history score, THE SYSTEM SHALL break the tie by the piece-square-table change.

## Story 3 — Lifetime

As the engine, I want the tables scoped to one search, so they help across
iterations without leaking between moves.

- AC-3.1 WHEN a new `Searcher` is created, THE SYSTEM SHALL start with empty killer and history tables.
- AC-3.2 WHEN iterative deepening runs within one search, THE SYSTEM SHALL retain the killer and history tables across depths.

## Story 4 — Correctness preserved

As the maintainer, I want the same moves found, so ordering changes speed and not
results.

- AC-4.1 WHEN searched to depth 3, THE SYSTEM SHALL still return `f8f7`, `h7h8`, `f6a6`, and not `e1e8` for the four tactical positions.

## Story 5 — Measured strength

As the maintainer, I want evidence the change helps, so strength claims are
verified.

- AC-5.1 WHEN the candidate plays the pre-epic baseline through `selfplay.py`, THE SYSTEM SHALL record the Elo delta in the pull request.

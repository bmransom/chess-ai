---
title: Killers and history — tasks
description: Waved plan for killer-move and history-heuristic quiet ordering; each task names its gate.
---

> **Status:** Done (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Killers and history — tasks

Tasks within a wave are independent; each wave builds on the last. Every task
names its gate. Apply the changes in `search.rs` and `movesort.rs`; the existing
cargo gate (fmt, clippy, test) and the tactical tests cover correctness.

## Wave 1 — Killer moves

- **1.1 Killer table + update.** Add `killers` to the `Searcher`; at the quiet-move
  beta-cutoff in `search_node`, shift the move into the ply's slots with dedupe.
  *Gate: AC-1.1, AC-1.3, AC-1.4 — a unit test on the shift and dedupe.*
- **1.2 Ordering context + killers first.** Thread an `OrderingContext` (the ply's
  killers, the history borrow) into `prioritize_legal_moves` /
  `get_moves_to_dequiet`; place killers at the front of the quiet group. *Gate:
  AC-1.2, AC-4.1 — killers lead the quiet group and the four tactical tests pass.*

## Wave 2 — History heuristic

- **2.1 History table + update.** Add `history` to the `Searcher`; at the quiet-move
  cutoff, add `depth²`, clamped. *Gate: AC-2.1, AC-3.1–3.2 — a unit test that the
  bump adds `depth²` at `[side][from][to]`, the tables are empty on a new Searcher,
  and retained across iterations.*
- **2.2 History ordering.** Sort the non-killer quiets by history score, PST-delta
  as the tiebreak. *Gate: AC-2.2–2.3, AC-4.1 — a unit test reorders two equal quiets
  by history, and the tactical tests still pass.*

## Wave 3 — Measure & docs

- **3.1 Strength measurement.** Build the candidate against the pre-epic `main`
  baseline and run `selfplay.py`; record the Elo delta. *Gate: AC-5.1 — the Elo
  delta is recorded in the PR.*
- **3.2 Docs & board.** Add Killer move and History heuristic to
  `knowledge/glossary.md` with provenance; move the Epic 3 cards to Done. *Gate:
  `python3 scripts/knowledge.py check` clean; recorded gate PASS.*

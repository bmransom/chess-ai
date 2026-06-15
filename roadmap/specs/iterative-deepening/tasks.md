---
title: Iterative deepening — tasks
description: Waved implementation plan; each task names the gate that proves it.
---

> **Status:** Planned (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Iterative deepening — tasks

Tasks within a wave are independent; each wave builds on the last. Every task
names its gate. The enabling fixes (Wave 1) land before iterative deepening
relies on them. Apply the `search.rs` naming cleanups (see design.md) as those
functions are rewritten across Waves 1, 3, and 4.

## Wave 1 — Enabling fixes

- **1.1 Transposition-table reuse.** `get` returns on a Zobrist-key match; the
  search uses a stored entry with `depth ≥ requested` for the cutoff and always
  searches the stored best Move first. *Gate: AC-2.1–2.3 — a unit test shows a
  deep entry cuts, and a depth-`D` search with a warm table visits fewer nodes
  than with an empty one.*
- **1.2 Mate-distance scoring.** Score checkmate `MATE − ply`; classify mate
  scores; apply the ±ply adjustment on TT store and probe. *Gate: AC-3.1, AC-3.3
  — a mate in one outscores a mate in three and survives a TT round-trip.*

## Wave 2 — Time budget

- **2.1 `SearchLimits` + budget.** Parse limits into `SearchLimits`; compute the
  deadline from `movetime`, the clock (`remaining/movestogo` or `/30`, `+0.7·inc`,
  capped at 40%, minus overhead), or none for depth-only. *Gate: AC-1.2 — unit
  tests on the budget for movetime, sudden death, increment, `movestogo`, and the
  40% cap.*

## Wave 3 — Iterative deepening loop

- **3.1 Node counter + stop.** Add the `nodes` counter and `should_stop()` polled
  every ~2048 nodes against the deadline. *Gate: AC-1.1 — a `movetime` search
  returns within budget + overhead.*
- **3.2 Deepening loop.** Loop `1..=max_depth`, keep the last completed depth,
  discard a stopped iteration, early-exit on forced mate. *Gate: AC-1.3–1.5 — the
  result deepens with more time and never adopts a half-finished iteration.*

## Wave 4 — Principal variation

- **4.1 Triangular PV-table.** Collect the PV; expose it on the result. *Gate:
  AC-4.1–4.2 — the PV's first Move equals the returned Move and the line is legal.*

## Wave 5 — The `search` seam

- **5.1 PyO3 `search`.** Expose `search(max_depth, move_time_ms, white_time_ms,
  black_time_ms, white_increment_ms, black_increment_ms, moves_to_go)` returning
  the result dict (`best_move`, `score_centipawns`, `mate_in_moves`, `depth`,
  `nodes`, `elapsed_ms`, `principal_variation`); `mate_in_moves` signed. *Gate:
  AC-1.6, AC-3.2 — a Python call returns the documented shape with `mate_in_moves`
  in moves.*

## Wave 6 — UCI wrapper

- **6.1 Scenario first.** Add a UCI process Scenario to `features/`: `go movetime`
  returns a `bestmove` and an `info … pv …` line. *Gate: Scenario exists and fails.*
- **6.2 Wire `communication.py`.** Parse the `go` time-control tokens, call
  `search`, print the `info` line then `bestmove`; bare `go` keeps the default
  depth and endgame boost. *Gate: AC-5.1–5.5 — acceptance Scenarios pass through
  the real UCI engine.*

## Wave 7 — Verify & docs

- **7.1 Tactics preserved.** Run the four tactical tests through `search` at depth
  3. *Gate: AC-6.1 — `f8f7`, `h7h8`, `f6a6`, not `e1e8`; a changed move is recorded
  as a faster-mate improvement.*
- **7.2 Docs & board.** Update `knowledge/glossary.md` (new terms + provenance, and
  the Principal variation entry), note the seam, move the Epic 1 cards to Done.
  *Gate: `python3 scripts/knowledge.py check` clean; recorded gate PASS.*

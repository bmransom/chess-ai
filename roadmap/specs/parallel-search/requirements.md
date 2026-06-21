---
title: Parallel search — requirements
description: Multi-threaded Lazy SMP search that deepens within the same time budget, with the single-threaded path preserved bit-identical as the deterministic measurement basis.
---

> **Status:** Ready — tracked on the [board](../../ROADMAP.md). Derived from the
> two-harness deliberation session `parallel-search` (Codex + Claude Code).

# Parallel search — requirements

The engine searches single-threaded. This feature adds Lazy SMP — N worker
searches sharing one transposition table — so the engine deepens further within
the same time budget. `Threads = 1` stays the default and bit-identical to today,
because the fair-match harness measures eval terms against that deterministic
path; a separate time-control match measures the parallel speedup.

## Story 1 — Parallel search

As the maintainer, I want the engine to search across cores, so it reaches greater
depth in the same time and plays stronger on lichess.

- AC-1.1 WHEN `Threads` is greater than 1, THE SYSTEM SHALL run `Threads` worker searches in parallel that share one transposition table.
- AC-1.2 WHEN the parallel search finishes, THE SYSTEM SHALL report the first worker's completed result (best move and principal variation).
- AC-1.3 WHEN the time budget expires, THE SYSTEM SHALL stop every worker and return the best result from a completed iteration.

## Story 2 — The deterministic basis is preserved

As the maintainer, I want single-threaded search untouched, so the eval-term
measurements still hold.

- AC-2.1 THE SYSTEM SHALL default `Threads` to 1.
- AC-2.2 WHEN `Threads` is 1, THE SYSTEM SHALL produce the same best move and the same node count as the single-threaded engine for any position (bit-identical).
- AC-2.3 WHEN a node limit is set (`go nodes`), THE SYSTEM SHALL run a single thread regardless of the `Threads` value.

## Story 3 — Lockless shared transposition table

As the maintainer, I want a thread-safe TT without locks on the hot path, so the
workers actually share their work.

- AC-3.1 WHEN `Threads` is greater than 1, THE SYSTEM SHALL store and probe transposition entries without locks.
- AC-3.2 WHEN a transposition slot is read mid-write (a torn read), THE SYSTEM SHALL return a miss, never an entry for a different position.

## Story 4 — Thread configuration

As the maintainer, I want a standard `Threads` UCI option, so a bridge or GUI can
set the worker count.

- AC-4.1 WHEN it receives `setoption name Threads value N`, THE SYSTEM SHALL set the worker count, clamped to the available core count.
- AC-4.2 WHEN it receives `uci`, THE SYSTEM SHALL advertise `option name Threads type spin default 1 min 1 max <available_parallelism>` before `uciok`.

## Story 5 — Measured speedup

As the maintainer, I want the parallel gain measured honestly, so a claimed Elo
gain is real and not a fixed-node artifact.

- AC-5.1 WHEN measuring the parallel speedup, THE SYSTEM SHALL use a time-control SPRT (`Threads = 1` vs `Threads = N` at equal wall-clock), not the fixed-node SPRT.
- AC-5.2 WHEN it reports `info`, THE SYSTEM SHALL sum worker nodes for `nodes`, and that sum SHALL NOT feed an eval-term retention decision.

## Story 6 — Guarded by the gate

As the maintainer, I want the existing gate green and the new behavior tested.

- AC-6.1 WHEN `scripts/check-fast.sh` runs, THE SYSTEM SHALL pass perft and the tactical tests at `Threads = 1`, plus a `Threads = 1` `(best_move, node_count)` determinism baseline, `setoption` parsing, the `go nodes` single-thread guard, and a lockless torn-read rejection test.

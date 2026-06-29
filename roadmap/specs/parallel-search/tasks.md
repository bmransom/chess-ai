---
title: Parallel search — tasks
description: Waved plan — generic TT backend, lockless atomic table, Lazy SMP coordinator, config seam, and measurement; each task names its gate.
---

> **Status:** Ready — tracked on the [board](../../ROADMAP.md). Derived from the
> two-harness deliberation session `parallel-search`.

# Parallel search — tasks

Tasks within a wave are independent; each wave builds on the last. Every task names
its gate. The single-threaded path must stay bit-identical throughout — Wave 1's
determinism baseline guards every later wave.

## Wave 1 — Generic TT backend

- **1.1 `TranspositionTable` trait + generic `Searcher`.** Make `TranspositionTable`
  a trait (`probe(&self)`, `replace(&self)`); rename today's concrete table `ExclusiveTranspositionTable`
  and make `Searcher` generic over the trait. Convert `ExclusiveTranspositionTable`'s `probe`/`replace` to
  `&self` with interior mutability, keeping the replace-by-age-or-depth policy. *Gate: AC-2.2 — a `Threads=1`
  `(best_move, node_count)` baseline over a position set is unchanged; perft and the
  tactical tests stay green.*

## Wave 2 — Lockless atomic table

- **2.1 `LocklessTranspositionTable`.** The Hyatt single-u64 lockless slot
  `{ key: AtomicU64 = zobrist ^ data, data: AtomicU64 }`; pack/unpack `HashEntry`
  into one 60-bit `data` word. `probe` accepts only if `key ^ data == zobrist`.
  No `unsafe`. *Gate: AC-3.1–3.2 — a torn-read rejection test: a mismatched
  key/data pair probes as a miss; a matched pair round-trips.*

## Wave 3 — Lazy SMP coordinator

- **3.1 Parallel coordinator.** When `thread_count > 1` and no node limit, spawn
  `thread_count` workers with `std::thread::scope`, each running the iterative-deepening
  loop on a cloned `Board` with per-worker state, sharing the `LocklessTranspositionTable`, the
  `deadline`, an `AtomicBool` stop, and an `AtomicU64` node counter. Return thread 0's
  result. *Gate: AC-1.1–1.3 — a multi-thread search returns a legal move and stops
  within the budget; `search_node` is unchanged.*

## Wave 4 — Configuration & seam

- **4.1 `Threads` option.** Add `setoption` parsing to `communication.py` (none
  today) and `set_threads`; advertise `option name Threads type spin default 1 min 1
  max <available_parallelism>` on `uci`; store `thread_count` on the PyO3 `Searcher`;
  clamp to `available_parallelism()`. *Gate: AC-4.1–4.2 — a `setoption` parsing test
  and the advertised option on `uci`.*
- **4.2 Seam guards.** Force the single-thread path when `node_limit.is_some()`;
  wrap the Rust search in `py.allow_threads`; snapshot-decode the atomic TT for
  `/transposition_table`. *Gate: AC-2.3 — `go nodes` resolves to one thread (test).*

## Wave 5 — Measure, docs & board

- **5.1 Time-control SPRT.** A `Threads=1` vs `Threads=N` time-control match through
  the existing harness; record the Elo gain. *Gate: AC-5.1 — the gain is recorded;
  summed parallel nodes never feed a term decision.*
  **Measured (2026-06-29):** Threads=8 vs Threads=1 (both NNUE, `--movetime 400`,
  80 pairs via `sprt.py --movetime`): **−17.4 Elo [−46.3, +11.2]** — a wash (CI spans
  zero, 61% draws). The lockstep workers re-search the same tree; the gain awaits
  Wave 6 (search diversity). Confound noted: `Threads=8` also swaps in the lossier
  packed lockless table, so part of the deficit is the table, not the threads.
- **5.2 Docs & board.** Add `Lazy SMP`, `lockless transposition table`, and the
  `Threads` option to `knowledge/glossary.md` with provenance; note the option in
  `AGENTS.md`; move the Epic 5 cards to Done. *Gate: `python3 scripts/knowledge.py
  check` clean; recorded gate PASS.*

## Wave 6 — Search diversity

- **6.1 Staggered depths.** Add a per-worker `skip(depth)` schedule to the
  iterative-deepening loop (Stockfish `SkipSize`/`SkipPhase`, keyed on the worker
  index); worker 0 and `Threads = 1` never skip. *Gate: AC-7.1–7.2 — helpers skip a
  documented depth set; the `Threads = 1` `(best_move, node_count)` determinism
  baseline stays green.*
- **6.2 Thread voting.** Replace the unconditional thread-0 return with the
  depth-and-score-weighted vote (`weight = (score − min_score + 1) × depth`); report
  the winning worker's PV and score; prefer shorter mates. *Gate: AC-7.3–7.4 — a unit
  test that a constructed worker set votes for the agreed deep move, and that a mate
  worker outvotes a deeper non-mate.*
- **6.3 Re-measure.** Re-run the time-control SPRT (`Threads = 1` vs diversified
  `Threads = N`) and record the Elo delta against the Wave 5.1 lockstep baseline.
  *Gate: AC-7.5 — the gain is recorded; the determinism baseline stays green.*
- **6.4 Docs & glossary.** Add `depth staggering` and `thread voting` to
  `knowledge/glossary.md` with provenance. *Gate: `python3 scripts/knowledge.py check`
  clean; recorded gate PASS.*

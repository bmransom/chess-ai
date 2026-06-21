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
  a trait (`probe(&self)`, `replace(&self)`); rename today's concrete table `VecTt`
  and make `Searcher` generic over the trait. Convert `VecTt`'s `probe`/`replace` to
  `&self` with interior mutability, keeping the replace-by-age-or-depth policy. *Gate: AC-2.2 — a `Threads=1`
  `(best_move, node_count)` baseline over a position set is unchanged; perft and the
  tactical tests stay green.*

## Wave 2 — Lockless atomic table

- **2.1 `AtomicTt`.** The Hyatt single-u64 lockless slot
  `{ key: AtomicU64 = zobrist ^ data, data: AtomicU64 }`; pack/unpack `HashEntry`
  into one 60-bit `data` word. `probe` accepts only if `key ^ data == zobrist`.
  No `unsafe`. *Gate: AC-3.1–3.2 — a torn-read rejection test: a mismatched
  key/data pair probes as a miss; a matched pair round-trips.*

## Wave 3 — Lazy SMP coordinator

- **3.1 Parallel coordinator.** When `thread_count > 1` and no node limit, spawn
  `thread_count` workers with `std::thread::scope`, each running the iterative-deepening
  loop on a cloned `Board` with per-worker state, sharing the `AtomicTt`, the
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
- **5.2 Docs & board.** Add `Lazy SMP`, `lockless transposition table`, and the
  `Threads` option to `knowledge/glossary.md` with provenance; note the option in
  `AGENTS.md`; move the Epic 5 cards to Done. *Gate: `python3 scripts/knowledge.py
  check` clean; recorded gate PASS.*

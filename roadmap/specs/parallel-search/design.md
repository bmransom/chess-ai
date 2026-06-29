---
title: Parallel search — design
description: Lazy SMP with a monomorphized generic over two TranspositionTable backends — an exclusive table for Threads=1 and a lockless single-u64 table for Threads>1.
---

> **Status:** Ready — tracked on the [board](../../ROADMAP.md). Derived from the
> two-harness deliberation session `parallel-search` (Codex + Claude Code); the
> recorded decisions live in `.foundry/tmp/harness-deliberation/`.

# Parallel search — design

## Decision summary

| Decision | Choice | Why |
|---|---|---|
| Scheme | Lazy SMP | Matches the recursive Searcher shape; almost all the work is the shared TT. |
| Strategy pattern | No | Thread count is a runtime knob; the scheme is build-time + A/B'd — the repo's move-ordering principle. |
| Backend dispatch | Monomorphized generic `Searcher<Tt>` | The repo's own escape hatch (`Searcher<O: MoveOrderer>`); zero per-node virtual calls. |
| TT (parallel) | Lockless single-u64 atomic | Hyatt key-XOR-data; no locks on the hot path, no `unsafe`. |
| `Threads = 1` | Bit-identical to today | The deterministic basis the fair-match harness measures against. |
| `go nodes` | Forces one thread | The summed node count is non-deterministic — node mode is unreproducible with N>1. |
| Parallel Elo | Time-control SPRT | Fixed-node's premise is determinism, which parallel search abandons. |

## Lazy SMP coordinator

A parallel coordinator wraps `Searcher::search`; the recursive `search_node`
(`core/src/search.rs`) is **unchanged**. When `thread_count > 1` and no node limit
is set, the coordinator spawns `thread_count` workers with `std::thread::scope`
(scoped threads join at scope end — that join *is* the clean stop). Each worker
runs today's iterative-deepening loop on a **cloned `Board`** (`Board: Clone`) with
its own `history`, `killers`, `pv_table`, `position_history`, and `nodes`. Workers
share only:

- the `LocklessTranspositionTable` (a `&` borrow through the scope),
- the immutable `deadline` (each worker computes the same one from `limits` + `now`),
- an `AtomicBool` stop flag, so the first worker to reach the budget halts its peers.

Thread 0's completed result is returned, with its `nodes` replaced by the workers'
sum (each worker's count is added up at join — no per-node shared counter, so no
hot-path contention). YBWC and root-splitting are rejected: weaving shared alpha,
root-move arbitration, and cancellation through the serial alpha-beta move loop is
too much first-step risk for an engine with no concurrency today.

This Wave 1–4 coordinator runs every worker **identically** — the same iterative
deepening from depth 1 — relying on timing and the shared TT to desync them. Wave
5.1 measured that at **−17 Elo [−46.3, +11.2]** (Threads=8 vs Threads=1, time
control): a wash. The workers re-search the same tree, so the shared TT only
deduplicates redundant work. Search diversity is what converts the node throughput
into Elo.

## Search diversity — staggered depths and thread voting

Two mechanisms make the workers search *differently*. Both touch only the
`Threads > 1` path; worker 0 and the single-threaded `Searcher` are unchanged, so
AC-2.2 bit-identity holds by construction.

### Staggered depths (a skip schedule)

Worker 0 is the **main line**: it searches every depth `1, 2, 3, …` and never skips,
so a complete result always exists. Each **helper** `i > 0` skips a subset of depths
on a deterministic pattern keyed on `i`, spreading the helpers across plies — they
fill the TT with bounds from different depths instead of all racing the same one. We
adopt Stockfish's `SkipSize`/`SkipPhase` scheme (`search.cpp`): with `j = (i − 1) mod
20`, worker `i` skips root depth `d` when `((d + SkipPhase[j]) / SkipSize[j])` is
odd; the two length-20 tables fan the helpers over a range of depth offsets.

Integration: the iterative-deepening loop in `Searcher::search` gains a `skip(depth)`
predicate (a no-op for `Threads = 1` and worker 0). `search_node` is unchanged.

### Thread voting

Returning worker 0 wastes the helpers' finds. Instead, each worker contributes its
final `(best_move, depth, score)`, and the coordinator **votes** — with `min_score`
the minimum score over the workers:

```
weight(worker)     = (worker.score − min_score + 1) × worker.depth
votes[best_move]  += weight(worker)        # summed over all workers
```

The move with the greatest summed vote wins; among the workers proposing it the
deepest is selected and its principal variation and score are reported (AC-7.3–7.4).
This rewards a move that several deep, high-scoring workers agree on — Stockfish's
`Thread::best_thread` rule. Mate scores are the one special case: a worker reporting
a nearer mate outvotes a deeper non-mate. The vote runs once, at the
`std::thread::scope` join — no hot-path cost.

## No strategy pattern — a monomorphized generic

This follows the repo's compose-and-A/B principle from move ordering, not a runtime
`SearchStrategy`. The rule splits cleanly:

- **Runtime, one UCI option:** thread *count* — one parameterized code path.
- **Build-time, separate builds + SPRT:** the parallelization *scheme* (Lazy SMP
  vs YBWC) — never a runtime-swappable strategy.

The `Threads` option is a *resource* knob (a UCI `spin`, as in every serious
engine), not the eval/algorithm A/B knob the strength-harness spec rejected. The TT
backend is selected once, cold, at search entry via a monomorphized generic
`Searcher<Tt: TranspositionTable>` — the repo's own escape hatch
(`Searcher<O: MoveOrderer>`) — so there are zero per-node virtual calls.

## Two TT backends behind one trait

The `TranspositionTable` becomes a trait — `probe(&self, zobrist) -> Option<HashEntry>`
and `replace(&self, entry)` — and today's concrete table is renamed `ExclusiveTranspositionTable`, one of
its two implementations. `HashEntry` stays the decoded semantic record.

- **`ExclusiveTranspositionTable`** — today's `Vec<Option<HashEntry>>` with the same replace-by-age-or-depth
  policy, used for `Threads = 1`. The `&self` signature gives it interior mutability
  (`RefCell`); with one thread the borrow always succeeds and the behavior is
  identical. Bit-identity is therefore a property of the type, guarded by the
  determinism test — not a packing argument.
- **`LocklessTranspositionTable`** — the Hyatt key-XOR-data slot `{ key: AtomicU64, data: AtomicU64 }`
  with `key = zobrist ^ data`, used for `Threads > 1`.

**Packing (one u64).** The entry fits in 60 bits — `best_move` 16 (the `0x0000`
quiet `a1a1`, never legal, is the `None` sentinel), `depth` 8 (range −5..=64),
`value` 18 (`|value| ≤ MATE + ply < 2^17`), `flag` 2, `age` 16 (halfmove clock
≤ 100) — so a single data word suffices; no two-word `mix()` scheme.

- `probe`: load `data`, load `key`, accept only if `key ^ data == zobrist`. A torn
  read (data from store A, key from store B) fails the check and returns `None` — a
  miss, never a wrong-position hit.
- `replace`: load `data`, decode age/depth, apply the replace-by-age-or-depth
  policy best-effort, then store `data` and `key`.

The age/depth replace race is a **speed-only** concern: TT entries are hints, a lost
replacement costs nodes not legality, and node-count reproducibility is abandoned
under `Threads > 1` anyway.

## Determinism and measurement

- **`Threads = 1` is bit-identical** because it instantiates `Searcher<ExclusiveTranspositionTable>` —
  today's exact access pattern and policy. The eval-term measurements hold by
  construction; a `(best_move, node_count)` baseline test over a position set guards
  it (extending AC-1.3 of the fair-match harness).
- **`go nodes` forces one thread** by a hard guard in the PyO3 seam: when
  `node_limit.is_some()`, the single-thread path runs regardless of `thread_count`.
  Under `Threads > 1` the workers desync through the shared TT, so the summed node
  count varies run to run — node mode is unreproducible *in principle* with N>1, and
  per-thread sub-budgets don't save it.
- **Parallel Elo** is a time-control SPRT (`Threads = 1` vs `N` at equal wall-clock),
  never the fixed-node SPRT (whose premise is determinism). Summed worker nodes go
  to UCI `info nodes` (NPS is meaningful) but never to a term-retention decision.
- **`ucinewgame`** clears the shared TT; workers are spawned and joined inside one
  `search()`, so none outlives a UCI command and `new_game()` clears it safely.

## Configuration and boundaries

The threading lives in **Rust** (the coordinator in `search.rs` or a small
`search/parallel.rs`); Python only parses UCI. `communication.py` gains a
`setoption` branch (it has none today) that calls a new `set_threads`; `uci`
advertises `option name Threads type spin default 1 min 1 max <available_parallelism>`.
`thread_count` is stored on the PyO3 `Searcher`; the default is 1; the count is
clamped to `std::thread::available_parallelism()` (lichess-bot runs the engine as
one process, and oversubscription loses Elo).

**The GIL is released during search.** The PyO3 `search` method already takes
`py: Python`; it wraps the Rust call in `py.allow_threads(|| …)` so the CPU search
does not hold the GIL while N OS threads run — non-optional, since the GIL would
serialize the workers and erase the gain.

**HTTP introspection snapshots.** `entries()` cannot return references from an
atomic table, so `/transposition_table` snapshot-decodes the slots; it runs at
`Threads = 1` with no search in flight, so the point-in-time snapshot is well-defined.

## Naming and provenance

| Term | Definition | Provenance |
|---|---|---|
| Lazy SMP | Parallel search where each thread runs the full search, sharing one TT | CPW "Lazy SMP" |
| Lockless transposition table | A shared TT using the key-XOR-data trick to reject torn reads | Robert Hyatt; CPW "Shared Hash Table" |
| Threads (UCI option) | The worker count, a `spin` resource option | UCI `option`; standard engine convention |
| Depth staggering | A per-helper depth-skip schedule so the workers search different plies | Stockfish `SkipSize`/`SkipPhase` (`search.cpp`) |
| Thread voting | Selecting the reported move by a depth-and-score-weighted vote across workers | Stockfish `Thread::best_thread` |

## Alternatives considered

- **YBWC / root-splitting.** Rejected as a first step: far more complex (split
  points, shared alpha, cancellation) and superseded by Lazy SMP.
- **Sharded-mutex TT.** Rejected: a lock on every hot-path probe/replace.
- **Per-thread TTs.** Rejected: helpers stop sharing bounds, defeating Lazy SMP.
- **Two-data-word packing (Stockfish-style).** Rejected: the entry fits one u64, so
  a second word and a `mix()` only widen the torn-read window.
- **Two concrete code paths** (no generic). Rejected: duplicates the negamax logic;
  the monomorphized generic matches the repo's `Searcher<O: MoveOrderer>` and the
  determinism guard de-risks the `ExclusiveTranspositionTable` interior-mutability change.

## Risks

| Risk | Mitigation |
|---|---|
| Lockless correctness is subtle | A torn-read rejection test; `AtomicU64` only, no `unsafe`. |
| Identical workers duplicate effort before TT desync | Staggered depths + thread voting (Search diversity); measure with the time-control SPRT before claiming Elo. |
| Diversity gain is empirical and modest | Re-measure vs both Threads=1 and the lockstep baseline; basic Lazy SMP is tens of Elo, not hundreds. |
| Vote picks a worse move than the deepest worker | Weight by depth and score; prefer shorter mates; a unit test on a constructed worker set. |
| `go nodes` non-reproducible under threads | A hard single-thread guard in the seam + a test. |
| GIL held during search serializes workers | `py.allow_threads` around the Rust call (mandatory). |
| Oversubscription loses Elo | Default 1; clamp to `available_parallelism()`. |
| Baseline regression from the generic | The `Threads = 1` `(best_move, node_count)` determinism guard. |

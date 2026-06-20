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

### Epic 0 — Rust engine core (PyO3)

Port the move-picking core to a native Rust crate (`brandobot_core`, via PyO3 and
maturin) with hand-rolled bitboards; Python keeps only the UCI loop and Flask API
as thin wrappers. A faithful port — same evaluation and search — so strength comes
from native speed. Lands before iterative deepening, which then builds on the Rust
Searcher.

| Work | Status | Spec | Depends on |
|---|---|---|---|
| Crate scaffold + maturin + gate wiring (@branransom) | Done | [rust-engine-core](specs/rust-engine-core/design.md) | — |
| Bitboard Board + make/unmake + Zobrist (@branransom) | Done | [rust-engine-core](specs/rust-engine-core/design.md) | Crate scaffold + maturin + gate wiring |
| Move generation + perft suite (@branransom) | Done | [rust-engine-core](specs/rust-engine-core/design.md) | Bitboard Board + make/unmake + Zobrist |
| Evaluation, MoveSorter, TranspositionTable (@branransom) | Done | [rust-engine-core](specs/rust-engine-core/design.md) | Move generation + perft suite |
| Searcher (negamax + alpha-beta + quiescence + TT) (@branransom) | Done | [rust-engine-core](specs/rust-engine-core/design.md) | Evaluation, MoveSorter, TranspositionTable |
| UCI + Flask wrappers on `brandobot_core` (@branransom) | Done | [rust-engine-core](specs/rust-engine-core/design.md) | Searcher (negamax + alpha-beta + quiescence + TT) |
| Cutover: remove python-chess + docs (@branransom) | Done | [rust-engine-core](specs/rust-engine-core/design.md) | UCI + Flask wrappers on `brandobot_core` |

### Epic 1 — Iterative deepening with principal variation

Replace fixed-depth search with iterative deepening on the Rust Searcher: deepen
within a time budget, reuse the transposition table across depths, and report the
principal variation. Improves move quality and enables timed play on lichess.

| Work | Status | Spec | Depends on |
|---|---|---|---|
| Transposition-table reuse + mate-distance scoring (@branransom) | Done | [iterative-deepening](specs/iterative-deepening/design.md) | Rust engine core |
| Time budget (`SearchLimits`) (@branransom) | Done | [iterative-deepening](specs/iterative-deepening/design.md) | Transposition-table reuse + mate-distance scoring |
| Iterative-deepening loop + stop (@branransom) | Done | [iterative-deepening](specs/iterative-deepening/design.md) | Time budget (`SearchLimits`) |
| Principal variation (triangular PV-table) (@branransom) | Done | [iterative-deepening](specs/iterative-deepening/design.md) | Iterative-deepening loop + stop |
| Time-aware `search` seam (PyO3) (@branransom) | Done | [iterative-deepening](specs/iterative-deepening/design.md) | Principal variation (triangular PV-table) |
| UCI time controls (`go` + `info pv`) (@branransom) | Done | [iterative-deepening](specs/iterative-deepening/design.md) | Time-aware `search` seam (PyO3) |

### Epic 2 — Strength measurement

Turn engine changes into a measured strength delta: an EPD tactical suite that
reports a solve-rate and a self-play match that reports an Elo estimate, with
python-chess as the independent oracle. Verifies every future search and eval
change instead of guessing. The next step is to strengthen the self-play
decision rule so short, flat runs are not over-interpreted.

| Work | Status | Spec | Depends on |
|---|---|---|---|
| EPD tactical suite (solve-rate) (@branransom) | Done | [strength-harness](specs/strength-harness/design.md) | Iterative deepening |
| Self-play match (Elo) (@branransom) | Done | [strength-harness](specs/strength-harness/design.md) | Iterative deepening |
| Gate self-test + docs (@branransom) | Done | [strength-harness](specs/strength-harness/design.md) | EPD tactical suite (solve-rate), Self-play match (Elo) |
| Fair-match harness + acceptance rule (@branransom) | In progress | [fair-match-harness](specs/fair-match-harness/design.md) | Self-play match (Elo) |

### Epic 3 — Killer-move and history ordering

Order quiet moves with killer moves and the history heuristic so alpha-beta cuts
more and the search reaches greater depth in the same time. Ordering stays one
composed function; the gain is measured with the strength harness.

| Work | Status | Spec | Depends on |
|---|---|---|---|
| Killer moves (@branransom) | Done | [killers-history](specs/killers-history/design.md) | Iterative deepening |
| History heuristic (@branransom) | Done | [killers-history](specs/killers-history/design.md) | Killer moves |
| Measure (Elo) + docs (@branransom) | Done | [killers-history](specs/killers-history/design.md) | History heuristic, Strength measurement |

### Epic 4 — Evaluation

Replace material-plus-PST with a tapered evaluation on PeSTO's tuned tables, then
add mobility, king safety, and pawn structure. Retire the binary `is_endgame`
flag. Each term is measured against the prior build with the strength harness;
term-retention decisions stay open until the harness method is fair enough to
support them.

| Work | Status | Spec | Depends on |
|---|---|---|---|
| Tapered foundation (PeSTO) + retire `is_endgame` (@branransom) | Done | [evaluation](specs/evaluation/design.md) | Iterative deepening, Strength measurement |
| Mobility (@branransom) | In progress | [evaluation](specs/evaluation/design.md) | Tapered foundation (PeSTO) + retire `is_endgame`, Fair-match harness + acceptance rule |
| King safety (@branransom) | In progress | [evaluation](specs/evaluation/design.md) | Tapered foundation (PeSTO) + retire `is_endgame`, Fair-match harness + acceptance rule |
| Pawn structure (@branransom) | In progress | [evaluation](specs/evaluation/design.md) | Tapered foundation (PeSTO) + retire `is_endgame`, Fair-match harness + acceptance rule |
| Docs + cumulative measurement (@branransom) | Planned | [evaluation](specs/evaluation/design.md) | Mobility, King safety, Pawn structure |

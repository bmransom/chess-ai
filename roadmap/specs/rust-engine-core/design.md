---
title: Rust engine core — design
description: Architecture and decisions for the native Rust core behind a PyO3 seam, with a faithful-port correctness strategy.
---

> **Status:** Done (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Rust engine core — design

## Decision summary

| Decision | Choice | Why |
|---|---|---|
| Driver | Performance & strength | More nodes/sec → stronger play at the same depth. |
| Board & movegen | Hand-rolled bitboards | Highest performance ceiling and full control; the top-engine path. |
| FFI seam | PyO3 module via maturin | One coarse call per move; Python stays a thin wrapper. |
| Scope | Faithful port first | Reproduce today's eval + search; a clean, verifiable A/B baseline. |
| Position state | Rust owns it | `python-chess` drops entirely; Python is genuinely thin. |
| `GET /decision_tree` | Gated behind a debug flag | A fast engine should not build a debug tree every search. |
| HTTP validation | Add pydantic now | The contract already requires it and we are rewriting the boundary. |
| Sequencing | Rust port before iterative deepening (Epic 1) | Build iterative deepening once, in Rust — not twice. |

## Topology

A Cargo crate compiles to the PyO3 extension module `brandobot_core`. Python keeps
`src/communication.py` (UCI loop) and `src/api.py` (Flask) as thin wrappers that
`import brandobot_core`. The seam is coarse — one `next_move` call per move — so
Python overhead is negligible.

```
lichess-bot ─UCI─▶ main.py → communication.py ─┐
                                               ├─▶ brandobot_core  (Rust: all chess logic)
HTTP client ─JSON─▶ api.py ────────────────────┘
```

`python-chess` leaves the engine entirely. End-state runtime dependencies: the
Rust core, `flask`, `flask-cors`, `pydantic`. `python-chess` survives only as a
**test-only** differential oracle (Story 2).

## The PyO3 surface

A `Searcher` handle owns a `Board` and a `TranspositionTable`, matching the
glossary (the Searcher runs minimax to a depth and returns the best Move). All
types reuse glossary names.

```python
brandobot_core.Searcher()
  .new_game()                          # reset Board, clear TranspositionTable  (UCI `ucinewgame`)
  .set_position(fen=None, moves=[...]) # startpos (fen=None) or a FEN, then apply UCI moves
  .set_fen(fen)                        # set position directly from a FEN
  .next_move(depth, capture_tree=False) -> "g1f3"   # the best Move, UCI notation
  .fen() -> "..."                      # current position as FEN
  .transposition_table() -> [ {zobrist, best_move, depth, value, flag, age}, ... ]
  .decision_tree() -> dict | None      # the last search's tree, only if capture_tree was set

brandobot_core.perft(fen, depth) -> int   # module function; movegen gate + benchmark
```

The UCI null move `(none)` is returned when no legal move exists (AC-1.3).

## Crate layout — mirrors the glossary entity model

| Module | Owns | Glossary type |
|---|---|---|
| `board` | 12 piece bitboards + occupancy, side to move, castling rights, en-passant square, halfmove/fullmove clocks; FEN parse/format; make/unmake; incremental Zobrist | `Board`, `Move` |
| `movegen` | magic-bitboard rook/bishop attacks; knight/king/pawn attack tables; legal move generation; `perft` | — |
| `eval` | piece values + piece-square tables ported verbatim from `src/evaluate.py`; `value()`, `is_endgame` | — |
| `movesort` | checks → MVV-LVA captures → quiet-by-position-value | `MoveSorter` |
| `tt` | Zobrist-keyed array; replace-by-depth-and-age | `TranspositionTable`, `HashEntry`, `Flag` |
| `search` | negamax + alpha-beta + quiescence + TT; fixed depth + endgame depth boost | `Searcher` |
| `ffi` | PyO3 bindings — the `Searcher` class and `perft` | — |

## Correctness strategy — the spine

Hand-rolled move generation is the classic bug-nest, so every gate is independent
ground truth, never self-check:

1. **Perft suite (the movegen gate).** The six canonical Chess Programming Wiki
   positions to their *published* node counts at depth. No code above `movegen` is
   trusted until all pass. The published numbers are the oracle — not the engine.
2. **Differential vs `python-chess`.** For many random positions, assert Rust's
   legal-move set equals `python-chess`'s. A separate implementation, so the check
   is genuine, not circular.
3. **make/unmake invariants.** After make then unmake, the Board (including
   Zobrist key) equals its prior state byte-for-byte.
4. **Eval parity.** Verbatim piece-square tables → the existing `value() == -290`
   test passes, plus golden values sampled from the current Python evaluation.
5. **Tactical parity.** The four existing `next_move` tests — mate-in-1 `f8f7`,
   escape `h7h8`, mate-in-3 `f6a6`, don't-hang-rook `≠ e1e8` — run against the
   Rust Searcher. Forced lines any correct engine must reproduce.
6. **TT parity.** The four existing replacement tests, re-expressed in Rust.

## Behavioral contracts (feature files)

`next_move` becomes an **outcome contract**: a position yields a legal Move,
exercised by both the UCI runner and the HTTP runner. The existing
`engine.feature` (`uci` → `uciok`) stays; new Scenarios cover `position`+`go` →
`bestmove` and `POST /next_move` → a legal move. Each Scenario precedes its
wrapper code.

## Build & gate

`maturin` builds the extension into the project virtualenv. `scripts/check-fast.sh`
and CI gain a Rust stage before the Python stage:

```
cargo fmt --check  →  cargo clippy -D warnings  →  cargo test  →  maturin develop
        →  ruff  →  pytest  →  knowledge check
```

Rust stable (via `rustup`) becomes a documented dev prerequisite. `src/perft.py`
becomes a thin caller of `brandobot_core.perft`, retained as the benchmark for
AC-1.4.

## Sequencing

This epic lands before Epic 1 ("Iterative deepening with principal variation").
Epic 1's three cards then build on the Rust Searcher rather than the Python one —
iterative deepening, PV reporting, and time-managed `go` are written once, in Rust.

## Glossary additions

New canonical terms, each recording Chess Programming Wiki (CPW) provenance:

| Term | Definition | Provenance |
|---|---|---|
| Bitboard | A 64-bit word with one bit per square, encoding a piece set | CPW "Bitboards" |
| Magic bitboard | Perfect-hash lookup of sliding-piece attacks by a `(blockers × magic)` index | CPW "Magic Bitboards" |
| Negamax | Minimax reformulation where each node negates the child score; refines the glossary's Minimax | CPW "Negamax" |
| Make/unmake | Apply a Move, then reverse it to restore the prior Board, with incremental Zobrist | CPW "Make Move" / "Unmake Move" |
| Piece-square table | Per-piece, per-square positional bonus added to material in evaluation | CPW "Piece-Square Tables" |
| `brandobot_core` | The Rust engine core exposed to Python as a PyO3 module | this repo |

Existing entities (Board, Move, Searcher, TranspositionTable, HashEntry, Flag,
MoveSorter) keep their names as the Rust types.

## Alternatives considered

- **Keep `python-chess` for movegen, port only search.** Rejected: the search
  loop crosses the FFI boundary at every node (generate, push, pop), and that
  marshalling would erase the speedup the port exists to deliver.
- **A fast Rust crate (`cozy-chess` / `shakmaty`) for the board.** A lower-risk
  route, but the maintainer chose hand-rolled bitboards for the higher ceiling
  and full control.
- **Standalone UCI binary + subprocess seam.** Rejected: the Flask path would pay
  IPC per request and we would maintain a UCI client in Python; the PyO3 module is
  a single, thinner seam.
- **Fold in strength upgrades now.** Deferred: mixing new heuristics into the port
  destroys the clean A/B baseline that makes the port verifiable.

## Risks

| Risk | Mitigation |
|---|---|
| Movegen bugs in hand-rolled bitboards | Perft suite + `python-chess` differential gate the whole stack before search. |
| Eval drift from the Python original | Golden-value parity test against `src/evaluate.py`. |
| Rust toolchain in CI / contributor setup | Document the prerequisite; pin a toolchain; cache the build. |
| Maturin build friction in the gate | `maturin develop` runs in the gate; a broken build fails fast and locally. |

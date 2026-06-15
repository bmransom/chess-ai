---
title: Rust engine core — tasks
description: Waved implementation plan for the native Rust core; each task names the gate that proves it.
---

> **Status:** Done (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Rust engine core — tasks

Tasks within a wave are independent; each wave builds on the last. Every task
names its gate. The movegen gate (Wave 2) precedes all search work — nothing
above `movegen` is trusted until perft passes.

## Wave 0 — Walking skeleton

- **0.1 Scaffold the crate.** Create the Cargo crate, PyO3 binding, and maturin
  build config; expose a `Searcher` whose `next_move` returns any legal move and a
  `perft` stub. *Gate: `maturin develop` builds; `import brandobot_core` succeeds.*
- **0.2 Wire the gate.** Extend `scripts/check-fast.sh` and CI with the Rust
  stage (`cargo fmt --check`, `cargo clippy -D warnings`, `cargo test`, `maturin
  develop`) before the Python stage. *Gate: `scripts/check-fast.sh` runs the Rust
  steps and still passes.*

## Wave 1 — Board & Zobrist

- **1.1 Bitboard Board + FEN.** Piece bitboards, occupancy, side, castling rights,
  en-passant square, clocks; FEN parse and format. *Gate: FEN round-trip unit
  tests over a position suite (parse → format is identity).*
- **1.2 make/unmake + incremental Zobrist.** Apply and reverse moves, maintaining
  the Zobrist key incrementally. *Gate: AC-2.3 — make then unmake restores the
  Board and Zobrist key; incremental key equals a from-scratch recompute.*

## Wave 2 — Move generation & perft (the movegen gate)

- **2.1 Attack tables.** Knight, king, and pawn attack tables; magic-bitboard rook
  and bishop attacks. *Gate: attack-set unit tests against known masks.*
- **2.2 Legal move generation.** Pins, checks, castling, en passant, promotions.
  *Gate: AC-2.1 — perft matches published counts for the six CPW positions.*
- **2.3 Differential oracle.** Compare Rust legal-move sets to `python-chess` over
  random positions (test-only dependency). *Gate: AC-2.2 — move sets equal.*

## Wave 3 — Evaluation

- **3.1 Port eval verbatim.** Piece values and piece-square tables from
  `src/evaluate.py`; `value()` and `is_endgame`. *Gate: AC-3.1 `value() == -290`,
  AC-3.3 endgame detection, and AC-3.2 golden-value parity vs the Python eval.*

## Wave 4 — Move ordering

- **4.1 MoveSorter.** Checks → MVV-LVA captures → quiet-by-position-value; the
  quiescence subset (checks + captures). *Gate: ordering unit tests — a position
  yields the expected move order.*

## Wave 5 — Transposition table

- **5.1 TT + HashEntry + Flag.** Zobrist-keyed array with replace-by-depth-and-age.
  *Gate: AC-4.1–4.4 — the four replacement tests, re-expressed in Rust.*

## Wave 6 — Search

- **6.1 Searcher.** negamax + alpha-beta + quiescence + TT lookup/store; fixed
  depth + endgame depth boost; `(none)` on no legal move. *Gate: AC-1.1–1.3 and
  the four tactical `next_move` tests against the Rust Searcher.*

## Wave 7 — UCI wrapper

- **7.1 Scenarios first.** Add `position`+`go` → `bestmove` to `features/`
  (outcome contract) before touching the wrapper. *Gate: Scenario exists and fails.*
- **7.2 Wire `communication.py` to Rust.** `position`/`ucinewgame`/`go` delegate to
  `Searcher`; Rust owns position state. *Gate: AC-5.1–5.3 — acceptance Scenarios
  pass through the real UCI engine.*

## Wave 8 — Flask wrapper

- **8.1 Scenario first.** Add `POST /next_move` → a legal Move (outcome contract,
  HTTP runner). *Gate: Scenario exists and fails.*
- **8.2 pydantic models + wire `api.py`.** Validated `POST /next_move`;
  `GET /transposition_table` from `Searcher.transposition_table()`;
  `GET /decision_tree` debug-gated. *Gate: AC-6.1–6.5 — API tests (valid FEN →
  move; bad FEN → 422; TT endpoint; tree gated to 404 when absent).*

## Wave 9 — Cutover & docs

- **9.1 Remove python-chess.** Drop it (and now-unused numpy) from engine and
  wrapper runtime imports; keep it test-only. *Gate: AC-7.1 — a test asserts no
  `import chess` in engine/wrapper modules; full gate PASS.*
- **9.2 Benchmark.** Record AC-1.4 — `perft(startpos, 5)` Rust vs the Python
  baseline. *Gate: benchmark recorded in the spec / a knowledge note.*
- **9.3 Docs & board.** Update `knowledge/glossary.md` (new terms + provenance),
  add an architecture concept for the seam, update `CLAUDE.md`/`AGENTS.md` commands
  (Rust toolchain, maturin), move the board card to Done. *Gate: `python3
  scripts/knowledge.py check` clean; recorded gate PASS.*

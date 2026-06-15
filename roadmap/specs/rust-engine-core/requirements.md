---
title: Rust engine core — requirements
description: User stories and EARS acceptance criteria for porting the engine core to Rust behind a PyO3 seam.
---

> **Status:** Done (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Rust engine core — requirements

Port the move-picking core — Board, move generation, evaluation, MoveSorter,
TranspositionTable, and Searcher — from Python to a native Rust crate exposed to
Python as the `brandobot_core` module (PyO3, built with maturin). Python keeps
only the UCI loop and the Flask API as thin wrappers.

This first spec is a **faithful port**: the Rust core reproduces today's
evaluation and search exactly; strength comes from native speed, not new
heuristics. Iterative deepening, principal variation, and time management stay
deferred to Epic 1, which re-targets the Rust Searcher once this lands.

## Story 1 — Native move selection

As the engine maintainer, I want move selection to run in Rust so the Searcher
explores far more nodes per second and returns stronger moves at the same depth.

- AC-1.1 WHEN `Searcher.next_move(depth)` is called on a set position, THE SYSTEM SHALL return a legal Move for the side to move in UCI long algebraic notation.
- AC-1.2 WHEN the position has a forced mate within `depth` plies, THE SYSTEM SHALL return a mating Move.
- AC-1.3 WHEN the position has no legal move, THE SYSTEM SHALL return the UCI null move `(none)`.
- AC-1.4 WHEN `perft(startpos, 5)` runs, THE SYSTEM SHALL complete at least 10× faster than the `src/perft.py` Python baseline on the same machine. *(target benchmark, recorded — not a blocking gate)*

## Story 2 — Independently verified move generation

As the maintainer, I want move generation validated against ground truth that
shares no code with the engine, so I can trust every search built on it.

- AC-2.1 WHEN `perft(fen, depth)` runs on each of the six canonical Chess Programming Wiki positions (startpos, Kiwipete, positions 3–6), THE SYSTEM SHALL return exactly the published node count at each tested depth.
- AC-2.2 WHEN a randomly generated legal position is enumerated, THE SYSTEM SHALL produce a legal-move set equal to `python-chess`'s for that position. *(differential oracle; test-only dependency)*
- AC-2.3 WHEN a Move is made and then unmade, THE SYSTEM SHALL restore the Board — including castling rights, en-passant square, clocks, and Zobrist key — to its exact prior state.

## Story 3 — Evaluation parity

As the maintainer, I want the Rust evaluation to match the current Python
evaluation exactly, so any change in play is attributable to search depth alone.

- AC-3.1 WHEN `value()` evaluates `5k2/8/4p3/4Np2/3P4/7r/P3p3/6K1 b - - 0 1`, THE SYSTEM SHALL return `-290`.
- AC-3.2 WHEN evaluating any position in a sampled parity set, THE SYSTEM SHALL return the same centipawn value as `src/evaluate.py`, using the same piece values and piece-square tables.
- AC-3.3 WHEN, for each side, that side has no queen or has at most one minor piece, THE SYSTEM SHALL report `is_endgame` true and evaluate the king with the endgame piece-square table — matching `Board.__is_endgame` in `src/board.py` exactly.

## Story 4 — Transposition-table parity

As the maintainer, I want the Rust TranspositionTable to keep the current
replace-by-depth-and-age policy, so search results stay stable.

- AC-4.1 WHEN a HashEntry is stored into an empty slot, THE SYSTEM SHALL return it on lookup by matching Zobrist key and sufficient depth.
- AC-4.2 WHEN a new HashEntry has greater age than the stored entry, THE SYSTEM SHALL replace it.
- AC-4.3 WHEN a new HashEntry has equal age and greater depth, THE SYSTEM SHALL replace it.
- AC-4.4 WHEN a new HashEntry has equal age and lesser depth, THE SYSTEM SHALL keep the stored entry.

## Story 5 — UCI wrapper stays thin

As a bridge (lichess-bot, a GUI, the acceptance harness), I want the UCI contract
unchanged, so nothing downstream breaks.

- AC-5.1 WHEN the engine receives `uci`, THE SYSTEM SHALL reply `uciok`.
- AC-5.2 WHEN the engine receives a `position` command then `go`, THE SYSTEM SHALL reply `bestmove <move>` computed by `brandobot_core`.
- AC-5.3 WHEN the engine accepts UCI commands, THE SYSTEM SHALL recognize exactly `uci`, `isready`, `ucinewgame`, `position`, `go`, `quit`.

## Story 6 — HTTP API contract with validation

As an API client, I want `POST /next_move` validated and the introspection
endpoints preserved, so the JSON contract is trustworthy.

- AC-6.1 WHEN `POST /next_move` receives `{fen}`, THE SYSTEM SHALL validate the body with pydantic and respond `{move}`.
- AC-6.2 WHEN `POST /next_move` receives a malformed or illegal FEN, THE SYSTEM SHALL respond `422` with a validation error.
- AC-6.3 WHEN `GET /transposition_table` is called, THE SYSTEM SHALL respond with the current TranspositionTable entries.
- AC-6.4 WHEN `GET /decision_tree` is called after a search captured a tree, THE SYSTEM SHALL respond with that tree.
- AC-6.5 WHEN `GET /decision_tree` is called and no search captured a tree, THE SYSTEM SHALL respond `404`.

## Story 7 — python-chess removed from the engine

As the maintainer, I want the engine free of `python-chess`, so the Rust core is
the single source of chess logic.

- AC-7.1 WHEN the port is complete, THE SYSTEM SHALL NOT import `python-chess` in any engine or wrapper module, enforced by a test.

## Story 8 — The gate covers Rust

As the maintainer, I want the canonical gate to build and test the Rust core, so
a broken core cannot merge.

- AC-8.1 WHEN `scripts/check-fast.sh` runs, THE SYSTEM SHALL run `cargo fmt --check`, `cargo clippy`, `cargo test`, and `maturin develop` before the Python checks, failing the gate if any fails.

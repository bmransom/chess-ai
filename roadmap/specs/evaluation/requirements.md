---
title: Evaluation — requirements
description: User stories and EARS acceptance criteria for tapered evaluation (PeSTO) with mobility, king safety, and pawn structure.
---

> **Status:** Planned (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Evaluation — requirements

Replace the material-plus-piece-square evaluation with a tapered evaluation: a
game phase blends a middlegame and an endgame score, built on PeSTO's tuned
tables, then mobility, king safety, and pawn-structure terms. The binary
`is_endgame` flag is retired. Each term's contribution is measured against the
prior build with the strength harness, not assumed. Depends on iterative deepening
and the strength harness (both on `main`).

## Story 1 — Tapered evaluation

As the engine, I want a phase-blended evaluation, so strength scales smoothly from
opening to endgame.

- AC-1.1 WHEN evaluating a position, THE SYSTEM SHALL compute a game phase from the remaining non-pawn material, from 0 (bare kings) to 24 (the full set).
- AC-1.2 WHEN evaluating, THE SYSTEM SHALL blend the middlegame and endgame scores by the phase: `(mg·phase + eg·(24 − phase)) / 24`.
- AC-1.3 WHEN evaluating material and placement, THE SYSTEM SHALL use PeSTO's middlegame and endgame piece values and piece-square tables.
- AC-1.4 WHEN evaluating the start position, THE SYSTEM SHALL return 0.
- AC-1.5 WHEN a position is color-mirrored, THE SYSTEM SHALL return the negation of the original position's evaluation.

## Story 2 — Mobility

As the engine, I want piece mobility valued, so active pieces score higher.

- AC-2.1 WHEN evaluating, THE SYSTEM SHALL add a mobility term scoring each knight, bishop, rook, and queen by its count of available squares, with middlegame and endgame weights.
- AC-2.2 WHEN one side's pieces have more available squares, all else equal, THE SYSTEM SHALL score that side higher.

## Story 3 — King safety

As the engine, I want king safety valued, so exposed kings are penalized.

- AC-3.1 WHEN evaluating, THE SYSTEM SHALL add a king-safety term for each king's pawn shield and the enemy pieces attacking its surrounding squares.
- AC-3.2 WHEN a king's shield pawns are advanced or missing, all else equal, THE SYSTEM SHALL score that king less safe than with the shield intact.

## Story 4 — Pawn structure

As the engine, I want pawn structure valued, so weak and strong pawns are scored.

- AC-4.1 WHEN evaluating, THE SYSTEM SHALL penalize doubled and isolated pawns and reward passed pawns, with middlegame and endgame weights.
- AC-4.2 WHEN a side has a passed pawn, all else equal, THE SYSTEM SHALL score that side higher than without it.

## Story 5 — Correctness preserved

As the maintainer, I want the search still sound, so the eval change adds strength
without breaking tactics.

- AC-5.1 WHEN searched to depth 3, THE SYSTEM SHALL return the mating moves `f8f7`, `h7h8`, and `f6a6` for the three mate puzzles.
- AC-5.2 WHEN the non-mate puzzle's searched move changes under the new evaluation, THE SYSTEM SHALL record the changed move.
- AC-5.3 WHEN move generation or perft runs, THE SYSTEM SHALL be unaffected by the eval change.

## Story 6 — Measured strength

As the maintainer, I want each term verified, so we keep only the terms that help.

- AC-6.1 WHEN a term is added, THE SYSTEM SHALL measure its Elo against the immediately preceding build with `selfplay.py` and record the result.

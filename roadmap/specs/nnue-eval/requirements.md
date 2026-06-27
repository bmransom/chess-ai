---
title: NNUE evaluation — requirements
description: User stories and EARS acceptance criteria for a borrowed NNUE evaluation — a 768 perspective network trained on self-play, behind a flag, measured by SPRT against the PeSTO build.
---

> **Status:** Planned (2026-06-26) — tracked on the [board](../../ROADMAP.md).

# NNUE evaluation — requirements

Add a learned evaluation: an NNUE (Efficiently Updatable Neural Network) that
replaces the tapered PeSTO score inside the existing alpha-beta search. Borrow a
proven architecture rather than invent one — the simplest viable modern net: a
**768 perspective network** (`(768 → 256)×2 → 1`), trained with the **bullet**
trainer on self-play positions **labeled by a teacher engine** (Stockfish eval —
knowledge distillation), quantized to integers, and updated
incrementally on make/unmake. The net stays ours — our architecture, our weights;
only the training signal is borrowed. The new path sits behind a flag; the PeSTO
evaluation stays as the fallback and the SPRT baseline. The net ships only if a
fair-match SPRT shows it beats PeSTO. Depends on the evaluation epic, the
fair-match harness, and self-play (all on `main`).

## Story 1 — Borrowed network and inference

As the engine, I want a learned static evaluation, so positional judgment comes
from data instead of hand-tuned tables.

- AC-1.1 WHEN evaluating a position, THE SYSTEM SHALL compute the score with a perspective network over the 768 piece-square feature set (piece type × color × square), with paired side-to-move and not-to-move accumulators of equal width concatenated before the output.
- AC-1.2 WHEN computing the network output, THE SYSTEM SHALL apply a squared clipped-ReLU activation clamped to `[0, QA]` to each accumulator, then a single output neuron.
- AC-1.3 WHEN producing a centipawn score, THE SYSTEM SHALL dequantize by `SCALE / (QA·QB)` and return a White-positive score, matching the existing `evaluate` sign convention so the search call site is unchanged.
- AC-1.4 WHEN loading a network, THE SYSTEM SHALL read a quantized little-endian network file and reject a file whose header or layer dimensions do not match the compiled architecture.
- AC-1.5 WHEN a color-mirrored position with the side to move swapped is evaluated, THE SYSTEM SHALL return the negation of the original — an antisymmetry the perspective design guarantees by construction.

## Story 2 — Borrowed trainer and self-play data

As the maintainer, I want a reproducible training pipeline, so the net can be
regenerated and improved.

- AC-2.1 WHEN building a training set, THE SYSTEM SHALL draw positions from self-play games and label each with a teacher engine's evaluation (Stockfish, at a fixed depth or node budget), optionally blended with the game result (WDL).
- AC-2.2 WHEN selecting a position for training, THE SYSTEM SHALL exclude non-quiet positions (in check or with a pending capture), so the target matches a static evaluation.
- AC-2.3 WHEN labeling, THE SYSTEM SHALL provision the teacher engine reproducibly (a fetch step, as with the opening book) and record its identity, version, and per-position budget.
- AC-2.4 WHEN training, THE SYSTEM SHALL use the bullet trainer over a bulletformat dataset and export a quantized network whose `QA`, `QB`, and `SCALE` match the inference constants.

## Story 3 — Incremental accumulator

As the engine, I want the accumulator updated incrementally, so the learned
evaluation is fast enough for alpha-beta.

- AC-3.1 WHEN a move is made, THE SYSTEM SHALL update each accumulator by adding and subtracting only the changed piece-square features, not recomputing from scratch.
- AC-3.2 WHEN a move is unmade, THE SYSTEM SHALL restore the accumulator to its exact pre-move value.
- AC-3.3 WHEN the incremental accumulator is compared against a full refresh for every position reached in a self-play game, THE SYSTEM SHALL produce identical values.

## Story 4 — Correctness preserved

As the maintainer, I want the new path isolated, so it adds strength without
breaking the engine.

- AC-4.1 WHEN the NNUE evaluation is disabled, THE SYSTEM SHALL use the existing tapered (PeSTO) evaluation, unchanged.
- AC-4.2 WHEN move generation or perft runs, THE SYSTEM SHALL be unaffected by the NNUE path.
- AC-4.3 WHEN the forced tactical puzzles are searched under the NNUE evaluation, THE SYSTEM SHALL still resolve them, or record any changed move.

## Story 5 — Measured strength

As the maintainer, I want the net verified, so we ship it only if it helps.

- AC-5.1 WHEN the NNUE build is compared against the PeSTO build, THE SYSTEM SHALL run a fair-match SPRT with `sprt.py` and record the verdict; the net ships only on a pass.

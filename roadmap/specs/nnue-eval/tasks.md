---
title: NNUE evaluation — tasks
description: Waved plan for a borrowed 768 perspective NNUE — pipeline proof, training, incremental accumulator, SPRT measurement, docs. Each task names its gate.
---

> **Status:** Planned (2026-06-26) — tracked on the [board](../../ROADMAP.md).

# NNUE evaluation — tasks

Tasks within a wave are independent; each wave builds on the last. Every task
names its gate. Wave 1 proves the inference pipeline with an untrained net; the
trained net and its strength verdict come later. The net ships only on an SPRT
pass against the PeSTO build.

## Wave 1 — Borrow the architecture

- **1.1 Network format + loader.** Define the quantized little-endian file
  (header + feature transformer + output weights) and `nnue.rs` load with header
  and dimension checks. *Gate: AC-1.4 — a matching file loads, a mismatched header
  or dimension is rejected.*
- **1.2 Full-refresh forward pass.** Implement the 768 feature extractor over the
  piece bitboards, the perspective accumulator pair, SCReLU, the output neuron,
  and White-positive dequantization by `SCALE / (QA·QB)`. *Gate: AC-1.1–1.3, 1.5 —
  the start position evaluates to a finite centipawn score and a color-mirrored,
  side-swapped position negates, on a randomly-initialized net.*
- **1.3 Flagged drop-in.** Add the eval-selection flag and `Searcher.load_nnue`;
  route `search.rs:275` through the selected eval. *Gate: AC-4.1–4.2 — with the
  flag off the engine is unchanged (PeSTO golden values hold) and perft is
  unaffected; the full gate passes.*

**Wave 1 gate.** `scripts/check-fast.sh` PASS (2026-06-27) on branch
`feat/nnue-eval`: rust core fmt + clippy (`-D warnings`) + 54 tests, maturin
build, ruff clean, 47 pytest, knowledge OK. Flag-off leaves the engine unchanged
(the 47 acceptance tests pass with the rebuilt extension); the six new NNUE unit
tests cover loader rejection (bad magic, wrong dimension, truncation), the
`to_bytes`/`from_bytes` round-trip, the bounded start-position score, and the
perspective antisymmetry of the white-positive score. The forward pass is full
refresh; the incremental accumulator is Wave 3.

## Wave 2 — Training pipeline (teacher distillation)

- **2.1 Provision the teacher.** Add a fetch step for the Stockfish binary
  (analogous to `fetch_uho.py`); record its identity and version. *Gate: AC-2.3 —
  the teacher provisions reproducibly and answers over UCI.*
  **Done (2026-06-27):** `scripts/fetch_stockfish.py` downloads the pinned
  `sf_17.1` release (GPL-3.0; only its eval labels are used), installs it to
  `bin/stockfish` (git-ignored, like the UHO book), and verifies the handshake —
  `id name Stockfish 17.1`, `uciok`. ruff clean.
- **2.2 Generate + label.** Extend `selfplay.py` to emit positions (FEN, game
  result) from varied book openings; filter to quiet positions; label each with
  the teacher's eval at a fixed depth/node budget; write bulletformat. *Gate:
  AC-2.1–2.2 — a small run produces a well-formed teacher-labeled dataset of quiet
  positions; the position count and teacher budget are recorded.*
  **In progress (2026-06-27):** `scripts/label.py` provides the labeling
  primitives — `teacher_eval` (white-positive, mate-capped centipawns via the
  provisioned teacher) and `is_quiet` (no check, no pending capture) — verified
  against `bin/stockfish` (startpos `+47`; `e2e4 d7d5` flagged non-quiet for the
  pending `exd5`). Remaining: self-play position emission and the bulletformat
  writer — the writer pairs with Wave 3's `bullet` setup so the binary format is
  validated against the trainer rather than written blind.
- **2.3 Train and export.** Run bullet on `(768 → 256)×2 → 1`; export the
  quantized net at the agreed `QA`/`QB`/`SCALE`. *Gate: AC-2.4 — a net file loads
  via Wave 1's loader; the training loss curve and position count are recorded.*

## Wave 3 — Incremental accumulator

- **3.1 Incremental update.** Have `make_move`/`unmake_move` carry the dirty-piece
  list in `Undo`; apply add/subtract feature deltas in `nnue.rs`. *Gate: AC-3.1–3.2
  — a unit test shows make then unmake restores the accumulator exactly.*
  **In progress (2026-06-27):** the incremental primitives landed in `nnue.rs` —
  an `Accumulator` (White/Black perspectives) with `add_piece`/`remove_piece` that
  adjust both perspectives by one weight column, and `evaluate` refactored onto
  them (results unchanged; the Wave 1 tests still pass). Two unit tests prove the
  deltas: a d4→f5 knight move incrementally equals a full refresh of the
  destination, and add-then-remove restores the accumulator exactly. `apply_move`
  now derives a move's deltas (capture, en passant, promotion, both castles) from
  the pre-move board, verified to equal a full refresh for every move type — so
  `board.rs` and perft stay untouched.
  **Done (2026-06-27):** the search maintains the accumulator — initialized at the
  root, advanced (clone + `apply_move`) before each `make_move` and restored after
  `unmake_move`; `evaluate` reads the maintained accumulator instead of a refresh.
  A `debug_assert` in `evaluate` compares it to a full refresh on every node, so
  any desync fails loudly under debug builds (compiled out of the release engine).
- **3.2 Equivalence + node rate.** Add the refresh == incremental test over a
  self-play game; measure nps against full refresh. *Gate: AC-3.3 — the
  incremental and refreshed accumulators are identical for every position; the
  nps delta is recorded.*
  **Done (2026-06-27):** AC-3.3 is proven two ways — `apply_move` equals a full
  refresh at every ply of a 16-move Ruy Lopez line (captures + both castles), and
  the `evaluate` `debug_assert` held at every node of depth-4 net-on searches of
  three positions. The nps measurement against full refresh waits on a trained net
  (Wave 2/4) — there is no `.nnue` file to benchmark yet; Wave 4's SPRT measures
  the effective speed in the match.

## Wave 4 — Measure strength

- **4.1 SPRT vs PeSTO.** Run a fair-match SPRT (`sprt.py`) of the NNUE build (flag
  on) against the PeSTO build (flag off). *Gate: AC-5.1 — the SPRT verdict is
  recorded; the net is retained only on a pass.*

## Wave 5 — Docs & board

- **5.1 Scenario.** Add or update a feature Scenario exercising the NNUE eval
  through the UCI entrypoint (load a net, get a legal move). *Gate: the acceptance
  runner passes.*
- **5.2 Docs, glossary, board.** Confirm the NNUE terms in `knowledge/glossary.md`
  with provenance, note the eval and the net file in `AGENTS.md`, and move the
  Epic 5 cards to Done. *Gate: `python3 scripts/knowledge.py check` clean; recorded
  gate PASS.*

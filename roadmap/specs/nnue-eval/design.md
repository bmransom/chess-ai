---
title: NNUE evaluation — design
description: A borrowed 768 perspective NNUE — bullet-trained on self-play, integer-quantized, incrementally updated on make/unmake, behind a flag, measured by SPRT.
---

> **Status:** Planned (2026-06-26) — tracked on the [board](../../ROADMAP.md).

# NNUE evaluation — design

## Decision summary

| Decision | Choice | Why |
|---|---|---|
| Approach | Borrow an architecture; supervised regression by distillation | Drops into the existing alpha-beta search; not AlphaZero's MCTS self-play, which would replace the search paradigm. |
| Feature set | 768 (piece type × color × square), perspective | The simplest viable modern net; no king buckets, so a king move needs no accumulator refresh. |
| Topology | `(768 → 256)×2 → 1`, squared clipped-ReLU (SCReLU) | bullet's canonical first net; one hidden width to tune later. |
| Trainer | bullet (Rust) | The most widely adopted NNUE trainer; matches the repo's Rust stack; trains in hours. |
| Training data | Self-play positions, teacher-labeled (Stockfish eval) | Distillation gives a strong first net without strong self-play — it defuses the data-quality risk. The net stays ours; only the label is borrowed, which rating lists accept (a borrowed *net* would not). |
| Quantization | `QA = 255`, `QB = 64`, `SCALE = 400`, int16 accumulator | bullet's defaults; integer math keeps make/unmake exact and fast. |
| Sign | White-positive, drop-in at the eval call | Keeps `search.rs:275` (`* perspective`) unchanged. |
| Rollout | Behind a flag; PeSTO stays as fallback and baseline | Isolates "is the net good?" and lets SPRT compare flag-off vs flag-on. |
| Verification | refresh == incremental, then fair-match SPRT | A correctness invariant for the fast path, then a strength gate. |

## The borrowed architecture

A **perspective network** over the **768** feature set. A feature is a
`(piece type, color, square)` triple — 6 × 2 × 64 = 768 binary inputs, of which
exactly the occupied squares (≤ 32) are active.

```
  768 inputs ──┬─► [stm accumulator : 256]  ─┐
  (per side)   └─► [nstm accumulator: 256]  ─┴─► concat(512) ─► output(1)
                          │                              │
                    SCReLU clamp [0, QA]            White-positive cp
```

Two accumulators share one feature transformer (the 768×256 first layer). The
side-to-move accumulator is built from features indexed in the mover's
orientation; the not-to-move accumulator from the mirrored orientation. Swapping
colors and the side to move swaps the two accumulators, so the output negates —
this is the structural antisymmetry of AC-1.5, independent of training.

**Why 768 over HalfKP.** HalfKP indexes every feature by the friendly king
square (≈ 40,960 inputs), so a king move invalidates that side's whole
accumulator and forces a refresh. The 768 set has no king index: every move is a
pure feature delta, which is the cleanest fit for brandobot's existing atomic
make/unmake. HalfKP is a later upgrade, not the first net.

## Inference and quantization

The accumulator stores int16 sums. Evaluation reads the two accumulators, applies
SCReLU (`x → clamp(x, 0, QA)²`), dots with the output weights (int32
accumulation), then dequantizes:

```
eval_cp = (output_int32 * SCALE) / (QA * QB)     // White-positive centipawns
```

`QA = 255`, `QB = 64`, `SCALE = 400` are bullet's defaults; the loader (AC-1.4)
checks them against the file header. These constants are a contract between the
trainer's export and the engine's inference — they live in one place and must
match on both sides.

## Integration map

New module `core/src/nnue.rs` owns the network, the accumulator pair, `refresh`,
and `evaluate`. The touch points in the existing core:

| Seam | Where | Change |
|---|---|---|
| Eval call | `search.rs:275` | `eval::evaluate(board)` → `self.eval_fn(board)`; NNUE returns White-positive, so `* perspective` is unchanged. |
| Feature read | `board.rs:216` `pieces()` | The extractor iterates the 12 piece bitboards with `pop_lsb()` to active feature indices. |
| Incremental update | `board.rs:280–289` `move_piece`/`add_piece`/`remove_piece` | The three atomic ops are the accumulator deltas; they emit a dirty-piece list `make_move` carries in `Undo`, applied in `nnue.rs` — board logic stays free of network knowledge. |
| Weight load | `lib.rs:305` `#[pymodule]` | New `Searcher.load_nnue(path)` and an eval-selection flag; the core has no file I/O today, so this is genuinely new surface. |

The PeSTO `eval::evaluate` stays. The flag selects the function pointer; with the
flag off the engine is byte-for-byte today's engine (AC-4.1).

## Perspective convention

The net is side-to-move relative by construction, but `nnue::evaluate` returns a
**White-positive** score — compute the stm-relative output, then negate when
Black is to move. This makes it a drop-in for `eval::evaluate` at the single call
site, where the searcher already applies `* perspective`. Minimal blast radius;
the same reason the chess-inator tutorial kept a White-centric eval.

## Training pipeline

Distillation: brandobot plays the games for position diversity, but a strong
**teacher** supplies the labels. brandobot's own search scores are too weak to be
a useful target until it is already strong — the teacher breaks that chicken-and-egg.

1. **Generate.** Play self-play games with `selfplay.py` (from varied book
   openings) for position diversity; record positions and the game result.
2. **Filter.** Drop non-quiet positions — in check or with a pending capture
   (AC-2.2) — so the regression target matches a static evaluation.
3. **Label.** Score each kept position with the teacher engine (Stockfish, fixed
   depth or node budget), optionally blended with the game's WDL by a lambda —
   bullet's standard target.
4. **Convert.** Write bulletformat (FEN + score + WDL).
5. **Train.** Run bullet on the `(768 → 256)×2 → 1` net; export the quantized
   network at the agreed `QA`/`QB`/`SCALE`.

**The teacher is new tooling.** A provisioning step fetches the Stockfish binary
(analogous to `fetch_uho.py` for the opening book), and a labeling step drives it
over UCI. The teacher's identity, version, and per-position budget are recorded
with the dataset (AC-2.3) so a net is reproducible. We ship our own net; only the
*labels* are distilled — this is how Stockfish trained its own first NNUE, and is
the line rating lists accept (a borrowed net would make brandobot a clone).

**Data volume still matters, but quality is no longer the bottleneck.** Teacher
labels make a given position budget far more effective than weak self-play scores;
the wave records the position count and the teacher budget. The dominant risk
shifts from label quality to label *throughput* — Stockfish at depth over millions
of positions is the slow step.

## Verification

- **Loader:** a mismatched header or dimension is rejected (AC-1.4); a round-trip
  of a known net loads to the expected weights.
- **Antisymmetry:** a color-mirrored, side-swapped position negates (AC-1.5);
  this holds for a randomly-initialized net, so it gates Wave 1 before any
  trained net exists.
- **refresh == incremental:** for every position in a self-play game, the
  incrementally-updated accumulator equals a full refresh (AC-3.3). This is the
  correctness invariant for the fast path — a sign or index bug in a delta breaks
  it. Integration test driving `Board` make/unmake, no mocks.
- **Tactics:** the forced puzzles still resolve under NNUE; a changed quiet move
  is recorded (AC-4.3).
- **Node rate:** the incremental path's nps is recorded against full-refresh; the
  search must stay fast enough to be worth the stronger eval.
- **Strength:** a fair-match SPRT with `sprt.py` compares the NNUE build against
  the PeSTO build (AC-5.1). Ship only on a pass.

## Naming and provenance

| Term | Definition | Provenance |
|---|---|---|
| NNUE | An efficiently updatable, quantized neural-network evaluation read inside alpha-beta | CPW "NNUE"; Nasu (shogi); Stockfish |
| Accumulator | The running first-layer pre-activation, updated incrementally per move | CPW "NNUE"; Stockfish |
| Feature transformer | The first layer mapping active input features to the accumulator | CPW "NNUE"; Stockfish |
| 768 feature set | An input feature per `(piece type, color, square)`, perspective-relative | bullet; CPW "NNUE" |
| Perspective network | Paired side-to-move / not-to-move accumulators concatenated before the output | bullet |
| Squared clipped-ReLU | The activation clamping an accumulator to `[0, QA]` then squaring | bullet; CPW "NNUE" |
| bullet | The NNUE trainer used to produce the network | `jw1912/bullet` |
| Teacher | The strong engine whose evaluation labels the training positions | Stockfish; CPW "NNUE" |
| Knowledge distillation | Training a net to predict a stronger engine's evaluation | CPW "NNUE"; Stockfish |

These are chess-engine-evaluation terms (the NNUE subdomain), within the neutral
engine's vocabulary; each names its prior art per the glossary contract.

## Alternatives considered

- **HalfKP / HalfKAv2 (Stockfish's sets).** Deferred: king-indexed, so a king
  move forces an accumulator refresh — more code for a first net. Revisit once the
  768 net proves the pipeline.
- **Roll our own architecture.** Rejected: the point is to borrow a proven one;
  novelty belongs in the data and tuning, not the topology.
- **AlphaZero-style RL self-play (policy/value net + MCTS).** Rejected: replaces
  the alpha-beta search wholesale and needs orders more compute. NNUE keeps the
  classical search and only swaps the leaf evaluation.
- **Pure self-play labels (brandobot's own search scores).** Deferred: a weak,
  data-hungry first net that loses to PeSTO until the data is huge. The right
  iteration *after* a teacher-distilled net is strong enough that its own games
  carry signal — a later epic, not the first net.
- **Warm-start from a public 768 net.** Rejected for the first net: shipping
  another engine's weights makes brandobot a derivative/clone (rating-list and GPL
  problems) for little gain. Distilling a teacher into *our* weights is the clean
  alternative.
- **Borrow a Stockfish net directly.** Rejected: its HalfKAv2_hm architecture does
  not fit our 768 net, and it would be a clone regardless.

## Risks

| Risk | Mitigation |
|---|---|
| Too little data → net loses to PeSTO | Teacher labels lift per-position signal; scale games; record the count; ship only on an SPRT pass. |
| Teacher labeling is the slow step | Fixed shallow depth/node budget per position; parallelize; record the budget so a net is reproducible. |
| Teacher version drift changes labels | Pin and record the teacher identity and version with the dataset (AC-2.3). |
| Incremental delta has a sign/index bug | The refresh == incremental equivalence test (AC-3.3) gates the fast path. |
| Quantization overflow or scale mismatch | int32 dot accumulation; the loader checks `QA`/`QB`/`SCALE` against the header. |
| NNUE slows the node rate below break-even | Incremental accumulator + SIMD-friendly layout; nps recorded; SPRT is wall-clock fair. |
| Trainer/export drift from inference | The quantization constants are one shared contract, asserted on load. |

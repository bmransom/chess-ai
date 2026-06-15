---
title: Evaluation — design
description: Tapered evaluation on PeSTO tables with mobility, king safety, and pawn structure, measured per term.
---

> **Status:** Planned (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Evaluation — design

## Decision summary

| Decision | Choice | Why |
|---|---|---|
| Foundation | Tapered eval on PeSTO tables | A proven, texel-tuned mg/eg set; smooth phase transition. |
| Phase | Non-pawn material, 0–24 | The standard; cheap to compute per position. |
| `is_endgame` | Retired | Tapering subsumes the frozen binary flag and its callers. |
| Terms | Mobility, king safety, pawn structure | The high-value positional signals beyond material. |
| Verification | Symmetry + per-term units + per-term Elo | Each term is kept only if the harness shows it helps. |

## Score and taper

Every term returns a `Score { mg: i32, eg: i32 }` from White's perspective (White
contributions positive, Black negative). `evaluate(board)` sums the terms, then
blends by the game phase:

```rust
fn evaluate(board: &Board) -> i32 {
    let s = material_placement(board) + mobility(board)
          + king_safety(board) + pawn_structure(board);
    let phase = game_phase(board);                       // 0..=24
    (s.mg * phase + s.eg * (24 - phase)) / 24            // centipawns
}
```

The searcher applies the side-to-move sign, as today.

**Game phase:** `phase = min(24, Σ piece_phase)`, with `knight = bishop = 1`,
`rook = 2`, `queen = 4` over all non-pawn pieces (24 at the full set, 0 at bare
kings). Phase is recomputed per evaluated node — today's `is_endgame` is frozen at
the search root — so the blend tracks the leaf, not the root. `game_phase` is a
popcount, so the per-node cost is negligible.

**PeSTO tables:** middlegame and endgame piece values and piece-square tables,
transcribed from PeSTO. Tables are White-oriented; Black mirrors by rank.

## Terms

- **Material + placement** — PeSTO mg/eg value and PST per piece.
- **Mobility** — for each knight, bishop, rook, queen, the count of attack squares
  not occupied by a friendly piece, times an mg/eg weight per piece type.
- **King safety** — the pawn shield in front of each king (mg-weighted), minus a
  penalty scaled by the number of enemy pieces attacking the king's ring.
- **Pawn structure** — penalties for doubled and isolated pawns, a bonus for passed
  pawns (rank-scaled, larger in the endgame). Computed from the pawn bitboards.

## Retiring `is_endgame`

Tapering replaces the binary flag; remove it everywhere it appears:

- `eval`: `value(board, is_endgame)` → `evaluate(board)`; drop `is_endgame` and the
  king-endgame table (PeSTO's eg king table covers it).
- `movesort`: `evaluate_move_value` and the quiet sort drop `is_endgame` and order
  quiets by the **middlegame** PST delta (`eval::mg_position_value`). This drops
  endgame PST awareness from quiet ordering — an efficiency tradeoff, not a
  correctness one: ordering changes the node count, never the search result.
- `search`: drop the `is_endgame` field and the frozen-root logic; call
  `evaluate(board)` directly.
- `lib`: drop the `is_endgame` pyfunction; the `evaluate(fen)` pyfunction calls the
  new core `evaluate(board)` (the renamed `value`).
- `communication.py`: drop the bare-`go` endgame depth boost (time management and
  tapering supersede it); bare `go` searches the default depth.

## Verification

- **Invariants:** the start position evaluates to 0 (AC-1.4); a color-mirrored
  position negates (AC-1.5); `game_phase` is 24 at the start and 0 for bare kings.
  These re-run after every term wave — a term with a sign or symmetry bug breaks
  them.
- **Per term:** a crafted position isolates each term (a doubled/isolated/passed
  pawn, a cramped vs free piece, an exposed vs sheltered king) and asserts the sign.
- **Tactics:** the three mate puzzles still resolve; the no-sacrifice puzzle may
  change move and is recorded.
- **Retired:** the eval-parity tests (`value() == -290`, the Python golden values)
  go — they pinned the *port* eval, which this epic deliberately replaces.
- **Strength:** each wave builds the candidate against the prior build and runs
  `selfplay.py`; the Elo delta is recorded. A flat term is dropped, not shipped.

## Naming and provenance

| Term | Definition | Provenance |
|---|---|---|
| Tapered evaluation | Phase-weighted blend of a middlegame and an endgame score | CPW "Tapered Eval" |
| Game phase | A 0–24 measure of remaining non-pawn material | CPW "Tapered Eval" |
| PeSTO | A public texel-tuned mg/eg piece-value and PST set | CPW "PeSTO's Evaluation Function" |
| Mobility | Score for a piece's count of available squares | CPW "Mobility" |
| King safety | Score for a king's shelter and the attackers near it | CPW "King Safety" |
| Passed pawn | A pawn with no enemy pawns ahead on its or adjacent files | CPW "Passed Pawn" |
| Isolated pawn | A pawn with no friendly pawn on an adjacent file | CPW "Isolated Pawn" |
| Doubled pawn | Two friendly pawns on the same file | CPW "Doubled Pawn" |
| Score | A paired middlegame/endgame value, summed per term and tapered | Stockfish `make_score` / `Score` |

Internal names stay expressive (`game_phase`, `mobility`, `king_safety`,
`pawn_structure`). The `Endgame` glossary entry is retired with the flag, and the
Board entity-model line changes from `value()`/`is_endgame` to `evaluate()`.

## Alternatives considered

- **Taper our existing hand-picked PSTs.** Rejected: weakly tuned; PeSTO is a
  proven, public, much stronger starting point.
- **Texel-tune our own weights.** Deferred: needs a labeled dataset and a tuner;
  a candidate later epic once the term set is settled.
- **Keep the binary `is_endgame`.** Rejected: it is the hack tapering removes.
- **All terms unmeasured, one shot.** Rejected: the killers+history epic showed a
  textbook term can be flat; measure each.

## Risks

| Risk | Mitigation |
|---|---|
| A term is flat or negative (per killers+history) | Measure each with the harness; drop a flat term. |
| Eval slows the node rate | Keep terms bitboard-based; mobility/king-safety reuse attack tables. |
| Tactics shift under the new eval | The three mate puzzles guard correctness; a changed quiet move is recorded. |
| PeSTO transcription error | The symmetry and mirror invariants catch a mistyped table. |

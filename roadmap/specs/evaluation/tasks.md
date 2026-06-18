---
title: Evaluation — tasks
description: Waved plan for tapered evaluation and the positional terms; each task names its gate, and each term is measured.
---

> **Status:** In progress (2026-06-17) — tracked on the [board](../../ROADMAP.md).

# Evaluation — tasks

Tasks within a wave are independent; each wave builds on the last. Every task names
its gate. Each term wave ends with a strength measurement against the prior build;
a flat term is dropped, not shipped.

## Wave 1 — Tapered foundation

- **1.1 Score + game phase + PeSTO.** Add `Score { mg, eg }`, `game_phase`, the
  PeSTO mg/eg values and tables, and `evaluate(board)` with the tapered blend.
  *Gate: AC-1.1–1.5 — start position evaluates to 0, a mirror negates, phase is 24
  at the start and 0 for bare kings.*
- **1.2 Retire `is_endgame`.** Remove the flag from `eval`, `movesort` (order quiets
  by the mg PST), `search`, `lib`, and the bare-`go` boost in `communication.py`;
  retire the eval-parity tests. *Gate: AC-5.1–5.3 — the forced tactical puzzles
  resolve, the threatened-mate position's PeSTO shift (`f8f7` → `f5g6`) is
  recorded, and perft and the full gate pass.*
- **1.3 Measure the foundation.** Build the candidate against `main` and run
  `selfplay.py`. *Gate: AC-6.1 — the Elo delta is recorded.*

**Wave 1 measurement.** Candidate `feat/evaluation` against `main` commit
`5de5293`, with engine stderr suppressed, `--games 16 --depth 4 --max-moves 80
--progress move`: `engine1 vs engine2: +2 -1 =13, 53.1%, Elo +22 ± 73`.
The progress stream showed active move completion throughout the match.

**Wave 1 gate.** `scripts/check-fast.sh` PASS (2026-06-17).

## Wave 2 — Mobility

- **2.1 Mobility term.** Score knight/bishop/rook/queen available-square counts with
  mg/eg weights, reusing the attack tables. *Gate: AC-2.1–2.2 — a unit test shows the
  freer side scores higher; AC-1.4–1.5 still hold (start evaluates to 0, a mirror
  negates).*
- **2.2 Measure mobility.** Match the candidate against the Wave 1 build; record the
  Elo delta; keep the term only if it helps. *Gate: AC-6.1.*

**Wave 2 measurement.** Candidate mobility weights `mg N/B/R/Q = 4/4/2/1`,
`eg N/B/R/Q = 4/5/4/2`, against Wave 1 commit `01b4f15`, with engine stderr
suppressed, `--games 16 --depth 4 --max-moves 80 --progress game`:
`engine1 vs engine2: +1 -1 =14, 50.0%, Elo -0 ± 60`. The term did not show a
gain and was dropped; no mobility code is retained.

**Wave 2 gate.** `scripts/check-fast.sh` PASS (2026-06-17).

## Wave 3 — King safety

- **3.1 King-safety term.** Score the pawn shield and the attackers on the king ring,
  mg-weighted. *Gate: AC-3.1–3.2 — a unit test shows an exposed king scores worse;
  AC-1.4–1.5 still hold.*
- **3.2 Measure king safety.** Match against the Wave 2 build; record the Elo delta.
  *Gate: AC-6.1.*

**Wave 3 measurement.** Candidate king-safety weights `shield = +12 mg per pawn`,
`ring attack mg P/N/B/R/Q = 4/10/10/14/24`, against pre-king-safety commit
`180f875`, with engine stderr suppressed, `--games 16 --depth 4 --max-moves 80
--progress game`: `engine1 vs engine2: +2 -1 =13, 53.1%, Elo +22 ± 73`.
The signal is weak but positive, so the term is retained.

**Wave 3 gate.** `scripts/check-fast.sh` PASS (2026-06-17).

## Wave 4 — Pawn structure

- **4.1 Pawn-structure term.** Penalize doubled and isolated pawns; reward passed
  pawns, rank-scaled and larger in the endgame. *Gate: AC-4.1–4.2 — a unit test shows
  a passed pawn and the doubled/isolated penalties; AC-1.4–1.5 still hold.*
- **4.2 Measure pawn structure.** Match against the Wave 3 build; record the Elo
  delta. *Gate: AC-6.1.*

**Wave 4 measurement.** Candidate pawn-structure weights `doubled mg/eg = 10/12`,
`isolated mg/eg = 12/10`, `passed mg by rank = 0/5/10/18/30/48/72/0`,
`passed eg by rank = 0/12/24/40/64/96/140/0`, against pre-pawn-structure commit
`ae97dbd`, with engine stderr suppressed, `--games 16 --depth 4 --max-moves 80
--progress game`: `engine1 vs engine2: +1 -1 =14, 50.0%, Elo -0 ± 60`.
The term did not show a gain and was dropped; no pawn-structure code is retained.

**Wave 4 gate.** `scripts/check-fast.sh` PASS (2026-06-18).

## Wave 5 — Docs & cumulative measurement

- **5.1 Cumulative match.** Run the full candidate against `main`; record the total
  Elo gain. *Gate: AC-6.1 — the cumulative delta is recorded in the PR.*
- **5.2 Docs & board.** Add the later positional terms to `knowledge/glossary.md`
  with provenance, note the eval in `AGENTS.md`, and move the Epic 4 cards to Done.
  *Gate: `python3 scripts/knowledge.py check` clean; recorded gate PASS.*

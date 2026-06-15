---
title: Evaluation — tasks
description: Waved plan for tapered evaluation and the positional terms; each task names its gate, and each term is measured.
---

> **Status:** Planned (2026-06-15) — tracked on the [board](../../ROADMAP.md).

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
  retire the eval-parity tests. *Gate: AC-5.1–5.3 — the three mate puzzles resolve,
  the changed non-mate move is recorded, and perft and the full gate pass.*
- **1.3 Measure the foundation.** Build the candidate against `main` and run
  `selfplay.py`. *Gate: AC-6.1 — the Elo delta is recorded.*

## Wave 2 — Mobility

- **2.1 Mobility term.** Score knight/bishop/rook/queen available-square counts with
  mg/eg weights, reusing the attack tables. *Gate: AC-2.1–2.2 — a unit test shows the
  freer side scores higher.*
- **2.2 Measure mobility.** Match the candidate against the Wave 1 build; record the
  Elo delta; keep the term only if it helps. *Gate: AC-6.1.*

## Wave 3 — King safety

- **3.1 King-safety term.** Score the pawn shield and the attackers on the king ring,
  mg-weighted. *Gate: AC-3.1–3.2 — a unit test shows an exposed king scores worse.*
- **3.2 Measure king safety.** Match against the Wave 2 build; record the Elo delta.
  *Gate: AC-6.1.*

## Wave 4 — Pawn structure

- **4.1 Pawn-structure term.** Penalize doubled and isolated pawns; reward passed
  pawns, rank-scaled and larger in the endgame. *Gate: AC-4.1–4.2 — a unit test shows
  a passed pawn and the doubled/isolated penalties.*
- **4.2 Measure pawn structure.** Match against the Wave 3 build; record the Elo
  delta. *Gate: AC-6.1.*

## Wave 5 — Docs & cumulative measurement

- **5.1 Cumulative match.** Run the full candidate against `main`; record the total
  Elo gain. *Gate: AC-6.1 — the cumulative delta is recorded in the PR.*
- **5.2 Docs & board.** Add the new terms to `knowledge/glossary.md` with provenance,
  retire the `Endgame` entry, update the Board entity-model line (`value()`/`is_endgame`
  → `evaluate()`), note the eval in `AGENTS.md`, and move the Epic 4 cards to Done.
  *Gate: `python3 scripts/knowledge.py check` clean; recorded gate PASS.*

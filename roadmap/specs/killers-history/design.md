---
title: Killers and history — design
description: Killer-move and history-heuristic ordering of quiet moves, as one composed function, measured with the harness.
---

> **Status:** Planned (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Killers and history — design

## Decision summary

| Decision | Choice | Why |
|---|---|---|
| Scope | Quiet-move ordering only | Captures, checks, and the TT move already order well. |
| Structure | One composed function | No strategy pattern in the hot path; add terms, not strategies. |
| Killers | 2 per ply | The standard; cheap and effective. |
| History bonus | `depth²` on a quiet cutoff | The conventional weighting; deeper cutoffs count more. |
| Lifetime | Per search, across iterations | Fresh each move; accumulates within iterative deepening. |
| Verification | Tactics + units + harness Elo | Correctness by tests; strength by measurement, not assumption. |

## Killer moves

A table `killers: [[Option<Move>; 2]; MAX_PLY]` on the `Searcher`. At a beta-cutoff
where the cutting move is **quiet** (not a capture or promotion), shift it into the
ply's slots: `killers[ply][1] = killers[ply][0]; killers[ply][0] = mv`, unless it
already equals `killers[ply][0]` (dedupe). In ordering, a ply's killers lead the
quiet group, first slot before second.

## History heuristic

A table `history: [[[i32; 64]; 64]; 2]` indexed by side to move, from square, and
to square. At a quiet-move beta-cutoff, add `depth²` to `history[side][from][to]`.
Scores are clamped to avoid overflow over a long search. The non-killer quiet moves
sort by history score descending, with the piece-square-table change as the
tiebreak (the current quiet order).

## Ordering integration

`move_sorter` stays the composed function. It gains an `OrderingContext` carrying
the ply's killers (`[Option<Move>; 2]`) and a borrow of the history table; the
`Searcher` builds it per node from `killers[ply]` and `&self.history` and passes it
to `prioritize_legal_moves` / `get_moves_to_dequiet`. The quiet group becomes:

```
killers (slot 0, then slot 1) → remaining quiets by history desc → PST-delta tiebreak
```

Checks and captures keep their place; the TT move still leads the whole list
(Epic 1). The updates fire at the existing `alpha >= beta` cutoff in `search_node`,
guarded to quiet moves.

The escape hatch if a second ordering must coexist: a generic
`Searcher<O: MoveOrderer>` (monomorphized, no `dyn`). Not built.

## Lifetime

The tables live on the `Searcher`, which is created fresh per move, so they start
empty each move and accumulate across the iterative-deepening iterations within one
search. No cross-move aging is needed.

## Verification

- **Correctness:** the four tactical tests still pass — ordering changes speed, not
  results. Move generation and perft are untouched.
- **Units:** the killer shift/dedupe keeps two distinct moves and leads the quiet
  group; a history bump reorders two otherwise-equal quiets.
- **Strength:** build the candidate against the pre-epic `main` baseline in a
  worktree and run `selfplay.py`; record the Elo delta in the PR. This is evidence,
  not a blocking gate — small deltas need hundreds of games.

## Naming and provenance

| Term | Definition | Provenance |
|---|---|---|
| Killer move | A quiet move that caused a beta-cutoff at a ply, tried first there next time | CPW "Killer Heuristic" |
| History heuristic | A from-to score table of cutoff frequency that orders quiet moves | CPW "History Heuristic" |

Internal names stay expressive (`killers`, `history`, `OrderingContext`). Both
terms enter `knowledge/glossary.md` in Wave 3.2; they are not in the glossary yet.

## Alternatives considered

- **Strategy pattern for ordering.** Rejected: a virtual call per decision taxes
  the hot path, and the variation is composition, not whole-strategy swap; the
  harness is the A/B mechanism.
- **Captures-first regrouping** (drop the checks-first quirk). Out of scope: a
  separable change, measurable on its own later.
- **History penalties for failed quiets / butterfly boards.** Deferred: start with
  the cutoff bonus and measure before adding complexity.

## Risks

| Risk | Mitigation |
|---|---|
| A killer or history move is illegal in the current position | Promote only moves present in the generated quiet list; a miss is a no-op. |
| History overflow over a long search | Clamp scores to a bound. |
| The change helps tactics but not games | Measure with self-play before claiming a gain; the harness exists for this. |

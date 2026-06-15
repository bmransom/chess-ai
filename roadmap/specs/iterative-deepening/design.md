---
title: Iterative deepening — design
description: Architecture and decisions for iterative deepening, time management, and principal variation, with UCI/CPW-faithful naming.
---

> **Status:** Planned (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Iterative deepening — design

## Decision summary

| Decision | Choice | Why |
|---|---|---|
| Time policy | Clock fraction | Predictable and safe: `remaining/movestogo (or /30) + 0.7·inc`, capped at 40%. |
| Scope | Core + TT fix | Iterative deepening, time-managed `go`, PV, the TT reuse fix, and mate-distance scoring. Killers/history/aspiration deferred. |
| Stop | Deadline + node poll | Check the clock every ~2048 nodes; discard a half-finished iteration. |
| PV | Triangular PV-table | Robust against TT overwrites. |
| Mate scores | Distance to root | A faster mate wins; `info` reports `score mate` correctly. |
| Naming | UCI tokens at the boundary; expressive names inside | The wrapper speaks UCI; the core reads with full names and translates between them. |

## The seam

The core gains one time-aware entry point. `Searcher.search` deepens against a
deadline and returns a result dict with expressive keys. `next_move` stays as-is
for the HTTP decision-tree path.

```python
searcher.search(max_depth=64, move_time_ms=None,
                white_time_ms=None, black_time_ms=None,
                white_increment_ms=0, black_increment_ms=0,
                moves_to_go=None) -> {
    "best_move": "e2e4",
    "score_centipawns": 31,       # side-to-move POV; None when a mate is found
    "mate_in_moves": None,        # signed moves to mate; None when not a mate
    "depth": 9,                   # last completed depth, plies
    "nodes": 240117,
    "elapsed_ms": 842,
    "principal_variation": ["e2e4", "e7e5", "g1f3"] }
```

All times are milliseconds. `SearchLimits` (Rust) holds the inputs under the same
field names. UCI token spellings appear only in the wrapper (see Naming).

## Iterative deepening and stop

`search` loops `depth = 1..=max_depth`, calling the root search each time. After a
*completed* depth it keeps the result. The `Searcher` carries a `nodes` counter
and a `deadline`; every ~2048 nodes it checks `should_stop()` (past the deadline),
which sets `stopped`. A stopped search unwinds and the loop **discards the
half-finished iteration**, returning the deepest completed result. A found forced
mate ends the loop early.

## Time budget

| Input | Budget |
|---|---|
| `movetime M` | `M − overhead` |
| clock (`wtime`/`btime` …) | `remaining/movestogo` (or `remaining/30` in sudden death) `+ 0.7·increment`, capped at `0.4·remaining`, minus overhead |
| `depth D` only | no deadline; deepen to `D` |
| bare `go` | no deadline; default depth (with the endgame boost), keeping the acceptance test fast |

`overhead` is a small constant (~50 ms) so the engine never flags. The side to
move picks its own clock: `wtime`/`winc` for White, `btime`/`binc` for Black.

## Transposition-table fix

Today a probe returns an entry only when its depth equals the requested depth, so
iterative deepening cannot reuse shallower work. Two changes:

1. **Probe on key match.** `get` returns the entry whenever the Zobrist key
   matches. The depth check moves into the search: a stored entry with
   `depth ≥ requested` yields the cutoff (`Exact` → return; `LowerBound`/`UpperBound`
   → tighten alpha/beta).
2. **Hash-move ordering.** The stored best Move is searched **first**, even when the
   entry is too shallow to cut. This is what makes re-searching from depth 1 cheap.

## Mate-distance scoring

Checkmate scores `MATE − ply` (ply = distance from the root) instead of flat
`MATE`, so a mate in one outscores a mate in three. A score is a mate score when
its magnitude exceeds `MATE − MAX_PLY`. The transposition table applies the
standard ±ply adjustment on store and probe so mate scores stay correct across the
table. The result converts plies to moves for `mate` (UCI `score mate` is in
moves, not plies).

## Principal variation

A triangular PV-table collects the line: at a node that raises alpha, the node's PV
becomes its move prepended to the best child's PV. The root's line is the principal
variation; its first move is the returned `move`.

## UCI wrapper

`communication.py` parses `go wtime/btime/winc/binc/movestogo/movetime/depth`,
translates the tokens to the core's parameters (`wtime` → `white_time_ms`, and so
on), and calls `search`. It maps the result back to UCI, printing one
`info depth D score (cp X | mate Y) nodes N time T pv …` line, then
`bestmove <move>`. Bare `go` keeps the old default depth and endgame boost. The
command set is unchanged. The HTTP API is unchanged.

## Naming

UCI tokens are an interface detail. They appear only in the UCI wrapper, which
parses the `go` line and prints `info`. The core and its seam use expressive names
per the repo's clean-code standard; the wrapper translates between the two layers.

| UCI interface (wrapper only) | Core / seam name |
|---|---|
| `go wtime` / `btime` | `white_time_ms` / `black_time_ms` |
| `go winc` / `binc` | `white_increment_ms` / `black_increment_ms` |
| `go movetime` | `move_time_ms` |
| `go movestogo` | `moves_to_go` |
| `go depth` | `max_depth` |
| `info score cp` | `score_centipawns` |
| `info score mate` | `mate_in_moves` (signed moves) |
| `info time` | `elapsed_ms` |
| `info pv` | `principal_variation` |
| `info depth` / `nodes` | `depth` / `nodes` |
| `bestmove` | `best_move` |

The underlying concepts carry their domain provenance, recorded in the glossary in
Wave 7: iterative deepening, triangular PV-table, mate score, and centipawn from the
Chess Programming Wiki; the UCI time controls from the UCI protocol. `SearchLimits`
follows Stockfish's `LimitsType`. The existing **Principal variation** glossary
entry loses "(planned)"; its id becomes `principal_variation` (UCI wire token `pv`),
and `pline` moves to the debt column.

## Naming cleanups in `search.rs`

Apply these when the search functions are rewritten (Waves 1, 3, 4); the existing
cargo gate covers them.

| Now | New | Why |
|---|---|---|
| `checked` | `in_check` | boolean reads as a question; matches the `in_check()` helper |
| `alpha_orig` | `original_alpha` | no abbreviation |
| `max_val` | `best_score` | what it is, not how it's computed |
| `child` | `child_score` | it is a score; aligns with `capture_tree`'s `child_value` |
| `move_eval` | `move_score` | consistent with `best_score` / `child_score` |
| `key` | `zobrist_key` | `key` alone is generic at the call sites |
| `sign` | `perspective` | the side-to-move multiplier |

`stand_pat` stays (the Chess Programming Wiki term for the quiescence static eval)
with a one-line doc. `negamax` gains a named result type once it carries the
principal variation and score (Wave 4). `NULL_MOVE` (`"0000"`) stays in the core,
consistent with the UCI move strings it already returns.

## Alternatives considered

- **TT-based PV** (follow stored best moves). Rejected: a collision or overwrite
  truncates the line; the triangular table is robust.
- **UCI tokens as the seam names** (`wtime`, `pv`, `cp`). Rejected: the protocol's
  terse tokens are an interface detail; the core reads more clearly with expressive
  names, and the wrapper is the right place to translate.
- **Adaptive timing** (spend more when the best move is unstable). Deferred: more
  tuning; the clock fraction is the safe first version.
- **Per-iteration `info` streaming.** Deferred: needs a PyO3 callback; one final
  `info` line satisfies lichess-bot.

## Risks

| Risk | Mitigation |
|---|---|
| Time check too coarse and the engine flags | Poll every ~2048 nodes; keep a 50 ms overhead; cap at 40%. |
| Mate-score TT adjustment is a classic bug source | A unit test asserts a faster mate outscores a slower one and survives a TT round-trip. |
| Tactical moves shift under new ordering/scoring | Re-run the four tactical tests; a faster mate is an allowed improvement, recorded if a move changes. |
| Partial-iteration result leaks into the move | The loop only adopts a result from a depth that completed before `stopped`. |

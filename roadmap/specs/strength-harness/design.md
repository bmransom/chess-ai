---
title: Strength harness — design
description: Architecture for the EPD tactical suite and self-play match harness, with python-chess as the independent oracle.
---

> **Status:** Done (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Strength harness — design

## Decision summary

| Decision | Choice | Why |
|---|---|---|
| Metrics | EPD solve-rate + self-play Elo | Fast tactical regression and a real strength number. |
| A/B method | Two UCI engine commands | General and decoupled from build management; mirrors cutechess. |
| Oracle | `python-chess` | The suite's moves and the game arbiter share no code with the engine. |
| Dependencies | None new | `python-chess` (a test dep) supplies EPD parsing, SAN↔UCI, and the UCI driver. |
| Gate | On-demand; tiny self-test | Full runs are slow; a fast self-test guards the tools. |

## Components

Two scripts in `scripts/`, on-demand like `bench_perft.py`.

### `epd_suite.py` — tactical solve-rate

Loads an EPD file, searches each position at a fixed `movetime` or `depth`, and
reports the solve-rate. Runs `brandobot_core` in-process for speed.
`python-chess` parses the EPD and converts each position's `bm` (SAN) to UCI for
comparison.

```
python scripts/epd_suite.py --movetime 100 bench/wac.epd
→ 247/300 solved (82.3%); 53 failed (listed)
```

### `selfplay.py` — match and Elo

Takes two UCI player commands, plays `N` games, and reports the result and an Elo
estimate. `python-chess`'s `chess.engine.SimpleEngine` runs each engine as a UCI
subprocess; `python-chess` is the **arbiter** (legality, draws, adjudication).

```
# build the baseline in a worktree, then:
python scripts/selfplay.py --games 200 --movetime 100 \
  --engine1 "python src/main.py" --engine2 "python ../base/src/main.py"
→ engine1 vs engine2: +58 -41 =101, 54.2%, Elo +29 ± 24
```

Each opening is played twice, colors swapped, for fairness. `--depth` gives
deterministic games; `--movetime` gives timed play. A seed fixes opening order.

## Elo estimate

`score = (wins + 0.5·draws) / games`; `elo = -400 · log10(1/score − 1)` (clamped
away from 0 and 1). The error margin is the standard ±1.96·σ from the score
variance. It is the conventional fixed-rating-difference estimate, not SPRT (a
possible later addition).

## Data

| File | Contents |
|---|---|
| `bench/wac.epd` | A sample of the Win At Chess tactical suite (Fred Reinfeld), a standard public test set; the runner accepts any EPD file for fuller suites |
| `bench/openings.epd` | Balanced opening positions for self-play variety |

## Independent verification

The engine is the system under test; the referee is not. EPD best moves are
external ground truth, and `python-chess` adjudicates games. Neither shares code
with `brandobot_core`, satisfying the repo's independent-verification rule.

## Gate

The full suite and matches are manual. A fast pytest self-test runs `epd_suite`
on a two-position mini-EPD and `selfplay` on a single shallow game, asserting each
reports its summary — guarding the tools without slowing the gate.

## Naming and provenance

New domain terms, recorded in the glossary:

| Term | Definition | Provenance |
|---|---|---|
| EPD | Extended Position Description — a FEN with operations such as `bm` (best move) | the EPD standard / CPW |
| Elo | A rating-difference estimate from a match's score rate | Arpad Elo / CPW "Match Statistics" |
| Solve-rate | The fraction of EPD positions whose searched move matches a `bm` move | this repo |
| Self-play | Two engine builds playing a match to compare strength | CPW "Engine Testing" |

CLI flags reuse the established names (`--movetime`, `--depth`, `--games`); the
engine commands are opaque strings, so no UCI tokens leak into the harness.

## Alternatives considered

- **External arbiter (fastchess / cutechess-cli) with SPRT.** More rigorous, but
  adds a binary dependency; deferred. The in-repo harness can grow SPRT later.
- **Feature-flag A/B in one build.** Rejected: every change would need a flag and
  the engine would gain option plumbing; two commands stay general.
- **EPD only.** Rejected: it measures tactics, not overall strength, and gives no
  Elo.

## Risks

| Risk | Mitigation |
|---|---|
| Timed games are nondeterministic | `--depth` mode is deterministic; document it for reproducible A/B. |
| Self-play subprocess startup is slow | Self-test uses one shallow game; full matches are manual and use short time controls. |
| Suite licensing | Bundle a small attributed WAC sample; accept any external EPD path for fuller suites. |
| Elo from few games is noisy | Report the error margin; document that hundreds of games are needed for small deltas. |

---
title: Strength harness — requirements
description: User stories and EARS acceptance criteria for an EPD tactical suite and a self-play match harness that measure engine strength.
---

> **Status:** Planned (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Strength harness — requirements

Two on-demand tools that turn engine changes into a measured strength delta: an
EPD tactical suite that reports a solve-rate, and a self-play match that reports
an Elo estimate. Both use `python-chess` as the independent oracle — the suite's
known best moves and the game arbiter share no code with the engine.

## Story 1 — EPD tactical suite

As the maintainer, I want a solve-rate on a tactical suite, so any change shows a
tactical-strength delta.

- AC-1.1 WHEN `epd_suite.py` runs on an EPD file at a fixed `movetime` or `depth`, THE SYSTEM SHALL report the number solved, the total, and the solve-rate.
- AC-1.2 WHEN a position's searched best move is among that position's EPD `bm` moves, THE SYSTEM SHALL count it solved.
- AC-1.3 WHEN a position is not solved, THE SYSTEM SHALL list it with its FEN, the expected moves, and the move played.
- AC-1.4 WHEN given a path to any EPD file, THE SYSTEM SHALL run that file, so a fuller suite can be supplied.

## Story 2 — Self-play match

As the maintainer, I want two engine commands to play a match with an Elo
estimate, so I can measure whether a change is stronger.

- AC-2.1 WHEN `selfplay.py` runs with two UCI engine commands for `N` games, THE SYSTEM SHALL play `N` games, alternating colors, and report wins, losses, and draws from the first engine's view.
- AC-2.2 WHEN the match completes, THE SYSTEM SHALL report the score rate and an Elo estimate with an error margin.
- AC-2.3 WHEN `--depth` is given, THE SYSTEM SHALL play every game at that fixed depth.
- AC-2.4 WHEN `--movetime` is given, THE SYSTEM SHALL play at that time per move.
- AC-2.5 WHEN the match starts, THE SYSTEM SHALL draw openings from a fixed opening list so games vary.

## Story 3 — Independent oracle

As the maintainer, I want the verdicts to come from outside the engine, so the
measurement is trustworthy.

- AC-3.1 WHEN the harness judges a solved position or a game result, THE SYSTEM SHALL use `python-chess`, not `brandobot_core`.

## Story 4 — On-demand, guarded by a self-test

As the maintainer, I want the slow runs kept out of the fast gate but the tools
guarded, so the gate stays fast and the harness stays working.

- AC-4.1 WHEN `scripts/check-fast.sh` runs, THE SYSTEM SHALL NOT run the full EPD suite or a self-play match.
- AC-4.2 WHEN the gate runs, THE SYSTEM SHALL run a fast self-test that exercises both runners on a tiny input.

---
title: Strength harness — tasks
description: Waved plan for the EPD suite and self-play harness; each task names its gate.
---

> **Status:** Done (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Strength harness — tasks

Tasks within a wave are independent; each wave builds on the last. Every task
names its gate. The two runners (Waves 1 and 2) are independent and could land in
either order.

## Wave 1 — EPD tactical suite

- **1.1 EPD runner.** `scripts/epd_suite.py`: parse an EPD file with `python-chess`,
  search each position via `brandobot_core` at a `movetime` or `depth`, compare the
  move to the `bm` set, and report the solve-rate and the failures. *Gate: AC-1.1–1.4
  — a self-test runs a two-position mini-EPD and asserts the reported solve-rate.*
- **1.2 WAC sample.** Add `bench/wac.epd` (an attributed Win At Chess sample) and a
  header noting provenance. *Gate: the runner solves the sample at a sane depth.*

## Wave 2 — Self-play match

- **2.1 Self-play runner.** `scripts/selfplay.py`: play two UCI engine commands for
  `N` games via `python-chess`'s engine driver and arbiter, alternating colors from
  a fixed opening list, and report wins/losses/draws, the score rate, and an Elo
  estimate with an error margin. *Gate: AC-2.1–2.5 — a self-test plays one shallow
  game and asserts the reported summary.*
- **2.2 Openings + Elo.** Add `bench/openings.epd` and the Elo/error-margin
  computation. *Gate: AC-2.2 — a unit test on the Elo formula for known score rates.*

## Wave 3 — Gate & docs

- **3.1 Gate self-test.** Wire the fast harness self-test into the suite; keep full
  runs out of `scripts/check-fast.sh`. *Gate: AC-4.1–4.2 — the gate runs the
  self-test and not the full suite.*
- **3.2 Docs & board.** Update `knowledge/glossary.md` (EPD, Elo, solve-rate,
  self-play with provenance), document the tools in `AGENTS.md` Commands, and move
  the Epic 2 cards to Done. *Gate: `python3 scripts/knowledge.py check` clean;
  recorded gate PASS.*

---
title: Validation
description: Every verification gate — command, what it catches, when it fires.
type: reference
---

<!-- foundry-seed: validation v1 -->

# Validation

A **gate** is a verification command whose recorded PASS is the evaluator for
done-ness — the gate decides, never the author's assertion.

Every gate fires from two triggers: `.githooks/pre-push` (fast feedback; bypass
once with `git push --no-verify`) and CI (the non-bypassable backstop) — the same
script both times.

## Gates

Add a row for every gate.

- Heavy gates (long benchmarks, full suites) stay manual; add a row with trigger "manual".

| Gate | Command | Catches | Trigger |
|---|---|---|---|
| Quick gate | `scripts/check-fast.sh` | lint, unit tests, doc frontmatter | pre-push + CI |
| EPD tactical suite | `scripts/epd_suite.py <suite>` | tactical-strength regressions (solve-rate) | manual |
| Self-play Elo | `scripts/selfplay.py` | a fixed-N Elo strength delta vs a baseline | manual |
| Fair-match SPRT | `scripts/sprt.py` | a bounded-error keep/drop verdict on an eval term | manual |

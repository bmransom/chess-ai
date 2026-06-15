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

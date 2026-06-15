---
title: COE template
description: Correction of Error — the fill-in record for a real failure the setup permitted.
type: decision
---

<!-- foundry-seed: coe-template v1 -->

# Correction of Error — `<one-line title>`

**Date:** `<YYYY-MM-DD>` ·
**Severity:** `<low | medium | high>` ·
**Status:** `<open | root-caused | closed>`

*Copy this template to `knowledge/<slug>-coe.md`; keep the headings.*

## What happened

*State the observable failure — what broke, when, who or what caught it.*

## Root cause

*The mechanism that allowed the failure — not the proximate mistake. Keep asking
why until the answer is machinery, not a person.*

## Blast radius

*What the failure touched or could have touched: artifacts, decisions, consumers.*

## The mechanical fix

*The gate, lint, rule, or eval that now catches this class of failure. A COE
closed by prose alone is not closed.*

## Eval case spawned

*The fixture or seeded defect added so the fix is graded by discrimination — the
defect must fail the gate.*

## Promotion

*If the root cause is shared machinery, promote this COE upstream and add the
eval case there.*

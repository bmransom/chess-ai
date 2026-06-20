---
title: Fair-match harness — requirements
description: A reproducible fixed-node self-play harness with a pentanomial SPRT acceptance rule that decides term retention with bounded error.
---

> **Status:** Ready — tracked on the [board](../../ROADMAP.md). Derived from the
> two-harness deliberation session `fair-match-harness` (Codex + Claude Code).

# Fair-match harness — requirements

Epic 4 term-retention decisions were made on an under-powered method: every
recorded measurement used `--games 16 --depth 4`, where the Elo error margin
(±60–84) dwarfed every signal, and king safety (`+22 ± 73`) and mobility
(`−0 ± 60`) were statistically identical yet decided oppositely. At fixed depth
both engines are deterministic, so 16 games from 8 openings is a 16-position
census, not an i.i.d. sample, so the Elo error formula's assumption fails and
more games add no information. This card replaces the decision *method*: a
reproducible fixed-node match feeding a pentanomial SPRT with bounded error. The
Epic 4 term cards consume it; this card does not re-decide terms.

## Story 1 — Reproducible, fair match

As the maintainer, I want matches that are equal-effort and bit-reproducible, so a
measured delta reflects the eval change and nothing else.

- AC-1.1 WHEN given `go nodes N`, THE SYSTEM SHALL search a fixed node budget with no wall-clock dependence.
- AC-1.2 WHEN a node budget aborts a search mid-iteration, THE SYSTEM SHALL return the best move of the last completed depth.
- AC-1.3 WHEN the same position is searched twice at the same node budget, THE SYSTEM SHALL return an identical best move and an identical node count.
- AC-1.4 WHEN a game begins, THE SYSTEM SHALL send `ucinewgame` first, so no transposition-table state carries across games.
- AC-1.5 WHEN adjudicating a result, THE SYSTEM SHALL use evaluation thresholds (a win when `|eval|` holds above a resign margin for a sustained span; a draw when `|eval|` holds near zero for a sustained span), not a fixed move cap.
- AC-1.6 WHEN selecting openings, THE SYSTEM SHALL draw color-swapped pairs from a large unbalanced (UHO) book, capped at a configured number of unique pairs.

## Story 2 — SPRT acceptance rule

As the maintainer, I want a sequential test with bounded error, so each keep/drop
verdict is trustworthy rather than a coin flip.

- AC-2.1 WHEN a match runs, THE SYSTEM SHALL tally each color-swapped pair into one of five pentanomial categories and report a running log-likelihood ratio (LLR).
- AC-2.2 THE SYSTEM SHALL test H0 Elo ≤ 0 against H1 Elo ≥ 5 at α = β = 0.05, accepting H1 when LLR ≥ log((1−β)/α) and H0 when LLR ≤ log(β/(1−α)).
- AC-2.3 THE SYSTEM SHALL compute the LLR by the pentanomial GSPRT (constrained multinomial MLE), not by a trinomial game count.
- AC-2.4 WHEN it reports a verdict, THE SYSTEM SHALL report one of `accept-H1`, `accept-H0`, or `inconclusive`.

## Story 3 — Honest exhaustion and status

As the maintainer, I want a definite, non-fabricated answer when the evidence runs
out, so a flat run is never over-interpreted.

- AC-3.1 WHEN the unique-pair supply is exhausted before a bound is crossed, THE SYSTEM SHALL report `inconclusive` with the pentanomial census point estimate and a finite-population confidence interval, and SHALL NOT replay openings to accumulate further likelihood.
- AC-3.2 WHEN a term's verdict is `inconclusive`, THE SYSTEM SHALL leave the term `In progress`; no verdict marks a term `Done` without a recorded gate PASS.
- AC-3.3 WHEN either game of a pair truncates (crash or timeout), THE SYSTEM SHALL drop the whole pair and SHALL NOT fabricate the missing half.

## Story 4 — Cost-aware keep/drop

As the maintainer, I want the keep rule to see a term's cost, so a slow term that
wins on equal nodes but loses on the clock is not shipped.

- AC-4.1 WHEN deciding to keep a term, THE SYSTEM SHALL require both an `accept-H1` SPRT verdict and a passing node-rate / short-time-control cost check.
- AC-4.2 WHEN a match completes, THE SYSTEM SHALL report node-rate (and elapsed time) as a secondary metric that never alters the SPRT verdict.

## Story 5 — Independent verification, guarded by a self-test

As the maintainer, I want the SPRT math checked against an outside oracle and the
tools guarded without slowing the gate.

- AC-5.1 THE SYSTEM SHALL verify the LLR against an oracle that shares no code with the harness: the degenerate binomial case (only `LL`/`WW`), where GSPRT reduces to the closed-form Wald LLR, plus a brute-force numerical maximizer for a worked five-category vector.
- AC-5.2 WHEN `scripts/check-fast.sh` runs, THE SYSTEM SHALL run a fast self-test (a synthetic SPRT stream plus a two-pair node-limited mini-match) and SHALL NOT run a full SPRT match.

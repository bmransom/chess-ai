---
title: Fair-match harness — design
description: Fixed-node reproducible self-play feeding a pentanomial GSPRT acceptance rule, with an independent oracle and a cost gate.
---

> **Status:** Ready — tracked on the [board](../../ROADMAP.md). Derived from the
> two-harness deliberation session `fair-match-harness` (Codex + Claude Code);
> the recorded decisions live in `.foundry/tmp/harness-deliberation/`.

# Fair-match harness — design

## Decision summary

| Decision | Choice | Why |
|---|---|---|
| Acceptance rule | Pentanomial SPRT (GSPRT) | Sequential, bounded-error keep/drop; the Fishtest/OpenBench standard. |
| Model | Pentanomial, **mandatory** | Trinomial assumes a pair's two games are independent — the exact i.i.d. error that gave Epic 4's ±60–84 margins. |
| Bounds | H0 ≤ 0, H1 ≥ 5; α = β = 0.05 | The Fishtest "add a feature" gate; logistic Elo, nominal Wald bounds. |
| Play mode | Fixed nodes | Equal effort, deterministic, bit-reproducible. |
| Variety | Large UHO book + color-swapped pairs | Power comes from the book + pentanomial, not from fixed nodes. |
| Exhaustion | inconclusive + census CI | Deterministic play caps independent pairs at book size; never replay. |
| Cost | Node-rate / short-TC gate | Fixed-node SPRT is blind to a term's CPU cost. |
| Verification | Binomial-degenerate Wald oracle | The exact MLE LLR is not hand-computable; verify where GSPRT collapses to closed form. |

## Why this is fair *and* powered

Two independent problems, two independent fixes — the spec must not conflate them:

- **Fairness (equal effort)** comes from **fixed nodes**: both engines get the same
  node budget per move, so a delta reflects eval quality, not speed. Fixed nodes is
  deterministic, which also makes a match bit-reproducible.
- **Power** comes from the **large UHO book + pentanomial + SPRT**. Determinism does
  *not* solve the census problem — it keeps it: a deterministic match draws without
  replacement, so independent pairs are capped at the book size. Only book size and
  the game-pair model buy statistical power. Fixed nodes earns no credit here.

## Components

Three scripts in `scripts/`, sharing one core; the SPRT math is engine-free.

- **`match_core.py`** — UCI driving, book loading, color-swapped pair play,
  `ucinewgame` per game, eval-based adjudication, and pentanomial tallying.
  Extracted from today's `selfplay.py` with no behavior change to the reporter.
- **`selfplay.py`** — stays the fixed-N Elo reporter, now importing `match_core`.
- **`sprt.py`** — the SPRT front-end: pull pairs, update the LLR, stop at a verdict.
- **`sprt` math** — a pure function taking a five-count vector → `(LLR, verdict)`,
  with no engine and no game model, so it is unit-tested on synthetic vectors.

## Pentanomial GSPRT

Each color-swapped pair scores one of five categories with normalized pair scores:

```
categories = [LL, LD+DL, LW+DD+WL, DW+WD, WW]
x          = [0,  0.25,  0.5,      0.75,  1]
```

Endpoints from **logistic** Elo `s(e) = 1 / (1 + 10^(−e/400))`: `s0 = s(0) = 0.5`,
`s1 = s(5) = 0.507196`. The LLR is the constrained multinomial MLE (Fishtest
`LLRcalc`), not a trinomial count. With counts `n_i`, `N = Σ n_i`, empirical
`p̂_i = n_i / N`, for each endpoint mean `s ∈ {s0, s1}` solve the scalar `λ` in

```
Σ_i  p̂_i (x_i − s) / (1 + λ (x_i − s)) = 0
```

then `q_i^(s) = p̂_i / (1 + λ (x_i − s))` and

```
LLR = Σ_i  n_i · log( q_i^(s1) / q_i^(s0) )
```

Variance never enters the LLR (it is only for expected-sample-size estimates).
Accept H1 at `LLR ≥ log((1−β)/α) = log(19) ≈ 2.944`; accept H0 at
`LLR ≤ log(β/(1−α)) = −log(19)`. Bounds are **nominal Wald** (overshoot
unadjusted) — adequate for a keep/drop call, not a published rating.

A genuine +1…+4 Elo term sits inside the indifference region `[0, 5]`, where SPRT
offers no error guarantee; it resolves as `inconclusive`, not a false drop. That is
the intended, honest behavior of a strict gate, not a defect.

## Fixed-node search

Add `node_limit: Option<u64>` to `SearchLimits` (`core/src/search.rs:39`) and stop
in the existing `should_stop` (`core/src/search.rs:181`). Thread it through the
PyO3 `search` arg (`core/src/lib.rs:164`) and `GO_PARAMETERS["nodes"] =
"node_limit"` (`src/communication.py:7`); drive via `chess.engine.Limit(nodes=N)`.

**Determinism** rests on three verified facts and two new requirements:

- Zobrist keys seed from a fixed constant (`core/src/zobrist.rs:29`) — no
  per-process randomness, so even TT collision behavior is identical run to run.
- Partial iterations are already discarded (`core/src/search.rs:121`), so a
  mid-iteration node abort returns the last completed depth's move.
- In node mode, set `deadline = None` so `Instant::now()` is never called (zero
  wall-clock dependence) and `max_depth` high (e.g. 64) so `node_limit` binds.
- Check `node_limit` **exactly**, not only at the 64-node poll, so small budgets
  are honored; keep batched wall-clock polling for the time path.

## Transposition-table hygiene

`selfplay.py` (`105–154`) opens each engine once and never sends `ucinewgame`;
`core/src/lib.rs:78` clears the TT only on `new_game()`. The replace policy ages by
halfmove clock (`core/src/tt.rs:50`), which is **non-monotonic within a game**, so
game-1 entries with a high halfmove clock squat slots and block game-2 stores at the
same index — changing node counts, shifting where the node budget aborts, and so
changing the move. `probe` still returns only exact-key matches (no wrong-position
reads), but the node-count drift breaks reproducibility. `match_core.py` sends
`ucinewgame` before **every** game to reset the TT to a known state.

## Opening book

A large unbalanced (UHO) book from
[`official-stockfish/books`](https://github.com/official-stockfish/books) (e.g.
`UHO_4060_v4.epd`). The implementer **verifies the exact position count and the
`LICENSE` at the source** and records both in the glossary — no remembered figure is
laundered into the record. Sizing: expected pairs to accept at true +5 ≈
`log(19) · 2σ² / (s1 − s0)² ≈ 113,700 · σ²`, i.e. ~5,700–11,400 pairs at pentanomial
`σ² ≈ 0.05–0.10`. A 2,000-position book cannot cross `[0, 5]`; use ~200k positions
with a 20k–50k unique-pair cap so deterministic exhaustion is not the usual outcome.

## Exhaustion and cost

- **Exhaustion.** A deterministic match is a sample without replacement, so on
  reaching the pair cap it holds a *complete* census. Report `inconclusive` with the
  pentanomial point estimate and a finite-population confidence interval — more
  informative than a bare verdict, while never replaying to fabricate likelihood.
- **Cost.** Fixed nodes factor a term's per-node cost out, so `accept-H1` is
  necessary but not sufficient: a +4-Elo term that costs 20% node-rate is
  net-negative at real time controls. The keep/drop rule is `accept-H1` **and** a
  passing node-rate / short-TC check. Report node-rate as a secondary metric; it never
  alters the SPRT verdict.

## Independent verification

The exact MLE LLR needs a polynomial root-solve, so it is not hand-computable, and a
"hand-computed exact LLR" test would be circular. Verify instead in the degenerate
**binomial** case (only `LL`/`WW`), where the constraint is exact, `λ` vanishes, and
GSPRT collapses to the closed-form Wald LLR
`n_WW · log(s1/s0) + n_LL · log((1−s1)/(1−s0))` — hand-computable and sharing no code
with `sprt.py`. Pair it with a separate brute-force numerical multinomial maximizer
for a worked five-category vector. This satisfies the repo's independent-verification
rule (the oracle shares no code with the system under test).

## Gate

Full SPRT runs are manual. A fast pytest self-test runs the SPRT math on a synthetic
stream (H1-biased → `accept-H1`, H0-biased → `accept-H0`, short-ambiguous →
`inconclusive`) and a two-pair node-limited mini-match, asserting each reports its
verdict — guarding the tools without slowing `check-fast.sh`.

## Naming and provenance

New domain terms, to record in `knowledge/glossary.md`:

| Term | Definition | Provenance |
|---|---|---|
| SPRT | Sequential test that accepts H0 or H1 once the LLR crosses a bound | Wald 1945; Fishtest "Sequential Probability Ratio Test" |
| Pentanomial GSPRT | A generalized SPRT over the five outcomes of a color-swapped game pair | Michel Van den Bergh; Fishtest `LLRcalc` |
| Node limit | A fixed node budget per search (`go nodes`) | UCI `go nodes`; Stockfish `LimitsType` |
| UHO opening book | An unbalanced-human-openings book that raises the decisive rate | `official-stockfish/books` |

Elo stays **logistic** (matching `selfplay.py:32` and the glossary `Elo` entry);
normalized Elo would be a new glossary term and is not mixed in.

## Alternatives considered

- **Trinomial SPRT.** Rejected: treating a pair's two games as independent re-commits
  the false-independence error this card exists to fix.
- **Time-control play.** Rejected for term decisions: nondeterministic and
  hardware-dependent; fixed nodes gives equal effort and reproducibility. (A short-TC
  check survives only as the secondary cost gate.)
- **Fixed depth, deeper.** Rejected: unequal effort (a different eval explores a
  different node count at the same depth) and no fairer than today's method.
- **Fixed-N confidence interval.** Rejected: must guess N up front; SPRT stops early
  on clear results and runs longer on close ones.

## Risks

| Risk | Mitigation |
|---|---|
| TT carryover fabricates pair dependence and breaks reproducibility | `ucinewgame` before every game (AC-1.4); determinism guard test (AC-1.3). |
| A 2k-position book ends inconclusive on small-but-real terms | ~200k UHO book; 20k–50k pair cap; sizing recorded above. |
| `node_limit < 64` missed by 64-node polling | Check `node_limit` exactly; keep batched time polling. |
| The 80-move draw cap deflates the decisive rate | Eval-based adjudication (AC-1.5). |
| Fixed-node SPRT is blind to term cost | Keep rule adds a node-rate / short-TC gate (AC-4.1). |
| Exact MLE LLR not hand-verifiable → circular test | Binomial-degenerate Wald oracle + brute-force maximizer (AC-5.1). |

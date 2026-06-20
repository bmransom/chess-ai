---
title: Fair-match harness — tasks
description: Waved plan for fixed-node search, the match core, the pentanomial SPRT, the UHO book, and the gate; each task names its gate.
---

> **Status:** Ready — tracked on the [board](../../ROADMAP.md). Derived from the
> two-harness deliberation session `fair-match-harness`.

# Fair-match harness — tasks

Tasks within a wave are independent; each wave builds on the last. Every task names
its gate. Waves 1–3 are the load-bearing path; the SPRT math (Wave 3) needs no
engine and can land in parallel with the core work.

## Wave 1 — Fixed-node search

- **1.1 Node-limited search.** Add `node_limit: Option<u64>` to `SearchLimits`; stop
  exactly in `should_stop`; in node mode set `deadline = None` and `max_depth` high so
  the budget binds. *Gate: AC-1.1–1.2 — a fixed-node search is clock-free and returns
  the last completed depth's move.*
- **1.2 `go nodes` seam.** Thread `node_limit` through the PyO3 `search` arg and
  `GO_PARAMETERS["nodes"]`; drive via `chess.engine.Limit(nodes=N)`. *Gate: a unit
  test on `go nodes` parsing, plus repeated fixed-node best-move and node-count
  stability (AC-1.3).*

## Wave 2 — Match core

- **2.1 Extract `match_core.py`.** Move engine driving, book loading, and color-swapped
  pair play out of `selfplay.py`; `selfplay.py` stays the fixed-N reporter importing it.
  *Gate: the existing `selfplay` self-test still passes unchanged.*
- **2.2 Reproducibility + adjudication.** Send `ucinewgame` before every game; replace
  the fixed move cap with eval-based win/draw adjudication. *Gate: AC-1.4–1.5 — a
  determinism guard replays one opening as a later pair and asserts identical
  best moves and node counts.*

## Wave 3 — Pentanomial SPRT

- **3.1 SPRT math.** A pure `sprt` function: five-count vector → `(LLR, verdict)` via
  the constrained multinomial MLE, with H0/H1 bounds. Engine-free. *Gate: AC-2.1–2.4.*
- **3.2 Independent verification.** Test against the binomial-degenerate closed-form
  Wald oracle (hand-computed) and a brute-force numerical maximizer for a five-category
  vector; synthetic-stream verdicts (H1-biased → `accept-H1`, H0-biased → `accept-H0`,
  short-ambiguous → `inconclusive`). *Gate: AC-5.1.*
- **3.3 `sprt.py` front-end.** Pull pairs from `match_core`, update the LLR, stop at a
  verdict; on pair-cap exhaustion report `inconclusive` with the census estimate and a
  finite-population CI; drop a pair if either game truncates. *Gate: AC-3.1, AC-3.3.*

## Wave 4 — Opening book & cost gate

- **4.1 UHO book.** Add a UHO book under `bench/` with a provenance header; verify the
  exact position count and license at `official-stockfish/books` and record both.
  *Gate: AC-1.6 — the harness draws color-swapped pairs from the book.*
- **4.2 Cost gate.** Report node-rate (and elapsed time) as a secondary metric; the
  keep/drop rule is `accept-H1` **and** a passing node-rate / short-TC check. *Gate:
  AC-4.1–4.2.*

## Wave 5 — Gate, docs & governance

- **5.1 Gate self-test.** Wire a fast self-test (synthetic SPRT stream + two-pair
  node-limited mini-match) into the suite; keep full SPRT out of `check-fast.sh`.
  *Gate: AC-5.2.*
- **5.2 Docs & glossary.** Add `SPRT`, `pentanomial GSPRT`, `node limit`, and
  `UHO opening book` to `knowledge/glossary.md` with provenance; document the tools in
  `AGENTS.md` Commands. *Gate: `python3 scripts/knowledge.py check` clean.*
- **5.3 Board governance.** On a green gate, move this card to Done. Recommend
  reopening **King safety** to `In progress` so all three Epic 4 term decisions are
  provisional pending this harness — its `+22 ± 73` retention rests on the same broken
  16-game method. *Gate: maintainer sign-off on the board change; AC-3.2.*

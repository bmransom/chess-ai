---
title: Iterative deepening — requirements
description: User stories and EARS acceptance criteria for iterative deepening, time management, and principal variation on the Rust Searcher.
---

> **Status:** Done (2026-06-15) — tracked on the [board](../../ROADMAP.md).

# Iterative deepening — requirements

Replace fixed-depth search with iterative deepening on the Rust `Searcher`:
deepen one ply at a time within a time budget derived from the clock, report the
principal variation, and stop on the budget. Two enabling fixes ride along: the
transposition table must reuse work across depths, and mate scores must carry
their distance to the root. Vocabulary follows the UCI protocol and the Chess
Programming Wiki (see `design.md`).

## Story 1 — Time-managed iterative deepening

As the bot on lichess, I want to search within a budget derived from the clock,
so I use my time well and never flag.

- AC-1.1 WHEN `search` runs with a `movetime` budget, THE SYSTEM SHALL stop within `movetime` plus a fixed overhead and return a legal Move.
- AC-1.2 WHEN a clock budget is computed, THE SYSTEM SHALL allocate `remaining/movestogo` (or `remaining/30` in sudden death) plus `0.7 × increment`, never exceeding 40% of the side-to-move's remaining time.
- AC-1.3 WHEN the budget expires during an iteration, THE SYSTEM SHALL discard that iteration and return the deepest fully completed result.
- AC-1.4 WHEN `search` is given a `max_depth` and no clock or `movetime`, THE SYSTEM SHALL deepen iteratively to `max_depth` and stop.
- AC-1.5 WHEN the same position is searched with more time, THE SYSTEM SHALL reach a depth at least as great as a shorter search.
- AC-1.6 WHEN `search` returns, THE SYSTEM SHALL report `best_move`, `score_centipawns` or `mate_in_moves`, `depth`, `nodes`, `elapsed_ms`, and `principal_variation`.

## Story 2 — Transposition-table reuse across depths

As the engine, I want the table to serve any entry searched at least as deep and
to seed move ordering, so each iteration reuses the last one's work.

- AC-2.1 WHEN a position is probed and a stored entry's depth is at least the requested depth, THE SYSTEM SHALL use it for an exact cutoff or to tighten alpha/beta.
- AC-2.2 WHEN a stored entry exists for the position, THE SYSTEM SHALL search its stored best Move first, even when the entry is too shallow to cut.
- AC-2.3 WHEN a depth-`D` search runs with the table populated by the depth-`D-1` iteration, THE SYSTEM SHALL visit fewer nodes than the same search with an empty table.

## Story 3 — Mate-distance scoring

As an analyst, I want forced mates scored by distance, so the engine prefers the
fastest mate and reports it correctly.

- AC-3.1 WHEN two moves both force mate, THE SYSTEM SHALL prefer the one mating in fewer moves.
- AC-3.2 WHEN the engine reports a forced mate, THE SYSTEM SHALL report `mate_in_moves` as the number of moves to mate (positive when the side to move gives mate, negative when it is mated); the UCI wrapper prints this as `score mate`.
- AC-3.3 WHEN a mate score is stored to or read from the transposition table, THE SYSTEM SHALL adjust it by the distance from the root so it stays correct.

## Story 4 — Principal variation

As an analyst, I want the engine to report the line it expects, so I can see its
plan.

- AC-4.1 WHEN `search` completes a depth, THE SYSTEM SHALL produce a principal variation whose first Move equals the returned Move.
- AC-4.2 WHEN `search` reports a principal variation, THE SYSTEM SHALL produce a legal sequence of Moves from the searched position.

## Story 5 — UCI time controls

As lichess-bot, I want `go` with a clock or `movetime` to drive the search, so the
engine plays timed games.

- AC-5.1 WHEN the engine receives `go wtime W btime B` with optional `winc`, `binc`, and `movestogo`, THE SYSTEM SHALL search within the computed budget and reply `bestmove`.
- AC-5.2 WHEN the engine receives `go movetime M`, THE SYSTEM SHALL search about `M` ms and reply `bestmove`.
- AC-5.3 WHEN the engine receives `go depth D`, THE SYSTEM SHALL deepen to `D` and reply `bestmove`.
- AC-5.4 WHEN the engine receives bare `go`, THE SYSTEM SHALL search to a default depth and reply `bestmove`.
- AC-5.5 WHEN a search completes, THE SYSTEM SHALL print one `info depth D score (cp X | mate Y) nodes N time T pv ...` line before `bestmove`.

## Story 6 — Behavior preserved

As the maintainer, I want the tactics and contracts intact, so the upgrade adds
strength without regressing.

- AC-6.1 WHEN searched to depth 3, THE SYSTEM SHALL still return `f8f7`, `h7h8`, `f6a6`, and not `e1e8` for the four tactical positions.
- AC-6.2 WHEN the engine accepts UCI commands, THE SYSTEM SHALL recognize exactly `uci`, `isready`, `ucinewgame`, `position`, `go`, `quit`.
- AC-6.3 WHEN a move is requested over either entrypoint, THE SYSTEM SHALL return a legal Move.

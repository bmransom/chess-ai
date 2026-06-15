---
title: Glossary — the ubiquitous language
description: The vocabulary contract for specs, code, APIs, and concepts.
type: reference
---

<!-- foundry-seed: glossary v1 -->

# Glossary — the ubiquitous language

The vocabulary contract for this repo's specs, code, APIs, and concepts. When code and
this file disagree, this file wins; the code is debt to be migrated. A new term
names its prior art — the industry or stack standard it follows — or records why
none fits.

**Vocabulary polarity:** this is a **neutral engine** — it excludes outside
(product, business) vocabulary and uses only established chess and game-tree
search terminology. `.claude/rules/spec-conventions.md` and the `spec-reviewer`
agent enforce the rule in specs and concepts; when the debt column below gains
entries, `scripts/vocab-lint.sh` enforces it in code too.

## Entity model

The repo's core entities and how they nest — the spine every new public type,
field, and record must fit.

- **Engine** — the UCI process (`src/main.py` → `communication.talk`)
  - **Board** — a chess position (FEN); exposes `value()` and `is_endgame`
    - **Move** — one move in UCI long algebraic notation (e.g. `e2e4`)
  - **Searcher** — runs minimax + alpha-beta to a depth; returns the best Move
    - **TranspositionTable** — Zobrist-keyed cache of evaluated positions
      - **HashEntry** — one cached result: move, depth, value, bound `Flag`, age
  - **MoveSorter** — orders legal moves (MVV-LVA) to improve pruning

## Canonical terms

| Term | Definition | Wire / id | Replaces (now debt) |
|---|---|---|---|
| UCI | Universal Chess Interface — the text protocol the engine speaks over stdin/stdout | `uci`, `isready`, `position`, `go`, `bestmove` | |
| FEN | Forsyth–Edwards Notation — a one-line encoding of a board position | `position fen <FEN>` | |
| Move | A single move in UCI long algebraic notation | `e2e4`, `e7e8q` | |
| Minimax | The search that picks the move maximizing the engine's worst-case value | | |
| Alpha-beta pruning | Branch-and-bound that skips provably irrelevant moves during minimax | bounds `(alpha, beta)` | |
| Quiescence search | Search extension through capture sequences to avoid the horizon effect | | |
| Transposition table | Zobrist-keyed cache of evaluated positions, reused across the search | `TranspositionTable` | |
| Zobrist hash | The key identifying a position in the transposition table | `chess.polyglot.zobrist_hash` | |
| HashEntry | One transposition-table record: move, depth, value, bound flag, age | `HashEntry`, `Flag` | |
| MVV-LVA | Most Valuable Victim – Least Valuable Aggressor — capture-ordering heuristic | `move_sorter` | |
| Principal variation | The best line of play the search currently expects (planned) | `pline` | |
| Perft | Performance test — counts leaf nodes to a depth to validate move generation | `perft(depth, board)` | |
| Endgame | Late-game phase that triggers deeper search | `Board.is_endgame` | |

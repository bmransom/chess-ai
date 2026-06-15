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
field, and record must fit. The chess logic lives in the Rust core
(`brandobot_core`); the Python entrypoints (`communication.py` over UCI,
`api.py` over HTTP) are thin wrappers that hold a `Searcher`.

- **Engine** — the UCI process (`src/main.py` → `communication.talk`)
  - **Board** — a chess position (FEN); bitboards, `value()`, and `is_endgame`
    - **Move** — one move in UCI long algebraic notation (e.g. `e2e4`)
  - **Searcher** — runs negamax + alpha-beta to a depth; returns the best Move
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
| Zobrist hash | The key identifying a position in the transposition table | `Board::zobrist` | `chess.polyglot.zobrist_hash` |
| HashEntry | One transposition-table record: move, depth, value, bound flag, age | `HashEntry`, `Flag` | |
| MVV-LVA | Most Valuable Victim – Least Valuable Aggressor — capture-ordering heuristic | `movesort` | |
| Negamax | Minimax reformulated so each node negates the child's score | `negamax` | |
| Bitboard | A 64-bit word, one bit per square, encoding a piece set | `Bitboard` | |
| Magic bitboard | Perfect-hash lookup of a slider's attacks by blocker configuration | | |
| Make/unmake | Apply a Move, then reverse it, updating the Zobrist key incrementally | `make_move` / `unmake_move` | |
| Piece-square table | Per-piece, per-square positional bonus added to material in evaluation | | |
| Principal variation | The best line the search expects; reported each iteration | `principal_variation` (UCI `pv`) | `pline` |
| Iterative deepening | Search depth 1, 2, 3 … reusing each iteration's results for ordering | `SearchLimits.max_depth` | |
| Triangular PV-table | Ply-indexed array that collects the principal variation | `pv_table` | |
| Mate score | A score near ±`MATE`, offset by distance to the root; reported as `mate_in_moves` | `is_mate_score` | |
| Centipawn | Evaluation unit, one hundredth of a pawn | `score_centipawns` (UCI `cp`) | |
| Time control | The UCI clock tokens the wrapper parses into a per-move budget | `wtime`/`btime`/`winc`/`binc`/`movetime`/`movestogo` | |
| SearchLimits | The parsed per-search limits, depth and time | `SearchLimits` | |
| Perft | Performance test — counts leaf nodes to a depth to validate move generation | `perft(fen, depth)` | |
| Endgame | Late-game phase that triggers deeper search | `Board::is_endgame` | |
| brandobot_core | The Rust engine core exposed to Python as a PyO3 module | `import brandobot_core` | |

Bitboard, magic bitboard, make/unmake, piece-square table, negamax, iterative
deepening, the triangular PV-table, mate scores, and the centipawn follow
[Chess Programming Wiki](https://www.chessprogramming.org/) conventions; perft and
MVV-LVA already did. The time-control tokens are UCI; `SearchLimits` follows
Stockfish's `LimitsType`. `brandobot_core` is this repo's PyO3 module name.

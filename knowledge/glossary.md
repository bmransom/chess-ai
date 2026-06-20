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
search terminology. `rules/spec-conventions.md` and the `spec-reviewer`
agent enforce the rule in specs and concepts; when the debt column below gains
entries, `scripts/vocab-lint.sh` enforces it in code too.

## Entity model

The repo's core entities and how they nest — the spine every new public type,
field, and record must fit. The chess logic lives in the Rust core
(`brandobot_core`); the Python entrypoints (`communication.py` over UCI,
`api.py` over HTTP) are thin wrappers that hold a `Searcher`.

- **Engine** — the UCI process (`src/main.py` → `communication.talk`)
  - **Board** — a chess position (FEN); bitboards and `evaluate()`
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
| Killer move | A quiet move that caused a beta-cutoff at a ply, tried first there next time | `killers` | |
| History heuristic | A from-to score table of cutoff frequency that orders quiet moves | `history` | |
| Negamax | Minimax reformulated so each node negates the child's score | `negamax` | |
| Bitboard | A 64-bit word, one bit per square, encoding a piece set | `Bitboard` | |
| Magic bitboard | Perfect-hash lookup of a slider's attacks by blocker configuration | | |
| Make/unmake | Apply a Move, then reverse it, updating the Zobrist key incrementally | `make_move` / `unmake_move` | |
| Piece-square table | Per-piece, per-square positional bonus added to material in evaluation | | |
| Tapered evaluation | Phase-weighted blend of middlegame and endgame scores | `evaluate` | `is_endgame` |
| Game phase | A 0–24 measure of remaining non-pawn material | `game_phase` | |
| PeSTO | Public texel-tuned middlegame/endgame piece values and piece-square tables | `MG_PIECE_VALUES`, `EG_PIECE_VALUES` | |
| King safety | Score for a king's shelter and the attackers near it | `king_safety` | |
| Mobility | Score for a piece's count of available squares | `mobility` | |
| Doubled pawn | Two friendly pawns on the same file | `pawn_structure` | |
| Isolated pawn | A pawn with no friendly pawn on an adjacent file | `pawn_structure` | |
| Passed pawn | A pawn with no enemy pawns ahead on its or adjacent files | `pawn_structure` | |
| Score | A paired middlegame/endgame value, summed per term and tapered | `Score { mg, eg }` | |
| Principal variation | The best line the search expects; reported each iteration | `principal_variation` (UCI `pv`) | `pline` |
| Iterative deepening | Search depth 1, 2, 3 … reusing each iteration's results for ordering | `SearchLimits.max_depth` | |
| Triangular PV-table | Ply-indexed array that collects the principal variation | `pv_table` | |
| Mate score | A score near ±`MATE`, offset by distance to the root; reported as `mate_in_moves` | `is_mate_score` | |
| Centipawn | Evaluation unit, one hundredth of a pawn | `score_centipawns` (UCI `cp`) | |
| Time control | The UCI clock tokens the wrapper parses into a per-move budget | `wtime`/`btime`/`winc`/`binc`/`movetime`/`movestogo` | |
| SearchLimits | The parsed per-search limits, depth and time | `SearchLimits` | |
| Perft | Performance test — counts leaf nodes to a depth to validate move generation | `perft(fen, depth)` | |
| brandobot_core | The Rust engine core exposed to Python as a PyO3 module | `import brandobot_core` | |
| EPD | Extended Position Description — a FEN plus operations such as `bm` (best move) | `bench/wac.epd` | |
| Solve-rate | The fraction of EPD positions whose searched move matches a `bm` move | `epd_suite.py` | |
| Self-play | Two engine builds playing a match to compare strength | `selfplay.py` | |
| Elo | A rating-difference estimate from a match's score rate | `selfplay.py` | |
| SPRT | Sequential probability ratio test — accepts H0 or H1 once the log-likelihood ratio crosses a Wald bound | `sprt.py` | |
| Pentanomial GSPRT | A generalized SPRT over the five outcomes of a color-swapped game pair | `log_likelihood_ratio` | |
| Node limit | A fixed node budget per search, for deterministic equal-effort play | `go nodes`, `SearchLimits.node_limit` | |
| UHO opening book | An unbalanced-human-openings book that raises the decisive rate | `fetch_uho.py` | |

Bitboard, magic bitboard, make/unmake, piece-square table, tapered evaluation,
game phase, PeSTO, king safety, mobility, the doubled/isolated/passed pawn terms,
negamax, iterative deepening, the triangular PV-table, mate
scores, the centipawn, and the killer and history heuristics follow
[Chess Programming Wiki](https://www.chessprogramming.org/) conventions; Score
follows Stockfish `make_score` / `Score`; perft, MVV-LVA, EPD, Elo, and self-play
already did. The time-control tokens are UCI;
`SearchLimits` follows Stockfish's `LimitsType`. `brandobot_core` is this repo's
PyO3 module name. SPRT follows Wald 1945 and Fishtest; the pentanomial GSPRT
follows Michel Van den Bergh / Fishtest `LLRcalc`; the node limit follows UCI
`go nodes` and Stockfish `LimitsType`; the UHO opening book is
`official-stockfish/books` (CC0).

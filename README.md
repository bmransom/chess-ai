# brandobot — a chess engine

brandobot is a chess engine with a native **Rust core** (`brandobot_core`, a PyO3
module) that owns all chess logic, fronted by two thin Python wrappers: a UCI
engine over stdin/stdout and a Flask HTTP API.

## Play it

Challenge it on lichess: https://lichess.org/@/brandobot. Classical time controls
are preferred.

## What's inside

The Rust core (`core/`) implements:

- **Bitboard move generation** with a perft suite for validation
- **Tapered PeSTO evaluation** with king safety
- **Iterative-deepening negamax** with alpha-beta pruning and quiescence search
- **Move ordering** — MVV-LVA plus killer-move and history heuristics
- A **transposition table** and **time management**

Two production entrypoints wrap the core:

- **UCI engine** — `src/main.py`, bridged to lichess via
  [lichess-bot](https://github.com/lichess-bot-devs/lichess-bot)
- **HTTP API** — `src/api.py` (Flask): `POST /next_move {fen}` → `{move}`,
  `GET /transposition_table`, `GET /decision_tree`

## Run it locally

A one-time setup needs a [Rust toolchain](https://rustup.rs):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/maturin develop --release -m core/Cargo.toml   # build the Rust core into the venv
```

Then:

```bash
.venv/bin/python src/main.py     # UCI engine (type: uci, isready, go, quit)
.venv/bin/python src/api.py      # Flask HTTP API
.venv/bin/python src/perft.py    # move-generation benchmark
scripts/check-fast.sh            # the gate: fmt/clippy/test + maturin + ruff + pytest + knowledge
```

See [`AGENTS.md`](AGENTS.md) for the full command list and contributor workflow.

## Deploy to lichess

[lichess-bot](https://github.com/lichess-bot-devs/lichess-bot) bridges the engine
to lichess: clone it as a sibling repo, build the native core (above), and point
its engine configuration at the UCI entrypoint (`python src/main.py`). For a
standalone binary, package the entrypoint with `pyinstaller src/main.py`.

## Debugging the search

The HTTP API exposes the engine's reasoning: `GET /decision_tree` returns the
captured search tree for the last position, and `GET /transposition_table` dumps
the cache. The Rust core records the tree to a configurable depth.

## Roadmap

Tracked work lives on the board in [`roadmap/ROADMAP.md`](roadmap/ROADMAP.md);
ideas not yet committed sit in [`roadmap/BACKLOG.md`](roadmap/BACKLOG.md). The
vocabulary contract is [`knowledge/glossary.md`](knowledge/glossary.md).

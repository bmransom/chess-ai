Chess AI is **brandobot**, a chess engine. A native Rust core (`core/`, the
`brandobot_core` PyO3 module) owns all chess logic — bitboard move generation,
evaluation, iterative-deepening negamax with alpha-beta, quiescence, MVV-LVA
ordering, a transposition table, and time management. Two thin Python wrappers
are the production entrypoints: a
UCI engine over stdin/stdout (`src/main.py`, bridged to lichess via lichess-bot)
and a Flask HTTP API (`src/api.py`).

## Commands

```bash
# one-time setup: needs a Rust toolchain (https://rustup.rs)
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/maturin develop --release -m core/Cargo.toml   # build the Rust core into the venv
scripts/check-fast.sh            # canonical gate: cargo fmt/clippy/test + maturin + ruff + pytest + knowledge
.venv/bin/python src/main.py     # run the UCI engine (type: uci, isready, go, quit)
.venv/bin/python src/api.py      # run the Flask HTTP API
.venv/bin/python src/perft.py    # move-generation benchmark
scripts/board.sh                 # render the kanban board from roadmap/ROADMAP.md
```

Pre-push runs the same gate: run `scripts/install-hooks.sh` once per clone;
bypass once with `git push --no-verify`.

## Boundaries

**Never**
- Introduce vocabulary from outside the chess and game-tree-search domain. This
  is a neutral engine; `knowledge/glossary.md` is the contract.
- Edit a foundry verbatim file (marked `foundry-template:`) by hand — update via
  `/foundry:update`.
- `git add -A`. Stage explicit paths only — an untracked junk file named `\`
  (an old `searcher.py` copy) sits in the tree.

**Always**
- Use the `knowledge/glossary.md` vocabulary in records, APIs, and concepts — it
  is the contract.
- Before coining a canonical name (glossary term, public type or field, config
  knob), search the prior art and record provenance in the glossary.
- Stage explicit paths, never `git add -A`.

**Ask first**
- Commit or push. Branch first if on the default branch.

## Writing style

The standard is Strunk & White: omit needless words; use the active voice; make
definite assertions. Lead with the point; one idea per sentence; concrete
commands, paths, and names; say it once and link to depth. Prefer a table, list,
or code block when denser than a sentence. Context-resident prose (AGENTS.md,
rules, skills) loads into every session — every needless word costs tokens each
time it loads; cut hardest there.

## Testing

- Run the gate's tests: `.venv/bin/python -m pytest -q`.
- Scope to one file: `.venv/bin/python -m pytest src/tests/next_move.py -q`, or
  run a unittest file directly: `.venv/bin/python src/tests/next_move.py`.
- Integration over mocks: unit tests drive `Board`/`Searcher`; the acceptance
  Scenario drives the real UCI engine via subprocess. No mocks.
- New feature → add a Scenario; enhancement → update it; refactor → leave it.

## Contracts

The engine exposes two contracts:
- **UCI command set** over stdin/stdout: `uci`, `isready`, `ucinewgame`,
  `position`, `go`, `quit`.
- **HTTP JSON API**: `POST /next_move` `{fen}` → `{move}`; `GET
  /transposition_table`; `GET /decision_tree`.

Write the schema first; derive types from it — never parallel hand-written
types. Validate at every boundary (parse, don't trust); model request and
response with pydantic. Feature Scenarios exercise each contract through its
production entrypoint.

## Task tracking

`roadmap/ROADMAP.md` is the board; claim a card by owner; `Done` requires a
recorded gate PASS. Specs live in `roadmap/specs/<feature>/`; ideas in
`roadmap/BACKLOG.md`.

## Deeper docs

`knowledge/README.md` indexes everything · glossary · validation · specs.

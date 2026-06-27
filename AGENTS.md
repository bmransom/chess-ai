## Commands

```bash
# one-time setup: needs a Rust toolchain (https://rustup.rs)
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/maturin develop --release -m core/Cargo.toml   # build the Rust core into the venv
scripts/check-fast.sh            # canonical gate: cargo fmt/clippy/test + maturin + ruff + pytest + knowledge
.venv/bin/python src/main.py     # run the UCI engine (type: uci, isready, go, quit)
.venv/bin/python src/api.py      # run the Flask HTTP API
.venv/bin/python src/perft.py    # move-generation benchmark
.venv/bin/python scripts/epd_suite.py --movetime 100 bench/wac.epd  # tactical solve-rate
.venv/bin/python scripts/selfplay.py --games 100 --depth 4          # self-play Elo
.venv/bin/python scripts/fetch_uho.py            # provision the UHO opening book (CC0)
.venv/bin/python scripts/sprt.py --nodes 200000 --cost-check        # fair-match SPRT verdict
scripts/board.sh                 # render the kanban board from roadmap/ROADMAP.md
```

Pre-push runs the same gate: run `scripts/install-hooks.sh` once per clone;
bypass once with `git push --no-verify`.

## Boundaries

**Never**
- Introduce vocabulary from outside the chess and game-tree-search domain. This
  is a neutral engine; `knowledge/glossary.md` is the contract.

**Always**
- Use the `knowledge/glossary.md` vocabulary in records, APIs, and concepts — it
  is the domain language.
- Before coining a canonical name (glossary term, public type or field, config
  knob), search the prior art and record provenance in the glossary.
- Stage explicit paths, never `git add -A`.

**Ask first**
- Push to remote. Branch first if on the default branch.

## Writing style

Omit needless words; use the active voice; make
definite assertions. Lead with the point; one idea per sentence; concrete
commands, paths, and names; say it once and link to depth. Prefer a table, list,
or code block when denser than a sentence.

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


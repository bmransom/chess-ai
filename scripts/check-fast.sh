#!/usr/bin/env bash
# The quick gate: lock-free; runs from .githooks/pre-push and CI.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# Discover a project-local virtualenv; otherwise use the python on PATH
# (CI installs dependencies into the job's python before running this).
if [ -x "$REPO/.venv/bin/python" ]; then
  PY="$REPO/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

echo "== rust core: fmt + lint + test"
# Release for the test step so the perft suite (millions of nodes) stays fast.
( cd "$REPO/core" && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test --release -q )

echo "== rust core: build + install brandobot_core"
# Build the extension and install it where pytest will import it. A project-local
# venv gets an incremental `maturin develop`; CI (no venv) installs the package
# with pip using the already-present maturin backend (--no-build-isolation).
if [ -x "$REPO/.venv/bin/maturin" ]; then
  VIRTUAL_ENV="$REPO/.venv" "$REPO/.venv/bin/maturin" develop --release --manifest-path "$REPO/core/Cargo.toml"
else
  "$PY" -m pip install -q --no-build-isolation --force-reinstall --no-deps "$REPO/core"
fi

echo "== lint"
"$PY" -m ruff check .

echo "== tests"
"$PY" -m pytest -q

echo "== knowledge"
"$PY" scripts/knowledge.py check

echo "check-fast: PASS"

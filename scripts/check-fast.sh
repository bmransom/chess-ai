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

echo "== lint"
"$PY" -m ruff check .

echo "== tests"
"$PY" -m pytest -q

echo "== knowledge"
"$PY" scripts/knowledge.py check

echo "check-fast: PASS"

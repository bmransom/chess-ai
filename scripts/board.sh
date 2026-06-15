#!/usr/bin/env bash
# foundry-template: board v1
#
# Render the tracked kanban board — the Status Dashboard in roadmap/ROADMAP.md —
# to the terminal, with a per-column count. The board is the markdown; this is
# just a view. Pass a status word to filter (e.g. `scripts/board.sh "In Progress"`).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROADMAP="$REPO/roadmap/ROADMAP.md"
[ -f "$ROADMAP" ] || { echo "board: $ROADMAP not found" >&2; exit 1; }

filter="${1:-}"

# Extract the "## Status Dashboard" section (up to the next top-level "## ").
dashboard="$(awk '
  /^## Status Dashboard/ {grab=1; next}
  grab && /^## / {exit}
  grab {print}
' "$ROADMAP")"

if [ -n "$filter" ]; then
  # Print only the "### <filter>" column block.
  echo "$dashboard" | awk -v want="$filter" '
    /^### / {col = (tolower($0) ~ tolower(want))}
    col {print}
  '
  exit 0
fi

echo "Board — roadmap/ROADMAP.md (Backlog → Ready → In progress → Validating → Done)"
echo ""
echo "$dashboard"
echo ""
echo "Columns (rows per ### section):"
echo "$dashboard" | awk '
  /^### / {name=substr($0,5); next}
  /^\| / && name != "" && $0 !~ /^\|[ -]*\|/ && $0 !~ /Work/ {count[name]++}
  END {for (c in count) printf "  %-14s %d\n", c, count[c]}
'

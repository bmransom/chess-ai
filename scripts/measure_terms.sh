#!/usr/bin/env bash
# Measure one evaluation term with the fair-match SPRT.
#
# Builds a candidate commit and a baseline commit in throwaway git worktrees,
# each with its own venv and native core, then plays a pentanomial SPRT between
# them. A strict [0,5] verdict can need thousands of pairs (a multi-hour run);
# Ctrl-C stops it and prints the running counts.
#
#   scripts/fetch_uho.py                                  # provision the book first
#   scripts/measure_terms.sh <candidate> <baseline> [extra sprt.py args...]
#
# The eval terms form a linear chain (PeSTO+KS -> +mobility -> +pawn-structure):
#   King safety:     main                vs eval-no-king-safety   (PeSTO only)
#   Mobility:        08bfce1             vs main
#   Pawn structure:  fc89b26 (HEAD)      vs 08bfce1
#
# Example:
#   scripts/measure_terms.sh 08bfce1 main --nodes 50000 --max-pairs 40000 --cost-check
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
candidate="${1:?candidate commit required}"
baseline="${2:?baseline commit required}"
shift 2

work="$REPO/.measure"
cleanup() {
  git -C "$REPO" worktree remove --force "$work/candidate" 2>/dev/null || true
  git -C "$REPO" worktree remove --force "$work/baseline" 2>/dev/null || true
}
trap cleanup EXIT

build() { # <commit> <name>; echoes the engine command on stdout
  local commit="$1" dir="$work/$2"
  git -C "$REPO" worktree add --force --detach "$dir" "$commit" >&2
  python3 -m venv "$dir/.venv" >&2
  "$dir/.venv/bin/pip" install -q -r "$dir/requirements-dev.txt" >&2
  "$dir/.venv/bin/maturin" develop --release -m "$dir/core/Cargo.toml" >&2
  echo "$dir/.venv/bin/python $dir/src/main.py"
}

echo "building candidate ($candidate)..." >&2
candidate_cmd="$(build "$candidate" candidate)"
echo "building baseline ($baseline)..." >&2
baseline_cmd="$(build "$baseline" baseline)"

echo "SPRT: candidate ($candidate) vs baseline ($baseline)" >&2
"$REPO/.venv/bin/python" "$REPO/scripts/sprt.py" \
  --engine1 "$candidate_cmd" --engine2 "$baseline_cmd" "$@"

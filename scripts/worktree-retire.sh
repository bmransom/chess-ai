#!/usr/bin/env bash
# foundry-template: worktree-retire v1
#
# Retire a git worktree WITHOUT silently losing gitignored notes.
#
# `git worktree remove` deletes gitignored files with no warning; it only
# refuses on *untracked-but-not-ignored* files, never on ignored ones. This
# wrapper enumerates the worktree's gitignored files with the one command that
# lists them individually — `git ls-files --others --ignored --exclude-standard`
# (`git status --ignored` collapses a directory to a single line and misses
# them) — and REFUSES to remove a worktree that still holds un-promoted notes.
#
# Promote durable notes to the TRACKED tree first (roadmap/ROADMAP.md, roadmap/specs/,
# roadmap/BACKLOG.md), commit, then retire. `--force` deletes anyway.
#
# `--delete-branch` also deletes the worktree's branch after removal — `git
# branch -d` (merge-safe; refuses an unmerged branch), or `git branch -D` under
# `--force`. Run it from within the owning repo. Branch deletion runs only after
# note-protection and worktree removal succeed.
#
# Usage: scripts/worktree-retire.sh <worktree-path> [--force] [--delete-branch]
set -euo pipefail

force=0
delete_branch=0
wt=""
for arg in "$@"; do
  case "$arg" in
    --force) force=1 ;;
    --delete-branch) delete_branch=1 ;;
    -*) echo "worktree-retire: unknown flag $arg" >&2; exit 2 ;;
    *) wt="$arg" ;;
  esac
done
[ -n "$wt" ] || { echo "usage: scripts/worktree-retire.sh <worktree-path> [--force] [--delete-branch]" >&2; exit 2; }
[ -d "$wt" ] || { echo "worktree-retire: not a directory: $wt" >&2; exit 2; }

# Record the branch before removal so we can delete it afterward.
branch=""
[ "$delete_branch" -eq 1 ] && branch="$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"

# Durable-note patterns we refuse to drop on the floor.
note_re='(^|/)(.*followup|.*handoff|.*scratch|.*notes|TODO)'

strays="$(git -C "$wt" ls-files --others --ignored --exclude-standard 2>/dev/null \
  | grep -vE '(^|/)(node_modules|target)/' \
  | grep -iE "$note_re" || true)"

if [ -n "$strays" ] && [ "$force" -eq 0 ]; then
  echo "worktree-retire: REFUSING to remove $wt — it holds un-promoted gitignored notes:" >&2
  echo "$strays" | sed 's/^/    /' >&2
  echo "" >&2
  echo "  These are NOT in git and will be lost on removal. Promote what matters to the" >&2
  echo "  tracked tree (roadmap/ROADMAP.md, roadmap/specs/, roadmap/BACKLOG.md), commit," >&2
  echo "  then retire. Or re-run with --force to delete them anyway." >&2
  exit 1
fi

if [ "$force" -eq 1 ]; then
  echo "worktree-retire: removing $wt (--force)"
  git worktree remove --force "$wt"
else
  echo "worktree-retire: removing $wt"
  git worktree remove "$wt"
fi
git worktree prune

if [ "$delete_branch" -eq 1 ] && [ -n "$branch" ]; then
  if [ "$force" -eq 1 ]; then
    echo "worktree-retire: deleting branch $branch (--force)"
    git branch -D "$branch"
  else
    echo "worktree-retire: deleting branch $branch"
    git branch -d "$branch"
  fi
fi
echo "worktree-retire: done."

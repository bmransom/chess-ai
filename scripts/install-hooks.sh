#!/usr/bin/env bash
# foundry-template: install-hooks v1
# One-time per clone: route git hooks through .githooks/.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
hook_count="$(find .githooks -maxdepth 1 -type f | wc -l | tr -d ' ')"
[ "$hook_count" -gt 0 ] || { echo "install-hooks: no hook files in .githooks/ — nothing to install" >&2; exit 1; }
git config core.hooksPath .githooks
find .githooks -maxdepth 1 -type f -exec chmod +x {} +
echo "hooks installed (core.hooksPath=.githooks, $hook_count hook(s))"

#!/usr/bin/env bash
# derive-census-clean.sh [git-ref] — regenerate tests/census_snapshot.json
# via `maicdb-census --write` in a clean detached worktree of <ref>
# (default HEAD), with the vault sibling symlinked into /tmp.
#
# Born 2026-11-15 (derived-census-pins): the snapshot must be regenerated
# from a clean tree so the diff a reviewer sees is exactly the freeze
# delta, not working-tree noise (same discipline as derive-pins-clean.sh).
# The regenerated snapshot is copied back into the real tree; review it
# with `git diff tests/census_snapshot.json`. Cleans up the worktree on
# exit. The /tmp symlink is left behind (harmless, /tmp is ephemeral —
# same as derive-pins-clean.sh; a trap-time rm would race a concurrent
# derive run still using the symlink).
set -euo pipefail
ref="${1:-HEAD}"
repo="$(git rev-parse --show-toplevel)"
wt=$(mktemp -d /tmp/maicdb-census-XXXXXX)
cleanup() { git -C "$repo" worktree remove --force "$wt" >/dev/null 2>&1 || true; }
trap cleanup EXIT
git -C "$repo" worktree add --detach "$wt" "$ref" >/dev/null
vault_src="$repo/../Project_DataBase_MAICDB"
if [ -d "$vault_src" ]; then
    ln -sfn "$(cd "$vault_src" && pwd)" /tmp/Project_DataBase_MAICDB
fi
cd "$wt"
uv sync --quiet
uv run maicdb-census --write
cp tests/census_snapshot.json "$repo/tests/census_snapshot.json"
echo "regenerated $repo/tests/census_snapshot.json — review with: git diff tests/census_snapshot.json"

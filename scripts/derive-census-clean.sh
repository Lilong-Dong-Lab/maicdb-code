#!/usr/bin/env bash
# derive-census-clean.sh [git-ref] — regenerate tests/census_snapshot.json
# via `maicdb-census --write` in a clean detached worktree of <ref>
# (default HEAD), with $MAICDB_VAULT exported to the sibling checkout
# (resolved by the vault seam, maicdb.vault.resolve_vault).
#
# Born 2026-11-15 (derived-census-pins): the snapshot must be regenerated
# from a clean tree so the diff a reviewer sees is exactly the freeze
# delta, not working-tree noise (same discipline as derive-pins-clean.sh).
# The regenerated snapshot is copied back into the real tree; review it
# with `git diff tests/census_snapshot.json`. Cleans up the worktree on
# exit; nothing is left behind.
set -euo pipefail
ref="${1:-HEAD}"
repo="$(git rev-parse --show-toplevel)"
wt=$(mktemp -d /tmp/maicdb-census-XXXXXX)
cleanup() { git -C "$repo" worktree remove --force "$wt" >/dev/null 2>&1 || true; }
trap cleanup EXIT
git -C "$repo" worktree add --detach "$wt" "$ref" >/dev/null
vault_src="$repo/../Project_DataBase_MAICDB"
if [ -d "$vault_src" ]; then
    export MAICDB_VAULT="$(cd "$vault_src" && pwd)"
fi
cd "$wt"
uv sync --quiet
uv run maicdb-census --write
cp tests/census_snapshot.json "$repo/tests/census_snapshot.json"
echo "regenerated $repo/tests/census_snapshot.json — review with: git diff tests/census_snapshot.json"

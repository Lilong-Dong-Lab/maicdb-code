#!/usr/bin/env bash
# derive-pins-clean.sh [git-ref] — run scripts/check-suite-matrix.sh
# --derive in a clean detached worktree of <ref> (default HEAD), with the
# vault sibling symlinked into /tmp so the local-with-vault state resolves.
#
# Born 2026-11-05 retro: check-suite-matrix.sh refuses a dirty tree, but
# the working tree often carries the operator's unrelated files — the
# manual dance (worktree add → symlink vault → uv sync → derive → remove)
# ran four times the day the analysis layer landed. This wraps it.
# Cleans up the worktree on exit; the /tmp symlink is left (harmless,
# /tmp is ephemeral). Output: the three executed signatures + the re-pin
# edit list, exactly as --derive prints them.
set -euo pipefail
ref="${1:-HEAD}"
repo="$(git rev-parse --show-toplevel)"
wt=$(mktemp -d /tmp/maicdb-derive-XXXXXX)
cleanup() { git -C "$repo" worktree remove --force "$wt" >/dev/null 2>&1 || true; }
trap cleanup EXIT
git -C "$repo" worktree add --detach "$wt" "$ref" >/dev/null
vault_src="$repo/../Project_DataBase_MAICDB"
if [ -d "$vault_src" ]; then
    ln -sfn "$(cd "$vault_src" && pwd)" /tmp/Project_DataBase_MAICDB
fi
cd "$wt"
uv sync --quiet
bash scripts/check-suite-matrix.sh --derive

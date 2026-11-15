#!/usr/bin/env bash
# derive-pins-clean.sh [git-ref] — run scripts/check-suite-matrix.sh
# --derive in a clean detached worktree of <ref> (default HEAD), with the
# vault sibling symlinked into /tmp so the local-with-vault state resolves.
#
# Born 2026-11-05 retro: check-suite-matrix.sh refuses a dirty tree, but
# the working tree often carries the operator's unrelated files — the
# manual dance (worktree add → symlink vault → uv sync → derive → remove)
# ran four times the day the analysis layer landed. This wraps it.
#
# Re-pin order when a PR changes test counts (taught here, one place;
# first written down retro 2026-11-15, post-PR-89): (1) commit the code
# with --no-verify — the hook's signature guard blocks BY DESIGN until
# the pins match reality, so the bypass is the sanctioned first step,
# not a failure; (2) run this script; (3) apply the printed edit list
# (ci.yml + KNOWN-QUIRKS quirk 3); (4) commit the re-pin — it passes the
# hook cleanly; (5) run the full verdict: bash
# scripts/check-suite-matrix.sh (no args) → "matrix OK".
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

#!/usr/bin/env bash
# check-suite-matrix.sh — derive the three suite-state signatures by
# EXECUTION and compare them against the pins declared in
# .github/workflows/ci.yml (the single source of truth).
#
# Born 2026-10-24 (retro): the no-tag signature was once extrapolated
# from a stale test count (62/12 vs the real 61/13) — this script makes
# the pin discipline observational, not arithmetical.
#
# States:
#   local    full suite, vault if present            (reported, not pinned)
#   novault  MAICDB_VAULT=/nonexistent               (must match a ci.yml pin)
#   notag    shallow --no-tags clone of this HEAD    (must match the other pin;
#            more skips than novault — the signature ci.yml's error names)
#
# Usage: scripts/check-suite-matrix.sh    (after `uv sync`; needs git)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
CI_FILE=".github/workflows/ci.yml"

fail() { echo "check-suite-matrix: $*" >&2; exit 1; }
note() { printf '  %s\n' "$1"; }

# --- declared signatures: the numbers inside ci.yml's grep anchors ------
DECLARED=()
while IFS= read -r line; do DECLARED+=("$line"); done < <(
    grep -oE '[0-9]+ passed, [0-9]+ skipped, 1 warning' "$CI_FILE" | sort -u
)
[ "${#DECLARED[@]}" -eq 2 ] ||
    fail "expected exactly 2 declared signatures in $CI_FILE, found ${#DECLARED[@]}: ${DECLARED[*]}"
[ -x "$REPO_ROOT/.venv/bin/python" ] || fail ".venv missing — run uv sync first"
command -v git >/dev/null 2>&1 || fail "git not found"

matches_declared() { # summary -> success if it contains either signature
    local s="$1" d
    for d in "${DECLARED[@]}"; do [[ "$s" == *"$d"* ]] && return 0; done
    return 1
}
skips_of() { sed -E 's/.*[^0-9]([0-9]+) skipped.*/\1/' <<<"$1"; }

echo "Running the three suite states (each against the pins in $CI_FILE):"

# --- state 1: local (vault if present) — reported, not pinned -----------
LOCAL_SUMMARY="$(PYTHONPATH=src uv run pytest tests/ -q 2>&1 | tail -1)"
note "local   : $LOCAL_SUMMARY"

# --- state 2: no vault (the CI condition, tags present) ------------------
NOVAULT_SUMMARY="$(PYTHONPATH=src MAICDB_VAULT=/nonexistent uv run pytest tests/ -q 2>&1 | tail -1)"
note "novault : $NOVAULT_SUMMARY"
matches_declared "$NOVAULT_SUMMARY" ||
    fail "novault summary does not match a declared pin (declared: ${DECLARED[*]})"

# --- state 3: no tag (shallow clone of this HEAD) ------------------------
if [ -n "$(git status --porcelain)" ]; then
    note "WARNING: dirty working tree — the notag state clones HEAD, so"
    note "uncommitted test/pin changes are NOT reflected in it. Commit first,"
    note "then re-run for a verdict on the pushed state."
fi
TMP_CLONE="$(mktemp -d)"
trap 'rm -rf "$TMP_CLONE"' EXIT
git clone --depth 1 --no-tags --quiet "file://$REPO_ROOT" "$TMP_CLONE"
NOTAG_SUMMARY="$(cd "$TMP_CLONE" && PYTHONPATH=src MAICDB_VAULT=/nonexistent \
    "$REPO_ROOT/.venv/bin/python" -m pytest tests/ -q 2>&1 | tail -1)"
note "notag   : $NOTAG_SUMMARY"
matches_declared "$NOTAG_SUMMARY" ||
    fail "notag summary does not match a declared pin (declared: ${DECLARED[*]})"

# --- the two states must map to DIFFERENT pins ----------------------------
[ "$(skips_of "$NOTAG_SUMMARY")" -gt "$(skips_of "$NOVAULT_SUMMARY")" ] ||
    fail "notag must have strictly more skips than novault (the tag-gated tests) — signatures collapsed: '${NOVAULT_SUMMARY}' vs '${NOTAG_SUMMARY}'"

echo
echo "matrix OK — both executed signatures match the declared pins, and they differ."

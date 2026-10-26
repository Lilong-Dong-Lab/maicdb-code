#!/usr/bin/env bash
# check-suite-matrix.sh — derive the three suite-state signatures by
# EXECUTION and compare them against the pins declared in
# .github/workflows/ci.yml (the single source of truth), the local
# reference comment in the same file, and the human-facing mirror of the
# pins in KNOWN-QUIRKS.md quirk 3.
#
# Born 2026-10-24 (retro): the no-tag signature was once extrapolated
# from a stale test count (62/12 vs the real 61/13) — this script makes
# the pin discipline observational, not arithmetical.
#
# States:
#   local    full suite, vault if present            (must match ci.yml's
#            "Local with-vault reference" comment)
#   novault  MAICDB_VAULT=/nonexistent               (must match a ci.yml pin)
#   notag    shallow --no-tags clone of this HEAD    (must match the other pin;
#            more skips than novault — the signature ci.yml's error names)
#
# Usage: scripts/check-suite-matrix.sh    (after `uv sync`; needs git)
# A bare `sh` invocation re-execs into bash below.

# Re-exec into bash when the running shell lacks process substitution:
# `sh scripts/check-suite-matrix.sh` died on the <() below before any
# check ran (found live 2026-10-26). $BASH_VERSION alone is the wrong
# test — macOS /bin/sh is bash in POSIX mode, which sets it while still
# disabling <() — and a raw probe subshell still parses fatal. eval
# defers parsing: its syntax error is contained (non-zero status), so
# the probe is safe in every shell.
if ! eval ': <( : )' 2>/dev/null; then
    exec bash "$0" "$@"
fi

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

# --- pin copies: KNOWN-QUIRKS quirk 3 mirrors the pins for humans ------
# ci.yml is authoritative, but its pins are re-stated in quirk 3 and a
# drifted copy is how that line went stale once already. Anchored to the
# quirk-3 table row (CODING_STANDARDS rule 1: structure, not a whole-file
# substring).
QUIRK3_ROW="$(grep -E '^\| 3 \|' KNOWN-QUIRKS.md)" ||
    fail "KNOWN-QUIRKS.md: no '| 3 |' table row found"
for d in "${DECLARED[@]}"; do
    printf '%s' "$QUIRK3_ROW" | grep -qF "$d" ||
        fail "KNOWN-QUIRKS.md quirk 3 drifted from $CI_FILE: missing '$d'"
done

[ -x "$REPO_ROOT/.venv/bin/python" ] || fail ".venv missing — run uv sync first"
command -v git >/dev/null 2>&1 || fail "git not found"

matches_declared() { # summary -> success if it contains an ANCHORED signature
    # Digit-boundary anchored, mirroring ci.yml's own grep: "178 passed"
    # must NOT match a "78 passed" pin (vacuous-pass guard).
    local s="$1" d
    for d in "${DECLARED[@]}"; do
        printf '%s' "$s" | grep -qE "(^|[^0-9])$d([^0-9]|$)" && return 0
    done
    return 1
}

# Self-test for the anchoring — runs before any state is executed.
# Vectors derive from DECLARED, so a re-pin cannot break the checker
# itself (found live on PR #24: hardcoded 78/61 vectors failed the
# moment the pins moved). "1$d" probes the leading digit boundary —
# "179 passed" must NOT match a "79 passed" pin.
self_test() {
    local ok=1 d
    for d in "${DECLARED[@]}"; do
        matches_declared "========================= $d =========================" || ok=0
        matches_declared "1$d" && ok=0
    done
    matches_declared "2 passed, 0 skipped, 1 warning" && ok=0
    matches_declared "all good, no summary here" && ok=0
    [ "$ok" -eq 1 ] || fail "self-test failed: matches_declared anchoring is broken"
}
self_test
skips_of() { sed -E 's/.*[^0-9]([0-9]+) skipped.*/\1/' <<<"$1"; }

echo "Running the three suite states (each against the pins in $CI_FILE):"

# --- state 1: local (vault if present) — pinned to ci.yml's reference ---
LOCAL_SUMMARY="$(PYTHONPATH=src uv run pytest tests/ -q 2>&1 | tail -1)"
note "local   : $LOCAL_SUMMARY"
LOCAL_REF="$(sed -nE 's/.*Local with-vault reference: ([0-9]+) passed.*/\1/p' "$CI_FILE")"
[ -n "$LOCAL_REF" ] ||
    fail "$CI_FILE: no 'Local with-vault reference: N passed' comment found"
LOCAL_PASSED="$(sed -E 's/.*[^0-9]([0-9]+) passed.*/\1/' <<<"$LOCAL_SUMMARY")"
[ "$LOCAL_PASSED" = "$LOCAL_REF" ] ||
    fail "local run says $LOCAL_PASSED passed but $CI_FILE's reference comment pins $LOCAL_REF — if the run is genuine, re-pin the comment and KNOWN-QUIRKS quirk 3 together (bash scripts/check-suite-matrix.sh derives, never arithmetic)"

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
echo "matrix OK — both executed signatures match the declared pins and differ,"
echo "the local reference matches ci.yml, and quirk 3 mirrors the pins."

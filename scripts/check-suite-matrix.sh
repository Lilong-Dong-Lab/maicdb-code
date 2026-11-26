#!/usr/bin/env bash
# check-suite-matrix.sh — derive the three suite-state signatures by
# EXECUTION and compare them against the pins declared in
# tests/suite-signatures.json (the single source of truth). The
# historical ci.yml/KNOWN-QUIRKS copies are prose only; pin changes edit
# the JSON once.
#
# Born 2026-10-24 (retro): the no-tag signature was once extrapolated
# from a stale test count (62/12 vs the real 61/13) — this script makes
# the pin discipline observational, not arithmetical.
#
# States:
#   local    full suite, vault if present            (must match the JSON
#            local reference)
#   novault  MAICDB_VAULT=/nonexistent               (must match a JSON pin)
#   notag    shallow --no-tags clone of this HEAD    (must match the other pin;
#            more skips than novault — the signature CI's error names)
#
# Usage: scripts/check-suite-matrix.sh            full: execute + compare (the verdict)
#       scripts/check-suite-matrix.sh --pins      static declared-pin sanity only
#       scripts/check-suite-matrix.sh --derive    execute the three states, print
#                                                  signatures + the complete re-pin
#                                                  edit list, compare nothing
# (after `uv sync`; needs git). Invoke via `bash` — every caller does
# (pre-commit, CI); this script uses arrays, <(), and ${!var}, all
# bash-only.

# Re-exec into bash when the running shell lacks process substitution:
# `sh scripts/check-suite-matrix.sh` died on the <() below before any
# check ran (found live 2026-10-26). $BASH_VERSION alone is the wrong
# test — macOS /bin/sh is bash in POSIX mode, which sets it while still
# disabling <() — and a raw probe subshell still parses fatal. eval
# defers parsing: its syntax error is contained (non-zero status) in
# bash-as-sh, where the probe was verified. LIMIT, found live
# 2026-11-02 (PR #54 retro): on dash the eval parse error is FATAL to
# the whole shell (exit 2, message swallowed by the probe's redirect)
# — the re-exec never runs. The probe is best-effort for bash-as-sh;
# dash users must call bash directly (see usage above).
if ! eval ': <( : )' 2>/dev/null; then
    exec bash "$0" "$@"
fi

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
PIN_FILE="tests/suite-signatures.json"
READ_PIN=("$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/scripts/read-suite-pin.py")

skips_of() { sed -E 's/.*[^0-9]([0-9]+) skipped.*/\1/' <<<"$1"; }

fail() { echo "check-suite-matrix: $*" >&2; exit 1; }
note() { printf '  %s\n' "$1"; }

# --- declared signatures: the JSON file is the only source of truth ------
DECLARED=("$("${READ_PIN[@]}" novault)" "$("${READ_PIN[@]}" notag)")
local_signature="$("${READ_PIN[@]}" local passed)"
local_collected="$("${READ_PIN[@]}" local collected)"
case "$local_signature" in
    ''|*[!0-9]*) fail "$PIN_FILE: local.passed must be a positive integer" ;;
esac
case "$local_collected" in
    *[!0-9]*) local_collected="${local_collected%% tests collected}" ;;
esac
case "$local_collected" in
    ''|*[!0-9]*) fail "$PIN_FILE: local.collected must be a positive integer" ;;
esac
[ "$local_collected" -gt 0 ] || fail "$PIN_FILE: local.collected must be positive"
[ "$local_signature" -gt 0 ] || fail "$PIN_FILE: local.passed must be positive"
[ "$local_collected" -ge "$local_signature" ] ||
    fail "$PIN_FILE: local.collected must be at least local.passed"
[ "$(skips_of "${DECLARED[0]}")" -gt 0 ] ||
    fail "$PIN_FILE: novault.skipped must be positive"
[ "$(skips_of "${DECLARED[1]}")" -gt "$(skips_of "${DECLARED[0]}")" ] ||
    fail "$PIN_FILE: notag must skip more tests than novault"

matches_declared() { # summary -> success if it contains an ANCHORED signature
    # Digit-boundary anchored, mirroring CI's own grep: "178 passed"
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

# --- static mode (--pins): declared-pin sanity only, no suite execution --
# Wired into .githooks/run-suite.sh and CI. Catches stray signature-shaped
# literals is obsolete because the JSON file is the only source. Needs no
# venv and no git objects: a fresh clone's first commit checks pins
# without blocking on uv sync.
# 2026-10-26 retro.
if [ "${1:-}" = "--pins" ]; then
    echo "pins OK — suite signatures single-sourced in $PIN_FILE: ${DECLARED[*]}"
    exit 0
fi

[ -x "$REPO_ROOT/.venv/bin/python" ] || fail ".venv missing — run uv sync first"
command -v git >/dev/null 2>&1 || fail "git not found"

# The bare signature only — the executed line carries pytest's ====
# decoration and wall-clock duration, which must never enter a grep
# anchor (the next run's timing would fail it forever).
bare_of() { grep -oE '[0-9]+ passed, [0-9]+ skipped, [0-9]+ warning' <<<"$1" | head -1; }

# Dirty tree = no verdict, so fail up front instead of warning after the
# runs: the notag state (below) clones HEAD, so uncommitted test/pin
# changes never reach it — and the stale HEAD can pair with the
# still-uncommitted old pin into a FALSE "matrix OK" (observed live
# 2026-11-02, PR #50 gate MAJOR: the notag run echoed the pre-change pin,
# and the invalid "unchanged" conclusion reached the PR body until the
# gate reviewer's clean-tree run exited 1). --pins (pre-commit + CI)
# exits above and never reaches this block.
#
# Only TRACKED changes and UNTRACKED TEST-LOADABLE files dirty the
# verdict (retro 2026-11-04, item 4): local/novault run in this tree,
# the notag clone carries tracked content only — so anything pytest can
# LOAD here but the clone lacks is a real divergence. That is untracked
# tests/ files (testpaths=["tests"], incl. folded dirs and non-ASCII
# names — hence core.quotepath=false) AND the four root-level pytest
# config files, which pytest reads ahead of pyproject's
# [tool.pytest.ini_options] (none of the four is tracked here; gate
# round 1 proved an untracked root conftest.py diverges the states).
# Any other untracked file is invisible to all three states, so it
# passes — ending the mv-away-and-back ritual the machine-local docs
# forced on every derive. Each grep may legitimately match nothing;
# the `|| true` keeps the empty result from tripping set -e.
status="$(git -c core.quotepath=false status --porcelain)"
blocking="$( { printf '%s' "$status" | grep -v '^??' || true; }
             printf '%s' "$status" | \
               grep -E '^\?\? (tests/|conftest\.py|pytest\.ini|tox\.ini|setup\.cfg)' || true )"
[ -z "$blocking" ] ||
    fail "dirty working tree — tracked changes or untracked test-loadable files (tests/, root conftest.py/pytest.ini/tox.ini/setup.cfg) are not reflected in the notag state (an old-HEAD pass is not a verdict on the pushed state). Commit, then re-run. (Other untracked files are tolerated — invisible to all three states.)"

# --- shared state runners (full mode + --derive) --------------------------
run_local_state()   { PYTHONPATH=src uv run pytest tests/ -q 2>&1 | tail -1; }
run_novault_state() { PYTHONPATH=src MAICDB_VAULT=/nonexistent uv run pytest tests/ -q 2>&1 | tail -1; }
run_notag_state() { # shallow no-tags clone of this HEAD, run there, clean up
    local tmp
    tmp="$(mktemp -d)"
    # RETURN trap, not a trailing rm: under set -e an aborting clone or
    # pytest must not leak the mktemp dir (origin/main's script-wide EXIT
    # trap covered this; the extraction into a function dropped it —
    # gate NIT, PR #55)
    trap 'rm -rf "$tmp"' RETURN
    git clone --depth 1 --no-tags --quiet "file://$REPO_ROOT" "$tmp"
    (cd "$tmp" && PYTHONPATH=src MAICDB_VAULT=/nonexistent \
        "$REPO_ROOT/.venv/bin/python" -m pytest tests/ -q 2>&1 | tail -1)
}

# --- derive mode (--derive): gather-only, no comparison --------------------
# Prints all three executed signatures and the COMPLETE re-pin edit list,
# then exits 0. Born 2026-11-02 (PR #54 retro): the full mode below stops
# at the FIRST mismatching state with one sed suggestion at a time, so a
# re-pin round meant commit→run→edit→commit loops; agents worked around
# it by running this script's own state commands verbatim to gather all
# signatures in one pass (PR #54 did that twice). --derive is the
# workaround wired in. Contract: the clean-tree guard above already
# enforced the precondition — commit the test/code change FIRST (the
# notag state clones HEAD, so uncommitted test edits never reach it).
# After applying the suggestions, the FULL mode is still the verdict.
if [ "${1:-}" = "--derive" ]; then
    pin_for_skips() { # skip-count -> the declared pin carrying it
        local s="$1" d
        for d in "${DECLARED[@]}"; do
            [ "$(skips_of "$d")" = "$s" ] && { printf '%s' "$d"; return 0; }
        done
        return 1
    }
    LOCAL_SUMMARY="$(run_local_state)"
    NOVAULT_SUMMARY="$(run_novault_state)"
    NOTAG_SUMMARY="$(run_notag_state)"
    echo "derive: executed signatures (gather-only — apply, then run the FULL mode for the verdict):"
    note "local   : $LOCAL_SUMMARY"
    note "novault : $NOVAULT_SUMMARY"
    note "notag   : $NOTAG_SUMMARY"
    echo
    echo "derive: re-pin edits —"
    changed=0
    for state in NOVAULT NOTAG; do
        summary_var="${state}_SUMMARY"
        executed="${!summary_var}"
        old_pin="$(pin_for_skips "$(skips_of "$executed")")" || {
            note "$state: no declared pin shares its skip count — add a third state only if one was genuinely added; otherwise investigate the drift"
            changed=1
            continue
        }
        new_pin="$(bare_of "$executed")"
        if [ "$new_pin" = "$old_pin" ]; then
            note "$state: in sync ('$old_pin')"
            continue
        fi
        changed=1
        echo "  update $PIN_FILE: $state.passed $(sed -E 's/.* ([0-9]+) passed.*/\1/' <<<"$old_pin") -> $(sed -E 's/.* ([0-9]+) passed.*/\1/' <<<"$new_pin")   # $state pin"
    done
    new_ref="$(sed -E 's/.*[^0-9]([0-9]+) passed.*/\1/' <<<"$LOCAL_SUMMARY")"
    if [ "$new_ref" = "$local_signature" ]; then
        note "local reference: in sync ($local_signature passed; $local_collected collected)"
    else
        changed=1
        echo "  update $PIN_FILE: local.passed $local_signature -> $new_ref; re-derive local.collected with pytest --collect-only -q"
    fi
    [ "$changed" -eq 0 ] && echo "  (all in sync — nothing to re-pin)"
    echo
    echo "derive: after applying, run the FULL mode — bash $0 — and require 'matrix OK'."
    exit 0
fi

echo "Running the three suite states (each against the pins in $PIN_FILE):"

# --- state 1: local (vault if present) — pinned to the JSON reference ---
LOCAL_SUMMARY="$(run_local_state)"
note "local   : $LOCAL_SUMMARY"
LOCAL_PASSED="$(sed -E 's/.*[^0-9]([0-9]+) passed.*/\1/' <<<"$LOCAL_SUMMARY")"
if [ "$LOCAL_PASSED" != "$local_signature" ]; then
    fail "local run says $LOCAL_PASSED passed but $PIN_FILE pins $local_signature — if the run is genuine, update local.passed (bash scripts/check-suite-matrix.sh derives, never arithmetic)"
fi

# --- state 2: no vault (the CI condition, tags present) ------------------
suggest_repin() { # executed-summary -> echo which declared pin it should replace
    local executed="$1" d bare
    bare="$(bare_of "$executed")"
    for d in "${DECLARED[@]}"; do
        if [ "$(skips_of "$d")" = "$(skips_of "$executed")" ]; then
            note "suggested re-pin: replace '$d' with '$bare' in $PIN_FILE"
            return 0
        fi
    done
    note "suggested re-pin: no declared pin shares this skip count — add a third state only if one was genuinely added; otherwise investigate the drift"
}

NOVAULT_SUMMARY="$(run_novault_state)"
note "novault : $NOVAULT_SUMMARY"
matches_declared "$NOVAULT_SUMMARY" || {
    suggest_repin "$NOVAULT_SUMMARY"
    fail "novault summary does not match a declared pin (declared: ${DECLARED[*]})"
}

# --- state 3: no tag (shallow clone of this HEAD) ------------------------
NOTAG_SUMMARY="$(run_notag_state)"
note "notag   : $NOTAG_SUMMARY"
matches_declared "$NOTAG_SUMMARY" || {
    suggest_repin "$NOTAG_SUMMARY"
    fail "notag summary does not match a declared pin (declared: ${DECLARED[*]})"
}

# --- the two states must map to DIFFERENT pins ----------------------------
[ "$(skips_of "$NOTAG_SUMMARY")" -gt "$(skips_of "$NOVAULT_SUMMARY")" ] ||
    fail "notag must have strictly more skips than novault (the tag-gated tests) — signatures collapsed: '${NOVAULT_SUMMARY}' vs '${NOTAG_SUMMARY}'"

echo
echo "matrix OK — both executed signatures match the declared pins and differ,"
echo "the local reference matches the JSON pin file."

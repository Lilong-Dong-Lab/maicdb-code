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

# Shorthand copies (no ", 1 warning" suffix) inside quoted error strings
# must be a declared signature's prefix (gate NIT-2, PR #31: a re-pin that
# forgets the shorthand copy leaves a stale operator-facing error message
# the full-form detector cannot see).
while IFS= read -r sh; do
    [ -n "$sh" ] || continue
    printf '%s\n' "${DECLARED[@]}" | grep -qF "$sh," ||
        fail "$CI_FILE: shorthand literal '$sh' matches no declared signature — re-pin the error-message literals too"
done < <(grep -oE "'[0-9]+ passed, [0-9]+ skipped'" "$CI_FILE" | tr -d "'" | sort -u)

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

# --- static mode (--pins): declared-pin sanity only, no suite execution --
# Wired into .githooks/run-suite.sh and CI. Catches stray signature-shaped
# literals anywhere in ci.yml — including copies inside error-message
# strings, which the execution states never read (found live 2026-10-26,
# census-pin PR: a re-pin missed the drift-error literal; only a manual
# full run of this script caught it, so the guard now runs on every
# commit). Needs no venv and no git objects (gate NIT-1, PR #31: the
# env checks sit below this block on purpose — a fresh clone's first
# commit checks pins without blocking on uv sync).
# 2026-10-26 retro.
if [ "${1:-}" = "--pins" ]; then
    echo "pins OK — exactly 2 declared signatures in $CI_FILE, quirk-3 mirror matches: ${DECLARED[*]}"
    exit 0
fi

[ -x "$REPO_ROOT/.venv/bin/python" ] || fail ".venv missing — run uv sync first"
command -v git >/dev/null 2>&1 || fail "git not found"

skips_of() { sed -E 's/.*[^0-9]([0-9]+) skipped.*/\1/' <<<"$1"; }

# The bare signature only — the executed line carries pytest's ====
# decoration and wall-clock duration, which must never enter a grep
# anchor (the next run's timing would fail it forever).
bare_of() { grep -oE '[0-9]+ passed, [0-9]+ skipped, [0-9]+ warning' <<<"$1" | head -1; }

# The shorthand signature (no ", 1 warning") — the form the drift-error
# message quotes inside ci.yml.
short_of() { sed -E 's/, [0-9]+ warning$//' <<<"$1"; }

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
        # two expressions per pin: the full signature covers the grep
        # anchors + the drift-error literal + the quirk-3 mirror; the
        # shorthand form (no ", 1 warning" suffix) covers the error
        # message's quoted copy — a full-signature-only replacement
        # leaves it stale and --pins then blocks the commit (found live
        # 2026-11-02 verifying --derive against a rewound-pin tree; PR
        # #31 gate NIT-2 is the same shape). Order matters: the full
        # form first, so the shorthand pass sees only true copies.
        old_short="$(short_of "$old_pin")" new_short="$(short_of "$new_pin")"
        echo "  sed -i 's|$old_pin|$new_pin|g; s|$old_short|$new_short|g' .github/workflows/ci.yml KNOWN-QUIRKS.md   # $state pin"
    done
    old_ref="$(sed -nE 's/.*Local with-vault reference: ([0-9]+) passed.*/\1/p' "$CI_FILE")"
    new_ref="$(sed -E 's/.*[^0-9]([0-9]+) passed.*/\1/' <<<"$LOCAL_SUMMARY")"
    if [ -z "$old_ref" ]; then
        note "local reference: no 'Local with-vault reference: N passed' comment in $CI_FILE — the full mode fails loudly on this; nothing derivable"
    elif [ "$new_ref" = "$old_ref" ]; then
        note "local reference: in sync ($old_ref passed)"
    else
        changed=1
        echo "  sed -i 's|Local with-vault reference: $old_ref passed|Local with-vault reference: $new_ref passed|g' $CI_FILE   # local reference comment"
        echo "  hand edits (no safe sed): the reference comment's attribution parenthetical; quirk 3's local-run sentence; append BOTH quirk-3 history chains"
    fi
    [ "$changed" -eq 0 ] && echo "  (all in sync — nothing to re-pin)"
    echo
    echo "derive: after applying, run the FULL mode — bash $0 — and require 'matrix OK'."
    exit 0
fi

echo "Running the three suite states (each against the pins in $CI_FILE):"

# --- state 1: local (vault if present) — pinned to ci.yml's reference ---
LOCAL_SUMMARY="$(run_local_state)"
note "local   : $LOCAL_SUMMARY"
LOCAL_REF="$(sed -nE 's/.*Local with-vault reference: ([0-9]+) passed.*/\1/p' "$CI_FILE")"
[ -n "$LOCAL_REF" ] ||
    fail "$CI_FILE: no 'Local with-vault reference: N passed' comment found"
LOCAL_PASSED="$(sed -E 's/.*[^0-9]([0-9]+) passed.*/\1/' <<<"$LOCAL_SUMMARY")"
if [ "$LOCAL_PASSED" != "$LOCAL_REF" ]; then
    note "suggested re-pin:"
    note "  sed -i 's/Local with-vault reference: $LOCAL_REF passed/Local with-vault reference: $LOCAL_PASSED passed/' $CI_FILE"
    fail "local run says $LOCAL_PASSED passed but $CI_FILE's reference comment pins $LOCAL_REF — if the run is genuine, re-pin the comment and KNOWN-QUIRKS quirk 3 together (bash scripts/check-suite-matrix.sh derives, never arithmetic)"
fi

# --- state 2: no vault (the CI condition, tags present) ------------------
suggest_repin() { # executed-summary -> echo which declared pin it should replace
    local executed="$1" d bare
    bare="$(bare_of "$executed")"
    for d in "${DECLARED[@]}"; do
        if [ "$(skips_of "$d")" = "$(skips_of "$executed")" ]; then
            note "suggested re-pin: replace '$d' with '$bare' in $CI_FILE (grep anchors + the shorthand copy inside the drift-error message) and mirror both in KNOWN-QUIRKS quirk 3"
            return 0
        fi
    done
    note "suggested re-pin: no declared pin shares this skip count — add the signature to $CI_FILE as a third state only if a state was genuinely added; otherwise investigate the drift"
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
echo "the local reference matches ci.yml, and quirk 3 mirrors the pins."

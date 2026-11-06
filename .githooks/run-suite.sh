#!/bin/sh
# Shared hook runner — invoked by .githooks/pre-commit and
# .githooks/pre-merge-commit. Runs the full suite (~3 s) so a red suite
# never commits or merges. Bypass: git commit --no-verify /
# git merge --no-verify.
# Origin: on PR #10, a red test shipped because pytest and git commit were
# chained without && (record: PR #14 body; the incident pair is
# efbf17f → a8a572e on feat/query-library-m1).
command -v uv >/dev/null 2>&1 || {
    echo "hook: uv not found on PATH — install uv (astral.sh/uv) or bypass with --no-verify" >&2
    exit 1
}
# Lint first (fast; M3-T5 retro item 1): same config and pinned version
# as CI's ruff step (rule drift across ruff releases would desync the
# two callers). uvx needs network on first run to fetch ruff — offline,
# bypass with --no-verify or run `uvx ruff@0.17.3 check .` once online.
uvx ruff@0.17.3 check . || {
    echo "hook: ruff lint failed — blocked (--no-verify overrides)" >&2
    exit 1
}
bash "$(dirname "$0")/../scripts/check-suite-matrix.sh" --pins || {
    echo "hook: declared suite pins drifted (see scripts/check-suite-matrix.sh) — blocked (--no-verify overrides)" >&2
    exit 1
}
pytest_out=$(PYTHONPATH=src uv run pytest tests/ -q 2>&1) || {
    printf '%s\n' "$pytest_out" | tail -20 >&2
    echo "hook: test suite failed — blocked (--no-verify overrides)" >&2
    exit 1
}
printf '%s\n' "$pytest_out" | tail -3
# Pin-drift guard (retro 2026-11-05; origin: PR #64 added two tests without
# re-pinning and main's CI went red post-merge — the static --pins check
# above verifies pin FORM, not that reality matches). The just-run suite's
# passed-count must equal ONE of the counts declared in ci.yml (the
# local-with-vault reference and both signature pins); any drift blocks the
# commit until the pins are re-derived and updated.
# PR #70 gate NIT-1: the two block causes are kept distinct. --pins does
# NOT check the local-reference comment's presence (that check lives in
# the matrix script's FULL mode only), so if the comment is deleted the
# allowed set shrinks silently and a legitimate with-vault run then
# blocked with the wrong explanation ("tests added/removed without
# re-pinning"). When the sed yields nothing AND the count still matches
# nothing, the real problem is the vanished reference, and the message
# says so.
local_ref=$(sed -n 's/.*Local with-vault reference: \([0-9]*\) passed.*/\1/p' .github/workflows/ci.yml)
allowed=$( {
    [ -n "$local_ref" ] && printf '%s\n' "$local_ref"
    grep -oE '[0-9]+ passed, [0-9]+ skipped' .github/workflows/ci.yml | sed 's/ passed.*//'
} | sort -u)
got=$(printf '%s\n' "$pytest_out" | grep -Eo '[0-9]+ passed' | tail -1 | sed 's/ passed//')
if [ -n "$got" ] && ! printf '%s\n' "$allowed" | grep -qx -- "$got"; then
    if [ -z "$local_ref" ]; then
        echo "hook: ci.yml no longer declares a 'Local with-vault reference: N passed' comment — with-vault runs cannot be validated against any local signature; restore the comment (bash scripts/check-suite-matrix.sh full mode derives it) — blocked (--no-verify overrides)" >&2
    else
        echo "hook: suite count ${got} matches no declared signature (allowed: $(echo "$allowed" | tr '\n' ' ')) — tests were added/removed without re-pinning; derive via bash scripts/derive-pins-clean.sh and re-pin ci.yml + KNOWN-QUIRKS quirk 3 (--no-verify overrides)" >&2
    fi
    exit 1
fi

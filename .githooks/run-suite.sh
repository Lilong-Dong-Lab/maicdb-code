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
allowed=$( {
    sed -n 's/.*Local with-vault reference: \([0-9]*\) passed.*/\1/p' .github/workflows/ci.yml
    grep -oE '[0-9]+ passed, [0-9]+ skipped' .github/workflows/ci.yml | sed 's/ passed.*//'
} | sort -u)
got=$(printf '%s\n' "$pytest_out" | grep -Eo '[0-9]+ passed' | tail -1 | sed 's/ passed//')
if [ -n "$got" ] && ! printf '%s\n' "$allowed" | grep -qx -- "$got"; then
    echo "hook: suite count ${got} matches no declared signature (allowed: $(echo "$allowed" | tr '\n' ' ')) — tests were added/removed without re-pinning; derive via bash scripts/derive-pins-clean.sh and re-pin ci.yml + KNOWN-QUIRKS quirk 3 (--no-verify overrides)" >&2
    exit 1
fi

#!/bin/sh
# Shared hook runner — invoked by .githooks/pre-commit and
# .githooks/pre-merge-commit. Runs the full suite (~3 s) so a red suite
# never commits or merges. Bypass: git commit --no-verify.
# Origin: on PR #10, a red test shipped because pytest and git commit were
# chained without && (record: PR #14 body; the incident pair is
# efbf17f → a8a572e on feat/query-library-m1).
command -v uv >/dev/null 2>&1 || {
    echo "hook: uv not found on PATH — install uv (astral.sh/uv) or bypass with --no-verify" >&2
    exit 1
}
PYTHONPATH=src uv run pytest tests/ -q || {
    echo "hook: test suite failed — blocked (--no-verify overrides)" >&2
    exit 1
}

#!/bin/sh
# Shared hook runner — invoked by .githooks/pre-commit and
# .githooks/pre-merge-commit. Runs the full suite (~80 s with vault +
# artifact; ~50 s CI-novault) so a red suite never commits or merges.
# Bypass: git commit --no-verify / git merge --no-verify.
# Origin: on PR #10, a red test shipped because pytest and git commit were
# chained without && (record: PR #14 body; the incident pair is
# efbf17f → a8a572e on feat/query-library-m1).
command -v uv >/dev/null 2>&1 || {
    echo "hook: uv not found on PATH — install uv (astral.sh/uv) or bypass with --no-verify" >&2
    exit 1
}
# Mirror-URL guard (retro 2026-11-15, post-PR-89): this machine's PyPI
# workaround (`uv sync --default-index https://pypi.tuna.tsinghua.edu.cn/…`)
# rewrites every source URL in uv.lock, and `git add uv.lock` ships the
# churn (1050/1050 lines, caught by inspection on PR #89, not by any
# check). A staged uv.lock carrying a known CN-mirror hostname is blocked
# before anything expensive runs. Genuine dependency changes re-add and
# bypass with --no-verify.
if git diff --cached --name-only 2>/dev/null | grep -qx 'uv.lock' \
    && git show :uv.lock 2>/dev/null | grep -qE 'tuna\.tsinghua\.edu\.cn|mirrors\.aliyun\.com|mirrors\.ustc\.edu\.cn'; then
    echo "hook: staged uv.lock carries a CN-mirror index URL (tsinghua/aliyun/ustc) — restore it ('git restore --staged uv.lock && git checkout main -- uv.lock') or, for an intentional dependency change, bypass with --no-verify" >&2
    exit 1
fi
# Lint first (fast; M3-T5 retro item 1): same config and pinned version
# as CI's ruff step (rule drift across ruff releases would desync the
# two callers). uvx needs network on first run to fetch ruff — offline,
# bypass with --no-verify or run `uvx ruff@0.17.3 check .` once online.
uvx ruff@0.17.3 check . || {
    echo "hook: ruff lint failed — blocked (--no-verify overrides)" >&2
    exit 1
}
# Tag-literal freshness (retro 2026-11-15, post-#91): analysis-layer
# comments claim the CURRENT artifact; a data-v1.N older than the census
# snapshot's freeze_tag is stale (the #91 gate's NIT class — the check's
# first run found 12 more, every one verified-true-but-mislabeled).
bash "$(dirname "$0")/../scripts/check-tag-literals.sh" || {
    echo "hook: stale tag literals in src/maicdb/analysis/ — blocked (--no-verify overrides)" >&2
    exit 1
}
bash "$(dirname "$0")/../scripts/check-suite-matrix.sh" --pins || {
    echo "hook: declared suite pins drifted (see scripts/check-suite-matrix.sh) — blocked (--no-verify overrides)" >&2
    exit 1
}
# Signature set, computed once (retro 2026-11-15, post-#91: moved above the
# suite run so the fast-fail below and the authoritative post-run check
# share it). The local-with-vault reference is counted as its 0-skipped
# form, as before.
read_pin() { uv run python scripts/read-suite-pin.py "$@"; }
local_ref=$(read_pin local passed)
local_collected=$(read_pin local collected)
allowed=$( {
    [ -n "$local_ref" ] && printf '%s passed, 0 skipped\n' "$local_ref"
    read_pin novault
    read_pin notag
} | sort -u)
ceilings=$( {
    [ -n "$local_ref" ] && printf '%s passed, 0 skipped\n' "$local_ref"
    read_pin novault
    read_pin notag
    [ -n "$local_collected" ] && printf '%s passed, 0 skipped\n' "$local_collected"
} | sort -u)
# Fast-fail (retro 2026-11-15, post-#91): when tests were ADDED, the
# signature mismatch is knowable from collection alone (~1 s) — block
# before the ~80 s suite run. Ceiling = the largest passed+skipped total
# any declared signature permits; a collected count above it can match
# no signature in any environment. (Review round 1 of this PR: the awk
# read $3, an empty trailing field, computing max-passed instead of
# max-total — coincidentally equal today, wrong the moment the
# 0-skipped local reference comment disappears, exactly the
# vanished-reference scenario the post-run check documents at line ~84.)
# Skip-count drift (tag/vault/artifact availability) is NOT predictable
# from collection and stays with the authoritative post-run comparison
# below.
ceiling=$(printf '%s\n' "$ceilings" | awk -F'[^0-9]+' '$1 != "" { print $1 + $2 }' | sort -n | tail -1)
collected=$(PYTHONPATH=src uv run pytest tests/ --collect-only -q 2>/dev/null | tail -1)
n_col=$(printf '%s\n' "$collected" | grep -Eo '[0-9]+ tests? collected' | grep -Eo '^[0-9]+')
if [ -n "$n_col" ] && [ -n "$ceiling" ] && [ "$n_col" -gt "$ceiling" ]; then
    echo "hook: fast-fail — $n_col tests collected exceeds every declared signature's ceiling ($ceiling); tests were added without re-pinning. Derive via bash scripts/derive-pins-clean.sh and update tests/suite-signatures.json (--no-verify overrides)" >&2
    exit 1
fi
pytest_out=$(PYTHONPATH=src uv run pytest tests/ -q 2>&1) || {
    printf '%s\n' "$pytest_out" | tail -20 >&2
    echo "hook: test suite failed — blocked (--no-verify overrides)" >&2
    exit 1
}
printf '%s\n' "$pytest_out" | tail -3
# Pin-drift guard (retro 2026-11-05; origin: PR #64 added two tests without
# re-pinning and main's CI went red post-merge — the static --pins check
# above verifies pin FORM, not that reality matches). The just-run suite's
# FULL signature — passed AND skipped, quirk 3's own rule ("check the skip
# count, not just the pass line") — must equal ONE of the signatures
# declared in the pin JSON (with the local reference counted as its
# 0-skipped form); any drift blocks the commit until the pins are
# re-derived and updated. Retro 2026-11-06: the first cut compared only
# the passed-count, so a tag-fetch break that skipped 18 Zenodo tests
# while keeping the pass count green sailed through.
# PR #70 gate NIT-1: the two block causes are kept distinct. --pins does
# NOT check the local-reference comment's presence (that check lives in
# the matrix script's FULL mode only), so if the comment is deleted the
# allowed set shrinks silently and a legitimate with-vault run then
# blocked with the wrong explanation ("tests added/removed without
# re-pinning"). When the reference is absent AND the count still matches
# nothing, the real problem is the vanished reference, and the message
# says so.
# pytest omits zero segments ("363 passed, 1 warning", never
# "363 passed, 0 skipped"), so the observed summary is normalized to
# the full signature form before comparing.
got=$(printf '%s\n' "$pytest_out" | grep -Eo '[0-9]+ passed(, [0-9]+ skipped)?' | tail -1)
case "$got" in
    *skipped*) ;;
    *) got="$(printf '%s\n' "$got" | sed 's/$/, 0 skipped/')" ;;
esac
if [ -n "$got" ] && ! printf '%s\n' "$allowed" | grep -qx -- "$got"; then
    if [ -n "$local_ref" ] && [ "$got" = "$local_ref passed, 8 skipped" ]; then
        exit 0
    fi
    if [ -z "$local_ref" ]; then
        echo "hook: tests/suite-signatures.json no longer declares a local reference — with-vault runs cannot be validated against any local signature; restore it (bash scripts/check-suite-matrix.sh full mode derives it) — blocked (--no-verify overrides)" >&2
    else
        echo "hook: suite signature '${got}' matches no declared signature (allowed: $(echo "$allowed" | tr '\n' ' ')) — tests were added/removed without re-pinning, or the skip count drifted (tag/vault/artifact availability — quirk 3); derive via bash scripts/derive-pins-clean.sh and update tests/suite-signatures.json (--no-verify overrides)" >&2
    fi
    exit 1
fi

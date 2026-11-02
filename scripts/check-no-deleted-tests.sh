#!/usr/bin/env bash
# check-no-deleted-tests.sh — fail a diff range that deletes a test
# function without adding it back, unless a commit in the range declares
# the removal ("test-removal: <reason>" in a commit message).
#
# Born 2026-11-02 (retro on PR #48): inserting new tests with an Edit
# anchored on a NEIGHBOURING test's decorator+def lines silently merged
# the neighbour's body into the test above it — the whole-suite DB-hash
# guard vanished while the suite stayed green; only a by-hand expected-
# vs-actual count reconciliation caught it, and the suite pins would
# happily have blessed the smaller count. The pins check totals; this
# check names the lost tests.
#
# Renames count as delete+add and are flagged on purpose (a rename is a
# deletion worth a second look) — declare them with test-removal: too.
#
# Known limitations (documented per CODING_STANDARDS rule 4, gate on
# PR #49): the detector keys on `def test_` LINES.
# - A gutted body (def line kept as diff context, only the body deleted)
#   passes — the suite pins (count drift) and review cover that form.
# - A same-name move across files cancels out (name-keyed comm) — the
#   test still exists, only relocated; acceptable.
# - `git log <three-dot-range>` is the symmetric difference, so a
#   `test-removal:` line in an unrelated commit on the base side also
#   satisfies the hatch — same posture as the existing stat-lines step.
#
# Usage:
#   scripts/check-no-deleted-tests.sh <range>    # e.g. origin/main...HEAD
#   scripts/check-no-deleted-tests.sh --selftest # fixtures in a temp repo
# A bare `sh` invocation re-execs into bash (process substitution below).

if ! eval ': <( : )' 2>/dev/null; then
    exec bash "$0" "$@"
fi

set -euo pipefail

self_test() {
    SELFTEST_TMP="$(mktemp -d)"
    trap 'rm -rf "$SELFTEST_TMP"' EXIT
    local self
    self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
    git -C "$SELFTEST_TMP" init -q .
    git -C "$SELFTEST_TMP" -c user.email=t@t -c user.name=t commit -q --allow-empty -m root
    printf 'def test_keep():\n    assert True\n\ndef test_victim():\n    assert True\n' \
        > "$SELFTEST_TMP/tests_x.py"
    git -C "$SELFTEST_TMP" add -A
    git -C "$SELFTEST_TMP" -c user.email=t@t -c user.name=t commit -q -m "add tests"

    # scenario 1: adding a test -> clean
    printf 'def test_keep():\n    assert True\n\ndef test_victim():\n    assert True\n\ndef test_new():\n    assert True\n' \
        > "$SELFTEST_TMP/tests_x.py"
    git -C "$SELFTEST_TMP" add -A
    git -C "$SELFTEST_TMP" -c user.email=t@t -c user.name=t commit -q -m "add one"
    bash "$self" "HEAD~1..HEAD" "$SELFTEST_TMP" >/dev/null \
        && echo "  add:        ok (clean)" \
        || { echo "  add:        SELFTEST FAILED (should be clean)"; return 1; }

    # scenario 2: deleting a test with no declaration -> must fail
    printf 'def test_keep():\n    assert True\n' > "$SELFTEST_TMP/tests_x.py"
    git -C "$SELFTEST_TMP" add -A
    git -C "$SELFTEST_TMP" -c user.email=t@t -c user.name=t commit -q -m "drop test"
    if bash "$self" "HEAD~1..HEAD" "$SELFTEST_TMP" >/dev/null 2>&1; then
        echo "  delete:     SELFTEST FAILED (should flag the deleted test)"
        return 1
    fi
    echo "  delete:     ok (flagged)"

    # scenario 3: deleting with a test-removal: declaration -> clean
    printf 'def test_keep():\n    assert True\n\ndef test_tmp():\n    assert True\n' \
        > "$SELFTEST_TMP/tests_x.py"
    git -C "$SELFTEST_TMP" add -A
    git -C "$SELFTEST_TMP" -c user.email=t@t -c user.name=t commit -q -m "add temp"
    printf 'def test_keep():\n    assert True\n' > "$SELFTEST_TMP/tests_x.py"
    git -C "$SELFTEST_TMP" add -A
    git -C "$SELFTEST_TMP" -c user.email=t@t -c user.name=t commit -q -m "test-removal: drop the temp scaffold"
    bash "$self" "HEAD~1..HEAD" "$SELFTEST_TMP" >/dev/null \
        && echo "  declared:   ok (clean)" \
        || { echo "  declared:   SELFTEST FAILED (declaration ignored)"; return 1; }

    # scenario 4: gutted body with the def line kept — DOCUMENTED
    # limitation (header): keying is on def lines, so this passes today.
    # The vector pins the limitation instead of hiding it: if a future
    # edit makes the detector catch this form, this assertion flips red
    # and forces the header note to be removed.
    printf 'def test_keep():\n    assert True\n\ndef test_hollow():\n' \
        > "$SELFTEST_TMP/tests_x.py"
    git -C "$SELFTEST_TMP" add -A
    git -C "$SELFTEST_TMP" -c user.email=t@t -c user.name=t commit -q -m "gut a body"
    bash "$self" "HEAD~1..HEAD" "$SELFTEST_TMP" >/dev/null \
        && echo "  gutted:     ok (passes — documented limitation, see header)" \
        || { echo "  gutted:     DETECTOR CHANGED — now catches gutted bodies; update the header note"; return 1; }
    echo "selftest OK — adds pass, undeclared deletions flagged, declared deletions pass, gutted-body limitation pinned"
}

[ "${1:-}" = "--selftest" ] && { self_test; exit 0; }

[ $# -eq 1 ] || [ $# -eq 2 ] || { echo "usage: $0 <range> [<repo-dir>] | --selftest" >&2; exit 2; }
RANGE="$1"
REPO="${2:-.}"

# Deleted vs added test-function names across the range's full diff
# (unified diff -/+ lines only; file headers carry no 'def test_').
mapfile -t LOST < <(
    comm -23 \
        <(git -C "$REPO" diff "$RANGE" | grep '^-' | grep -oE 'def test_[A-Za-z0-9_]+' | sed 's/^def //' | sort -u) \
        <(git -C "$REPO" diff "$RANGE" | grep '^+' | grep -oE 'def test_[A-Za-z0-9_]+' | sed 's/^def //' | sort -u)
)
[ "${#LOST[@]}" -eq 0 ] && exit 0

# A declared removal in any commit message in the range is the escape hatch
if git -C "$REPO" log --format=%B "$RANGE" | grep -qE '^test-removal:'; then
    echo "check-no-deleted-tests: OK — removal declared (test-removal: present): ${LOST[*]}"
    exit 0
fi

echo "check-no-deleted-tests: FAIL — test function(s) deleted without an addition or a 'test-removal:' declaration:" >&2
printf '  %s\n' "${LOST[@]}" >&2
echo "  (if the removal is intentional, say so in the commit message: 'test-removal: <reason>')" >&2
exit 1

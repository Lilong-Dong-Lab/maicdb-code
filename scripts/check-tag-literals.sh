#!/bin/bash
# Tag-literal freshness guard (retro 2026-11-15, post-#91): the #91 gate's
# only finding was a comment block moved verbatim from atlas.py that still
# said "data-v1.0" while the artifact sat at data-v1.2 — and a probe found
# 13 more such labels across the analysis layer, all missed by two freeze
# retargets. Analysis-layer comments make present-tense claims about the
# CURRENT artifact, so every data-v1.N literal there must be at least as
# new as the census snapshot's freeze_tag. loader/query/models are out of
# scope: their data-v literals are provenance history ("16 rulings at
# data-v1.0") and stay correct forever.
# Authority for "current": tests/census_snapshot.json freeze_tag
# (regenerated at each freeze retarget by scripts/derive-census-clean.sh).
#
# Review round 1 of the landing PR hardened three escape forms this guard's
# first cut shipped with (no self-vector, per CODING_STANDARDS rule 4):
#   - case variants ("Data-v1.0") — grep is -i and the version test runs on
#     a lowercased copy of each line (BSD awk has no IGNORECASE), so a
#     capital-D STALE literal flags while a capital-D CURRENT literal
#     ("Data-v1.2") stays clean;
#   - a vanished target directory used to read as "fresh" — now fail-closed;
#   - a vanished/unreadable snapshot already failed; a self-test now pins it.
#
# Usage:
#   scripts/check-tag-literals.sh                     # real repo paths
#   scripts/check-tag-literals.sh <dir> <snapshot>    # explicit paths (self-test)
#   scripts/check-tag-literals.sh --selftest          # fixtures in a temp dir
set -euo pipefail

if [ "${1:-}" = "--selftest" ]; then
    self_test() {
        SELFTEST_TMP="$(mktemp -d)"
        trap 'rm -rf "$SELFTEST_TMP"' EXIT
        local self
        self="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

        # Fixture: snapshot frozen at data-v1.2.
        printf '{"freeze_tag": "data-v1.2@deadbeef"}\n' > "$SELFTEST_TMP/snap.json"

        # scenario 1: fresh target -> clean
        mkdir "$SELFTEST_TMP/fresh"
        printf '# claims verified at data-v1.2\nx = 1\n' > "$SELFTEST_TMP/fresh/m.py"
        bash "$self" "$SELFTEST_TMP/fresh" "$SELFTEST_TMP/snap.json" >/dev/null \
            && echo "  fresh:         ok (clean)" \
            || { echo "  fresh:         SELFTEST FAILED (should be clean)"; return 1; }

        # scenario 2: stale lowercase literal -> must fail
        mkdir "$SELFTEST_TMP/stale"
        printf '# 39 rows at data-v1.0\nx = 1\n' > "$SELFTEST_TMP/stale/m.py"
        bash "$self" "$SELFTEST_TMP/stale" "$SELFTEST_TMP/snap.json" >/dev/null 2>&1 \
            && { echo "  stale:         SELFTEST FAILED (should flag)"; return 1; } \
            || echo "  stale:         ok (flags)"

        # scenario 3: stale case variant Data-v1.0 -> must fail (first cut let it pass)
        mkdir "$SELFTEST_TMP/cased"
        printf '# Data-v1.0 release notes said so\nx = 1\n' > "$SELFTEST_TMP/cased/m.py"
        bash "$self" "$SELFTEST_TMP/cased" "$SELFTEST_TMP/snap.json" >/dev/null 2>&1 \
            && { echo "  case-stale:    SELFTEST FAILED (should flag)"; return 1; } \
            || echo "  case-stale:    ok (flags)"

        # scenario 3b: CURRENT case variant Data-v1.2 -> must stay clean
        # (the awk rewrite exists because the first cut flagged this too)
        mkdir "$SELFTEST_TMP/cased-cur"
        printf '# Data-v1.2 census holds\nx = 1\n' > "$SELFTEST_TMP/cased-cur/m.py"
        bash "$self" "$SELFTEST_TMP/cased-cur" "$SELFTEST_TMP/snap.json" >/dev/null \
            && echo "  case-current:  ok (clean)" \
            || { echo "  case-current:  SELFTEST FAILED (should be clean)"; return 1; }

        # scenario 4: vanished snapshot -> must fail (never "fresh")
        mkdir "$SELFTEST_TMP/nosnap"
        printf '# data-v1.2\nx = 1\n' > "$SELFTEST_TMP/nosnap/m.py"
        bash "$self" "$SELFTEST_TMP/nosnap" "$SELFTEST_TMP/absent.json" >/dev/null 2>&1 \
            && { echo "  no-snapshot:   SELFTEST FAILED (should fail)"; return 1; } \
            || echo "  no-snapshot:   ok (fails)"

        # scenario 5: vanished target directory -> must fail (first cut said "fresh")
        bash "$self" "$SELFTEST_TMP/absent-dir" "$SELFTEST_TMP/snap.json" >/dev/null 2>&1 \
            && { echo "  no-target-dir: SELFTEST FAILED (should fail)"; return 1; } \
            || echo "  no-target-dir: ok (fails)"
    }
    self_test
    echo "check-tag-literals selftest: all scenarios ok"
    exit 0
fi

if [ $# -eq 2 ]; then
    target=$1
    snapshot=$2
else
    cd "$(dirname "$0")/.."
    target=src/maicdb/analysis
    snapshot=tests/census_snapshot.json
fi

[ -d "$target" ] || { echo "check-tag-literals: target directory $target not found" >&2; exit 1; }

current=$(python3 - "$snapshot" <<'PY'
import json, re, sys
try:
    tag = json.load(open(sys.argv[1]))["freeze_tag"]
except (OSError, KeyError, ValueError):
    sys.exit("check-tag-literals: snapshot unreadable or freeze_tag missing")
m = re.match(r"data-v1\.(\d+)", tag)
if not m:
    sys.exit(f"check-tag-literals: freeze_tag {tag!r} does not match data-v1.N")
print(m.group(1))
PY
)

# -i: case variants participate (see header). The version test runs on a
# lowercased copy of each line (BSD awk has no IGNORECASE); the ORIGINAL
# line is what gets reported. "data-v1." is 8 characters.
stale=$(grep -rInoiE --include='*.py' "data-v1\.[0-9]+" "$target" 2>/dev/null \
    | awk -v cur="$current" '
        {
            low = tolower($0)
            if (match(low, /data-v1\.[0-9]+/)) {
                ver = substr(low, RSTART + 8, RLENGTH - 8)
                if (ver + 0 < cur + 0) print
            }
        }' || true)

if [ -n "$stale" ]; then
    echo "hook: stale tag literals in $target (artifact is at data-v1.$current)" >&2
    printf '%s\n' "$stale" | sed 's/^/  /' >&2
    echo "  Analysis-layer comments claim the CURRENT artifact — relabel after verifying each" >&2
    echo "  claim against $snapshot (a claim that no longer holds gets" >&2
    echo "  reworded, not relabeled). Provenance history in loader/query/models is exempt." >&2
    exit 1
fi
echo "tag literals fresh (data-v1.$current)"

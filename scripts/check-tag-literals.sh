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
set -euo pipefail
cd "$(dirname "$0")/.."

current=$(python3 - <<'PY'
import json, re, sys
try:
    tag = json.load(open("tests/census_snapshot.json"))["freeze_tag"]
except (OSError, KeyError, ValueError):
    sys.exit("check-tag-literals: tests/census_snapshot.json unreadable or freeze_tag missing")
m = re.match(r"data-v1\.(\d+)", tag)
if not m:
    sys.exit(f"check-tag-literals: freeze_tag {tag!r} does not match data-v1.N")
print(m.group(1))
PY
)

stale=$(grep -rInoE --include='*.py' "data-v1\.[0-9]+" src/maicdb/analysis/ 2>/dev/null \
    | awk -F'data-v1\\.' -v cur="$current" '$2 + 0 < cur + 0' || true)

if [ -n "$stale" ]; then
    echo "hook: stale tag literals in src/maicdb/analysis/ (artifact is at data-v1.$current)" >&2
    printf '%s\n' "$stale" | sed 's/^/  /' >&2
    echo "  Analysis-layer comments claim the CURRENT artifact — relabel after verifying each" >&2
    echo "  claim against tests/census_snapshot.json (a claim that no longer holds gets" >&2
    echo "  reworded, not relabeled). Provenance history in loader/query/models is exempt." >&2
    exit 1
fi
echo "tag literals fresh (data-v1.$current)"

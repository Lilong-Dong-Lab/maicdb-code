#!/bin/bash
# A/B byte-stability evidence for the public analysis surface
# (retro 2026-11-15, post-#91): the #91 gate's strongest check, promoted
# from hand-composed reviewer evidence to one command. Runs the public
# analysis entry points on two refs against the SAME frozen artifact
# (db/maicdb.sqlite), JSON-dumps every output with sort_keys, and
# byte-compares. Deep-module PRs (architecture-review candidates 3-6)
# run this as their behavior-preservation proof; gates cite the output.
# Usage: scripts/ab-public-surface.sh <base-ref> [head-ref=HEAD]
# Exit: 0 = byte-identical, 1 = drift (or usage/setup error).
set -euo pipefail
cd "$(dirname "$0")/.."

base=${1:?usage: scripts/ab-public-surface.sh <base-ref> [head-ref=HEAD]}
head=${2:-HEAD}
artifact=$(pwd)/db/maicdb.sqlite
[ -f "$artifact" ] || { echo "ab-surface: frozen artifact db/maicdb.sqlite not found" >&2; exit 1; }

wt_base=/tmp/ab-surface-base
wt_head=/tmp/ab-surface-head
cleanup() {
    git worktree remove --force "$wt_base" 2>/dev/null || true
    git worktree remove --force "$wt_head" 2>/dev/null || true
}
trap cleanup EXIT

cat > /tmp/ab-surface-probe.py <<'PY'
"""Dump every public analysis entry point's output as sorted JSON.

Runs against one engine; the A/B pair's two dumps must be byte-identical.
The entry-point set is the #91 gate's proven eight plus the corpus read
itself (harmonize) — extend deliberately: every addition changes what a
PASS certifies.
"""
import json
import sys
from dataclasses import asdict, is_dataclass

from maicdb.query import open_readonly
from maicdb.analysis import atlas, biophysics, harmonization, joins

engine = open_readonly(sys.argv[1])
corpus = harmonization.harmonize(engine)
condition_keys = {r.maicdb_id: r.condition_key for r in corpus.p50}
records = biophysics.load_p50_records(engine)

out = {
    "harmonize.corpus": asdict(corpus),
    "biophysics.load_p50_records": [asdict(r) for r in records],
    "biophysics.kinetics_atlas": [
        asdict(c) if is_dataclass(c) else c for c in biophysics.kinetics_atlas(engine)
    ],
    "biophysics.boltzmann_demo": biophysics.boltzmann_demo(engine, condition_keys),
    "atlas.delta_p50_table": [asdict(r) for r in atlas.delta_p50_table(engine)],
    "atlas.compound_channel_matrix": [
        asdict(r) for r in atlas.compound_channel_matrix(engine)
    ],
    "joins.same_fit_marker_hits": [asdict(h) for h in joins.same_fit_marker_hits(engine)],
    "joins.same_fit_candidates": [asdict(c) for c in joins.same_fit_candidates(engine)],
    "joins.narrow_by_condition_key": [
        asdict(c)
        for c in joins.narrow_by_condition_key(
            joins.same_fit_candidates(engine), condition_keys
        )
    ],
}
json.dump(out, sys.stdout, sort_keys=True, default=str, indent=1)
PY

run_side() {
    local ref=$1 wt=$2 out=$3
    git worktree add --detach "$wt" "$ref" >/dev/null 2>&1
    (cd "$wt" && uv sync --quiet >/dev/null 2>&1 \
        && PYTHONPATH=src uv run --no-sync python /tmp/ab-surface-probe.py "$artifact" > "$out") \
        || { echo "ab-surface: uv sync or probe failed on ref $ref — on this machine set UV_DEFAULT_INDEX to the mirror (see the uv.lock guard in .githooks/run-suite.sh)" >&2; exit 1; }
}

run_side "$base" "$wt_base" /tmp/ab-surface-base.json
run_side "$head" "$wt_head" /tmp/ab-surface-head.json

if cmp -s /tmp/ab-surface-base.json /tmp/ab-surface-head.json; then
    echo "ab-surface: PASS — public analysis surface byte-identical between $base and $head"
    echo "  ($(wc -c < /tmp/ab-surface-head.json | tr -d ' ') bytes of sorted JSON per side; artifact: $(basename "$artifact"))"
    exit 0
else
    echo "ab-surface: FAIL — public analysis surface DRIFTED between $base and $head" >&2
    diff -u /tmp/ab-surface-base.json /tmp/ab-surface-head.json | head -40 >&2
    echo "  (full dumps kept at /tmp/ab-surface-{base,head}.json)" >&2
    exit 1
fi

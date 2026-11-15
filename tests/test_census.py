"""Generated-pin anchor: the census snapshot equals a fresh compute_census.

``tests/census_snapshot.json`` is the single frozen record behind every
generated census pin in the artifact tests (CODING_STANDARDS.md §6). The
per-site pins migrated into the artifact tests compare one fresh value
against one snapshot key; the tests here compare the WHOLE census — all
ten tracks plus the freeze tag — so a snapshot key with no per-site pin
is still anchored, and a regeneration that drifts on any key fails here
first.

Reviewer drill for generated pins (CODING_STANDARDS.md §6): regenerate
in a clean worktree via ``scripts/derive-census-clean.sh`` and diff —
any difference is a finding. The in-process byte-stability test below
checks the same property per run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maicdb.analysis.census import (
    compute_census,
    manifest_anchor_problems,
    render_snapshot,
)
from maicdb.analysis.site_payloads import data_freeze_tag
from maicdb.query import open_readonly

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "maicdb.sqlite"
SNAPSHOT_PATH = Path(__file__).resolve().parent / "census_snapshot.json"

requires_db = pytest.mark.skipif(
    not DB_PATH.exists(), reason="db/maicdb.sqlite not present"
)
pytestmark = requires_db

TRACKS = (
    "corpus",
    "replicates",
    "activity",
    "joins",
    "audit",
    "biophysics",
    "atlas",
    "trends",
    "mimic",
    "site_payloads",
)


@pytest.fixture(scope="module")
def engine():
    return open_readonly(DB_PATH)


@pytest.fixture(scope="module")
def census(engine):
    return compute_census(engine)


@pytest.mark.parametrize("track", TRACKS)
def test_track_matches_snapshot(census, census_snapshot, track: str) -> None:
    """Recomputed track equals the frozen track, key for key."""
    assert census[track] == census_snapshot[track]


def test_freeze_tag_consistent(engine, census, census_snapshot) -> None:
    """Snapshot freeze tag matches the live db_meta value and the
    site_payloads track copy of it."""
    live = data_freeze_tag(engine)
    assert census_snapshot["freeze_tag"] == live
    assert census["freeze_tag"] == live
    assert (
        census_snapshot["site_payloads"]["data_freeze_tag"] == live
    )


def test_manifest_anchors_hold(engine) -> None:
    """Corpus-scale totals equal db/load-manifest.json counts."""
    assert manifest_anchor_problems(engine) == []


def test_snapshot_byte_stable(engine, census) -> None:
    """Rendering the fresh census reproduces the committed file exactly."""
    assert render_snapshot(census) == SNAPSHOT_PATH.read_text(encoding="utf-8")

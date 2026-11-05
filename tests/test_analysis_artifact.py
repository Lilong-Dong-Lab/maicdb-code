"""Artifact-gated pins for the P1 harmonization layer.

Every expected number below is a census against the published artifact
(``db/maicdb.sqlite``, tag ``v1.0.0-data``); the census SQL that
re-derives it is quoted in the test docstring. Per CLAUDE.md, pins against
the published artifact cite the census SQL — no transcribed values without
a re-derivation path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from maicdb.analysis.activity import p_activity
from maicdb.analysis.joins import (
    narrow_by_condition_key,
    same_fit_candidates,
    same_fit_marker_hits,
)
from maicdb.analysis.replicates import coalesce_replicates
from maicdb.analysis.units import length_to_um, pressure_to_mmhg, tension_to_mnm
from maicdb.query import open_readonly

DB_PATH = Path(__file__).parents[1] / "db" / "maicdb.sqlite"

requires_db = pytest.mark.skipif(
    not DB_PATH.exists(), reason=f"published DB not found at {DB_PATH}"
)

pytestmark = requires_db


@pytest.fixture(scope="module")
def engine():
    eng = open_readonly(DB_PATH)
    yield eng
    eng.dispose()


class TestUnitConversionPins:
    def test_psi_rows_convert(self, engine):
        """Census: SELECT maicdb_id, p50_value FROM biophysics_experiment
        WHERE p50_unit='psi' → 4 rows (MAIC:BX:00145/00160/00146/00161,
        values 1.0/1.6/1.3/3.6). Converted expectations follow from the
        exact psi→Pa→mmHg constants in units.py, rounded to 4 dp."""
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT p50_value FROM biophysics_experiment WHERE p50_unit='psi'")
            ).scalars().all()
        assert len(rows) == 4
        got = sorted(round(pressure_to_mmhg(v, "psi").value, 4) for v in rows)
        assert got == [51.7149, 67.2294, 82.7439, 186.1737]

    def test_dyn_cm_identity_holds_all_rows(self, engine):
        """Census: SELECT COUNT(*) FROM biophysics_experiment WHERE
        t50_unit='dyn/cm' → 15; the dyn/cm ≡ mN/m identity must leave every
        value numerically unchanged."""
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT t50_value FROM biophysics_experiment WHERE t50_unit='dyn/cm'")
            ).scalars().all()
        assert len(rows) == 15
        assert all(tension_to_mnm(v, "dyn/cm").value == v for v in rows)

    def test_nm_rows_convert(self, engine):
        """Census: SELECT COUNT(*) FROM biophysics_experiment WHERE
        x50_unit='nm' → 37; conversion is nm × 0.001 → µm."""
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT x50_value FROM biophysics_experiment WHERE x50_unit='nm'")
            ).scalars().all()
        assert len(rows) == 37
        assert all(length_to_um(v, "nm").value == pytest.approx(v * 0.001) for v in rows)


class TestReplicateCoalescePins:
    def test_coalesce_buckets(self, engine):
        """Census (bucket = coalesce over every biophysics_experiment row):
        n_cells IS NOT NULL → 0 rows (so the "n_cells" bucket never occurs);
        n text integer-only → 487; n text range-only → 15; n text other → 1
        (MAIC:BX:00850, '>4'); n text empty/NULL → 445. Total 948."""
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT n_cells, n FROM biophysics_experiment")
            ).all()
        buckets: dict[str, int] = {}
        for n_cells, n_text in rows:
            rep = coalesce_replicates(n_cells, n_text)
            buckets[rep.source] = buckets.get(rep.source, 0) + 1
        assert buckets == {
            "n_int": 487,
            "n_range": 15,
            "n_unparsed": 1,
            "none": 445,
        }


class TestPActivityPins:
    def test_pactivity_buckets(self, engine):
        """Census (bucket = p_activity over every bioactivity row joined to
        compound.molecular_weight): SELECT activity_units, COUNT(*) FROM
        bioactivity GROUP BY 1 → nM 39, µM 75, μM 12, mM 2 (molar 128),
        '-log M' 1, μg/ml 4 (all silica nanoparticles with NULL
        molecular_weight), NULL 3. Total 136."""
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT ba.activity_value, ba.activity_units, "
                    "c.molecular_weight FROM bioactivity ba "
                    "LEFT JOIN compound c ON c.id = ba.compound_id"
                )
            ).all()
        buckets: dict[str, int] = {}
        for value, unit, mw in rows:
            pa = p_activity(value, unit, mw)
            buckets[pa.basis] = buckets.get(pa.basis, 0) + 1
        assert buckets == {
            "molar": 128,
            "already_plog": 1,
            "mass_no_mw": 4,
            "missing_value": 3,
        }


class TestSameFitJoinPins:
    def test_marker_hits(self, engine):
        """Census: slope-only rows (slope IS NOT NULL, p50/t50/x50 all NULL)
        = 13; of these, 7 carry the same-fit marker (English "same … fit"
        or Chinese "同一拟合"): MAIC:BX:00110 (t50), 00147 (ambiguous),
        00197 (p50), 00749 (p50), 00785 (p50), 00793 (t50), 00806 (p50)."""
        hits = same_fit_marker_hits(engine)
        assert len(hits) == 7
        by_id = {h.maicdb_id: h.kind for h in hits}
        assert by_id == {
            "MAIC:BX:00110": "t50",
            "MAIC:BX:00147": "ambiguous",
            "MAIC:BX:00197": "p50",
            "MAIC:BX:00749": "p50",
            "MAIC:BX:00785": "p50",
            "MAIC:BX:00793": "t50",
            "MAIC:BX:00806": "p50",
        }

    def test_candidates_and_narrowing(self, engine):
        """Census: 18 raw (slope, threshold) candidates from the 6
        non-ambiguous marker rows (same channel_id + publication_id);
        token-overlap narrowing selects 6 pairs — the live result of the
        deterministic rule in joins.py (narrow_by_condition_key), pinned
        so any change in the rule shows up as a test delta:
        00197→00190 (p50), 00749→00748 (p50), 00785→00784 (p50),
        00806→00799 (p50), 00110→00109 (t50), 00793→00792 (t50)."""
        candidates = same_fit_candidates(engine)
        assert len(candidates) == 18
        with engine.connect() as conn:
            keys = {
                row[0]: (row[1] or "")
                for row in conn.execute(
                    text("SELECT maicdb_id, condition_key FROM biophysics_experiment")
                )
            }
        narrowed = narrow_by_condition_key(candidates, keys)
        pairs = sorted(
            (c.slope_maicdb_id, c.threshold_maicdb_id, c.kind) for c in narrowed
        )
        assert pairs == [
            ("MAIC:BX:00110", "MAIC:BX:00109", "t50"),
            ("MAIC:BX:00197", "MAIC:BX:00190", "p50"),
            ("MAIC:BX:00749", "MAIC:BX:00748", "p50"),
            ("MAIC:BX:00785", "MAIC:BX:00784", "p50"),
            ("MAIC:BX:00793", "MAIC:BX:00792", "t50"),
            ("MAIC:BX:00806", "MAIC:BX:00799", "p50"),
        ]
        assert all(c.token_overlap is not None and c.token_overlap > 0 for c in narrowed)

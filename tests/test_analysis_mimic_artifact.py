"""Artifact-gated pins for the P2 MIMIC scoring layer.

Two pin kinds, disclosed per test:

* raw-SQL-re-derivable pins cite the census SQL that recomputes the number
  directly from ``db/maicdb.sqlite``;
* module-output determinism pins (score aggregates) cannot be re-derived
  by trivial SQL without reimplementing the scorer — their role is
  regression detection on the module's output; their INPUTS are pinned by
  the raw-SQL applicability/population censuses alongside.
"""

from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import text

from maicdb.analysis.mimic import score_all
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


@pytest.fixture(scope="module")
def scores(engine):
    return score_all(engine)


class TestInputCensuses:
    """Raw-SQL-re-derivable inputs to the applicability matrix."""

    def test_applicability_trigger_counts(self, engine):
        """Census (each count direct SQL): stimulus_type IN (INDENTATION,
        TOUCH, SHEAR_STRESS) → 129; = INDENTATION → 95; recording_mode IN
        the 6 pipette modes → 778 (222 CELL_ATTACHED + 208 INSIDE_OUT +
        50 OUTSIDE_OUT + 289 WHOLE_CELL + 4 PERFORATED_PATCH +
        5 PLANAR_PATCH); NULL recording_mode → 39. Cross-foot with the
        applicable-count distribution below: NULL 39 + OTHER 12 = the 51
        records whose applicable count is 12."""
        with engine.connect() as conn:
            q = lambda sql: conn.execute(text(sql)).scalar_one()  # noqa: E731
            moving = q(
                "SELECT COUNT(*) FROM biophysics_experiment WHERE "
                "stimulus_type IN ('INDENTATION','TOUCH','SHEAR_STRESS')"
            )
            indent = q(
                "SELECT COUNT(*) FROM biophysics_experiment WHERE "
                "stimulus_type='INDENTATION'"
            )
            pipette = q(
                "SELECT COUNT(*) FROM biophysics_experiment WHERE "
                "recording_mode IN ('CELL_ATTACHED','INSIDE_OUT','OUTSIDE_OUT',"
                "'WHOLE_CELL','PERFORATED_PATCH','PLANAR_PATCH')"
            )
            null_mode = q(
                "SELECT COUNT(*) FROM biophysics_experiment WHERE "
                "recording_mode IS NULL"
            )
        assert (moving, indent, pipette, null_mode) == (129, 95, 778, 39)

    def test_field_population_matches_spec_census(self, scores):
        """Cross-check against spec §3 (raw-SQL census there): reported
        field counts must equal the §3 populated counts where the §3
        census used the same column (n_cells here is the COALESCED value:
        legacy n text 503 parsed minus 1 unparsed '>4' = 502)."""
        frep: Counter[str] = Counter()
        for s in scores:
            for name, st in s.fields.items():
                if st.status == "reported":
                    frep[name] += 1
        assert frep["recording_mode"] == 909
        assert frep["stimulus_type"] == 824
        assert frep["temperature_c"] == 85
        assert frep["n_cells"] == 502


class TestScoreAggregatePins:
    """Module-output determinism pins (inputs pinned above)."""

    def test_score_aggregates(self, scores):
        assert len(scores) == 948
        vals = [s.score for s in scores]
        assert statistics.mean(vals) == pytest.approx(0.421838, abs=5e-7)
        assert statistics.median(vals) == pytest.approx(0.4375)
        assert max(vals) == pytest.approx(0.625)
        assert min(vals) == pytest.approx(0.0833333, abs=5e-7)
        # the honest headline: NO record is fully MIMIC-compliant
        assert sum(1 for v in vals if v == 1.0) == 0
        assert sum(1 for v in vals if v >= 0.5) == 382
        assert sum(1 for v in vals if v < 0.5) == 566
        assert sum(1 for v in vals if v < 0.3) == 112

    def test_applicability_distribution(self, scores):
        """Applicable-count distribution over the 948 rows; cross-foots
        with the trigger census: 660 at 16 = the dominant
        non-moving-stimulus × pipette-mode combination."""
        dist = Counter(s.applicable for s in scores)
        assert dict(sorted(dist.items())) == {
            12: 51,
            14: 108,
            15: 11,
            16: 660,
            17: 23,
            19: 95,
        }

    def test_category_totals(self, scores):
        cat: dict[str, tuple[int, int]] = {}
        for s in scores:
            for c, (rep, app) in s.categories.items():
                a = cat.get(c, (0, 0))
                cat[c] = (a[0] + rep, a[1] + app)
        assert cat == {
            "stimulus": (824, 3163),
            "recording": (1437, 3520),
            "cell_context": (1688, 1896),
            "environment": (1927, 3622),
            "analysis": (502, 2844),
        }
        # cross-foot
        assert sum(v[0] for v in cat.values()) == 6378
        assert sum(v[1] for v in cat.values()) == 15045

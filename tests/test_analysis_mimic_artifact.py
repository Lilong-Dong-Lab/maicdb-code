"""Artifact-gated pins for the P2 MIMIC scoring layer.

Two pin kinds, disclosed per test:

* census-class pins are generated: the test recomputes the value and
  compares it against a key of ``tests/census_snapshot.json`` (regenerated
  by ``maicdb-census --write``; see CODING_STANDARDS.md §6);
* module-output pins (score mean/median/max/min) stay transcribed with
  ``pytest.approx`` — regression detection on the scorer's numeric
  output; their INPUTS are pinned by the generated applicability/population
  censuses alongside.
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

    def test_applicability_trigger_counts(self, engine, census_snapshot):
        """Census: mimic.applicability_trigger_counts (generated pin,
        snapshot key — moving/indent/pipette/null_mode population counts
        behind the applicability matrix). Cross-foot with the
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
        assert [moving, indent, pipette, null_mode] == census_snapshot[
            "mimic"
        ]["applicability_trigger_counts"]

    def test_field_population_matches_spec_census(self, scores, census_snapshot):
        """Census: mimic.field_reported_counts (generated pin, snapshot
        key — n_cells here is the COALESCED value: legacy n text 509
        non-NULL minus 4 unparsed ('>4', three '>5') = 505 parsed)."""
        frep: Counter[str] = Counter()
        for s in scores:
            for name, st in s.fields.items():
                if st.status == "reported":
                    frep[name] += 1
        named = ("recording_mode", "stimulus_type", "temperature_c", "n_cells")
        assert {name: frep[name] for name in named} == census_snapshot["mimic"][
            "field_reported_counts"
        ]


class TestScoreAggregatePins:
    """Module-output determinism pins (inputs pinned above)."""

    def test_score_aggregates(self, scores, census_snapshot):
        assert len(scores) == census_snapshot["mimic"]["score_count"]
        vals = [s.score for s in scores]
        # score mean/median/max/min stay transcribed approx pins (module
        # numeric output, not re-derivable by trivial SQL)
        assert statistics.mean(vals) == pytest.approx(0.421020, abs=5e-7)
        assert statistics.median(vals) == pytest.approx(0.4375)
        assert max(vals) == pytest.approx(0.625)
        assert min(vals) == pytest.approx(0.0833333, abs=5e-7)
        # the honest headline: NO record is fully MIMIC-compliant
        tc = census_snapshot["mimic"]["score_threshold_counts"]
        assert sum(1 for v in vals if v == 1.0) == tc["eq_1"]
        assert sum(1 for v in vals if v >= 0.5) == tc["ge_05"]
        assert sum(1 for v in vals if v < 0.5) == tc["lt_05"]
        assert sum(1 for v in vals if v < 0.3) == tc["lt_03"]

    def test_applicability_distribution(self, scores, census_snapshot):
        """Applicable-count distribution over the artifact rows; cross-foots
        with the trigger census above (NULL 39 + OTHER 12 = 51). Snapshot
        keys are stringified counts (JSON object keys)."""
        dist = Counter(s.applicable for s in scores)
        assert {str(k): v for k, v in sorted(dist.items())} == census_snapshot[
            "mimic"
        ]["applicable_distribution"]

    def test_category_totals(self, scores, census_snapshot):
        cat: dict[str, tuple[int, int]] = {}
        for s in scores:
            for c, (rep, app) in s.categories.items():
                a = cat.get(c, (0, 0))
                cat[c] = (a[0] + rep, a[1] + app)
        assert cat == {
            k: (v[0], v[1]) for k, v in
            census_snapshot["mimic"]["category_totals"].items()
        }
        # cross-foot
        crossfoot = census_snapshot["mimic"]["category_crossfoot"]
        assert sum(v[0] for v in cat.values()) == crossfoot["reported"]
        assert sum(v[1] for v in cat.values()) == crossfoot["applicable"]

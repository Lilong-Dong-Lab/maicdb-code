"""Artifact-gated pins for the P6 field-trend layer (Track D).

Two pin kinds, disclosed per test (same convention as the P2/P3 files):

* raw-SQL-re-derivable pins cite the census SQL that recomputes the
  number directly from ``db/maicdb.sqlite``;
* module-output determinism pins (sparse row counts, grid shapes) whose
  inputs are pinned by the raw-SQL censuses alongside.

All descriptive counts (spec §5.4); no hypothesis tests (spec §6).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maicdb.analysis.trends import (
    PARAMETERS,
    assay_drift,
    load_trend_records,
    model_system_drift,
    parameter_adoption,
    pubs_per_year_by_family,
    pubs_per_year_total,
)
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
def records(engine):
    return load_trend_records(engine)


class TestLoaderCensuses:
    def test_full_coverage(self, records):
        """Census: 948 experiments (spec §3); every experiment joins to
        a publication year and a family (same LEFT JOIN coverage
        censuses as the P3 file: year NULL 0, family NULL 0)."""
        assert len(records) == 948
        assert sum(1 for r in records if r.year is None) == 0
        assert sum(1 for r in records if r.family is None) == 0

    def test_parameter_labels_are_census_totals(self, records):
        """Census (COUNT over the column, spec §3's coverage line):
        p50 152, conductance 263, tau_inact 93, x50 46 — the loader's
        presence detection must reproduce them exactly (this pins the
        label-vs-column pairing of PARAMETERS)."""
        for label, expected in (
            ("p50", 152),
            ("conductance", 263),
            ("tau_inact", 93),
            ("x50", 46),
        ):
            assert sum(1 for r in records if label in r.parameters) == expected


class TestPubsPerYear:
    def test_views_and_their_coincidence(self, records):
        """Census: DISTINCT (family, year, publication_id) tuples → 184;
        DISTINCT (year, publication_id) → 184. Module shapes: 105
        (year, family) cells summing to 184; 33 year totals summing to
        184. The two views coincide at data-v1.0 (no publication spans
        two families in one year) — pinned as a corpus fact, not a
        license to sum later (the pure tests hold the non-additivity
        contract)."""
        by_family = pubs_per_year_by_family(records)
        total = pubs_per_year_total(records)
        assert len(by_family) == 105
        assert sum(r.k for r in by_family) == 184
        assert len(total) == 33
        assert sum(t.k for t in total) == 184

    def test_year_anchors(self, records):
        """Census (COUNT DISTINCT publication_id JOIN year): 2010 → 5,
        2015 → 12, 2020 → 9, 2023 → 4."""
        total = {t.year: t.k for t in pubs_per_year_total(records)}
        assert total[2010] == 5
        assert total[2015] == 12
        assert total[2020] == 9
        assert total[2023] == 4

    def test_family_cell_anchor(self, records):
        """Census (COUNT DISTINCT publication_id WHERE year=2010 AND
        family='MSCL_MSCS') → 2; the 2010 family cells are
        MSCL_MSCS 2, PIEZO 1, TRP 2 (module output, SQL-re-derivable
        cell by cell)."""
        rows = {(r.family, r.k) for r in pubs_per_year_by_family(records)
                if r.year == 2010}
        assert rows == {("MSCL_MSCS", 2), ("PIEZO", 1), ("TRP", 2)}


class TestParameterAdoption:
    def test_grid_shape(self, records):
        """Grid: 33 distinct years × 17 PARAMETERS entries = 561 rows
        (census: COUNT DISTINCT year → 33, min 1986, max 2026 — the
        corpus's years are NOT contiguous, so the year set is pinned by
        membership within the span plus the count, not by a range).
        Labels (not column names) — the label set must equal the
        PARAMETERS label column (regression: a wrong unpack once
        emitted column names here)."""
        pa = parameter_adoption(records)
        assert len(pa) == 561
        assert {r.parameter for r in pa} == {label for _, label in PARAMETERS}
        years = {r.year for r in pa}
        assert len(years) == 33
        assert min(years) == 1986 and max(years) == 2026
        assert len(PARAMETERS) == 17

    def test_year_totals_via_of_year(self, records):
        """``of_year`` cross-foot: experiments per year. 2010 → 40
        (Census: COUNT JOIN year=2010 → 40)."""
        pa = parameter_adoption(records)
        of_2010 = {r.of_year for r in pa if r.year == 2010}
        assert of_2010 == {40}

    def test_anchor_cells(self, records):
        """Census anchors (COUNT(col) JOIN year): conductance 1986 → 2;
        p50 1998 → 1; thermal_threshold 2002 → 4 (column
        thermal_threshold_c)."""
        pa = parameter_adoption(records)

        def cell(label, year):
            return next(r.k for r in pa if r.parameter == label and r.year == year)

        assert cell("conductance", 1986) == 2
        assert cell("p50", 1998) == 1
        assert cell("thermal_threshold", 2002) == 4
        # corpus totals re-land through the grid
        for label, expected in (("p50", 152), ("conductance", 263)):
            assert sum(r.k for r in pa if r.parameter == label) == expected


class TestAssayDrift:
    def test_grid_shape_and_none_bucket(self, records):
        """Modes observed anywhere: 9 named + the None bucket (39
        records with no recording_mode — NULLIF census, the P3 file
        pins the same 39) = 10 keys; grid 33 years × 10 = 330 rows."""
        ad = assay_drift(records)
        assert len(ad) == 330
        assert len({r.recording_mode for r in ad}) == 10
        assert None in {r.recording_mode for r in ad}
        assert sum(r.k for r in ad if r.recording_mode is None) == 39

    def test_year_anchor(self, records):
        """Census (COUNT JOIN year=2010 GROUP BY recording_mode):
        CELL_ATTACHED 5, INSIDE_OUT 20, OTHER 1, TEVC 8, WHOLE_CELL 6
        (rest 0; year total 40)."""
        cells = {r.recording_mode: r.k for r in assay_drift(records)
                 if r.year == 2010 and r.k > 0}
        assert cells == {
            "CELL_ATTACHED": 5,
            "INSIDE_OUT": 20,
            "OTHER": 1,
            "TEVC": 8,
            "WHOLE_CELL": 6,
        }
        assert sum(cells.values()) == 40


class TestModelSystemDrift:
    def test_sparse_shape(self, records):
        """Sparse grid: 253 observed (year, expression_system) rows
        over 225 distinct systems (224 non-null DISTINCT NULLIF census
        + the None bucket, 41 NULL records)."""
        ms = model_system_drift(records)
        assert len(ms) == 253
        assert len({r.expression_system for r in ms}) == 225
        assert sum(r.k for r in ms if r.expression_system is None) == 41

    def test_anchor(self, records):
        """Census (COUNT JOIN year=2011 AND NULLIF(expression_system,'')
        IS NULL) → 23 — the None bucket's biggest year (module output,
        SQL-re-derivable)."""
        ms = model_system_drift(records)
        none_2011 = next(r.k for r in ms
                         if r.year == 2011 and r.expression_system is None)
        assert none_2011 == 23

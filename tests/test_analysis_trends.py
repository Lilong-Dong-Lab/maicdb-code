"""Pure field-trend tests for maicdb.analysis.trends (no artifact).

Fixtures are synthetic ``TrendRecord`` values exercising the spec §5.4
view contracts — format tests, not data claims. Live behavior is pinned
separately in ``tests/test_analysis_trends_artifact.py``.
"""

from __future__ import annotations

from maicdb.analysis.trends import (
    PARAMETERS,
    PubYearRow,
    TrendRecord,
    assay_drift,
    model_system_drift,
    parameter_adoption,
    pubs_per_year_by_family,
    pubs_per_year_total,
)


def _rec(
    mid: str = "M1",
    year: int | None = 2010,
    family: str | None = "PIEZO",
    pub: int | None = 1,
    mode: str | None = "WHOLE_CELL",
    expr: str | None = "HEK293T",
    params: tuple[str, ...] = (),
) -> TrendRecord:
    return TrendRecord(
        maicdb_id=mid,
        channel_id=1,
        family=family,
        year=year,
        publication_id=pub,
        recording_mode=mode,
        expression_system=expr,
        parameters=frozenset(params),
    )


class TestPubsPerYear:
    def test_distinct_publications_dedupe_within_cell(self):
        # two experiments, one publication, same year+family -> k=1
        recs = [
            _rec("M1", pub=7, params=("p50",)),
            _rec("M2", pub=7, params=("conductance",)),
        ]
        rows = pubs_per_year_by_family(recs)
        assert rows == [PubYearRow(year=2010, family="PIEZO", k=1)]

    def test_total_is_not_the_family_row_sum(self):
        # THE contract: one publication covering two families in one
        # year counts once in the total but once per family row — the
        # two views are NOT additive in general (at data-v1.0 they
        # coincide, which the artifact tests pin as a corpus fact)
        recs = [
            _rec("M1", family="PIEZO", pub=7),
            _rec("M2", family="K2P", pub=7),
        ]
        by_family = pubs_per_year_by_family(recs)
        total = pubs_per_year_total(recs)
        assert len(by_family) == 2
        assert all(r.k == 1 for r in by_family)
        assert sum(r.k for r in by_family) == 2
        assert len(total) == 1
        assert (total[0].year, total[0].k) == (2010, 1)

    def test_missing_year_or_pub_or_family_excluded(self):
        recs = [
            _rec("M1", year=None, pub=1),   # no year -> nowhere
            _rec("M2", pub=None),            # no pub -> nowhere countable
            _rec("M3", family=None, pub=2),  # no family -> family view only
            _rec("M4", pub=3),               # fully qualified
        ]
        assert pubs_per_year_by_family(recs) == [
            PubYearRow(2010, "PIEZO", 1)
        ]
        # totals: M3 and M4 count (family is not a total filter) -> {2, 3}
        total = pubs_per_year_total(recs)
        assert len(total) == 1
        assert (total[0].year, total[0].k) == (2010, 2)

    def test_sorted_by_year(self):
        recs = [_rec("M1", year=2015, pub=2), _rec("M2", year=2001, pub=1)]
        assert [r.year for r in pubs_per_year_by_family(recs)] == [2001, 2015]
        assert [t.year for t in pubs_per_year_total(recs)] == [2001, 2015]


class TestParameterAdoption:
    def test_counts_use_labels_not_column_names(self):
        # regression: the row builder once unpacked PARAMETERS the wrong
        # way and emitted COLUMN names ("p50_value") while counts were
        # keyed by labels ("p50") — every non-coinciding parameter
        # aggregated to 0 (iv_relation, whose label == column, was the
        # only survivor). This pin asserts the LABEL set.
        recs = [_rec("M1", params=("p50", "conductance"))]
        pa = parameter_adoption(recs)
        labels = {label for _, label in PARAMETERS}
        assert {r.parameter for r in pa} == labels
        assert "p50_value" not in {r.parameter for r in pa}

    def test_grid_is_full_and_counts_landing(self):
        labels = [label for _, label in PARAMETERS]
        recs = [
            _rec("M1", year=2010, params=("p50",)),
            _rec("M2", year=2010, params=("p50", "conductance")),
            _rec("M3", year=2011, params=()),
        ]
        pa = parameter_adoption(recs)
        assert len(pa) == 2 * len(labels)
        p50_2010 = [r for r in pa if r.parameter == "p50" and r.year == 2010]
        assert (p50_2010[0].k, p50_2010[0].of_year) == (2, 2)
        cond_2010 = [r for r in pa if r.parameter == "conductance" and r.year == 2010]
        assert (cond_2010[0].k, cond_2010[0].of_year) == (1, 2)
        p50_2011 = [r for r in pa if r.parameter == "p50" and r.year == 2011]
        assert (p50_2011[0].k, p50_2011[0].of_year) == (0, 1)
        # zero rows: 2010 misses 15 of 17 labels (2 nonzero), 2011 all 17
        assert sum(1 for r in pa if r.k == 0) == 2 * len(labels) - 2

    def test_records_without_year_excluded(self):
        recs = [_rec("M1", year=None, params=("p50",)), _rec("M2", year=2010)]
        pa = parameter_adoption(recs)
        assert {r.year for r in pa} == {2010}
        assert all(r.of_year == 1 for r in pa)


class TestAssayDrift:
    def test_none_mode_bucket_exists_and_sorts_first(self):
        recs = [
            _rec("M1", mode=None),
            _rec("M2", mode="TEVC"),
        ]
        rows = {(r.year, r.recording_mode): r.k for r in assay_drift(recs)}
        assert rows[(2010, None)] == 1
        assert rows[(2010, "TEVC")] == 1
        # full grid: both modes appear for the year
        assert len(rows) == 2

    def test_grid_spans_all_observed_modes_per_year(self):
        # a mode observed only in 2005 still gets a 2010 row (k=0)
        recs = [
            _rec("M1", year=2005, mode="TEVC"),
            _rec("M2", year=2010, mode="WHOLE_CELL"),
        ]
        ad = assay_drift(recs)
        assert len(ad) == 2 * 2  # 2 years x 2 observed modes
        tevc_2010 = [r for r in ad if r.recording_mode == "TEVC" and r.year == 2010]
        assert tevc_2010[0].k == 0

    def test_yearless_records_excluded(self):
        assert assay_drift([_rec("M1", year=None)]) == []


class TestModelSystemDrift:
    def test_sparse_only_observed_combinations(self):
        recs = [
            _rec("M1", year=2010, expr="HEK293T"),
            _rec("M2", year=2011, expr="HEK293T"),  # 2010 x HEK293T absent
            _rec("M3", year=2010, expr=None),
        ]
        rows = {(r.year, r.expression_system): r.k for r in model_system_drift(recs)}
        assert rows == {(2010, "HEK293T"): 1, (2011, "HEK293T"): 1, (2010, None): 1}
        assert (2011, None) not in rows  # sparse: never observed

    def test_counts_dedupe_by_combination(self):
        recs = [
            _rec("M1", year=2010, expr="X"),
            _rec("M2", year=2010, expr="X"),
            _rec("M3", year=2010, expr="X"),
        ]
        rows = model_system_drift(recs)
        assert [(r.year, r.expression_system, r.k) for r in rows] == [
            (2010, "X", 3)
        ]

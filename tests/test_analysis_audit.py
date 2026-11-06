"""Pure audit-view tests for maicdb.analysis.audit (no artifact).

Fixtures are synthetic records and scores exercising the spec §5.1 view
contracts — format tests, not data claims. Live behavior is pinned
separately in ``tests/test_analysis_audit_artifact.py``.
"""

from __future__ import annotations

import pytest

from maicdb.analysis.audit import (
    CONTEXT_FIELDS,
    MANDATED_FIELDS,
    PIEZO_YEAR,
    breakdown,
    category_weighted_mean,
    compliance_by_year,
    field_totals,
    four_field_audit,
    heatmap,
    weighted_score,
)
from maicdb.analysis.mimic import score_record


def _rec(**over: object) -> dict[str, object]:
    base: dict[str, object] = {"maicdb_id": "MAIC:BX:TEST", "channel_id": 1}
    base.update(over)
    return base


def _scores(*records: dict[str, object]):
    return [score_record(r) for r in records]


class TestHeatmap:
    def test_tri_state_counts_land_in_cells(self):
        # three records, same family: one reports temperature, one does
        # not, one has no temperature either (not_extracted on v1.0)
        scores = _scores(
            _rec(maicdb_id="A", channel_id=1, temperature_c=25.0),
            _rec(maicdb_id="B", channel_id=2),
            _rec(maicdb_id="C", channel_id=3, ph=7.4),
        )
        families = {1: "PIEZO", 2: "PIEZO", 3: "PIEZO"}
        hm = heatmap(scores, families)
        cell = hm["PIEZO"]["temperature_c"]
        assert (cell.reported, cell.not_reported, cell.not_extracted) == (1, 0, 2)
        assert cell.applicable == 3
        assert cell.compliance == pytest.approx(1 / 3)
        # ph: 1 of 3 reported
        ph = hm["PIEZO"]["ph"]
        assert (ph.reported, ph.applicable) == (1, 3)
        # always-applicable conditional field, no moving-probe stimulus:
        # velocity cell is empty-but-inapplicable
        vel = hm["PIEZO"]["stimulus_velocity"]
        assert vel.applicable == 0
        assert vel.compliance is None

    def test_unknown_family_gets_reserved_slice(self):
        scores = _scores(_rec(channel_id=99))
        hm = heatmap(scores, {})  # no families known
        assert set(hm) == {"?"}
        assert hm["?"]["recording_mode"].applicable == 1

    def test_slices_and_fields_sorted(self):
        scores = _scores(
            _rec(maicdb_id="A", channel_id=1),
            _rec(maicdb_id="B", channel_id=2),
        )
        hm = heatmap(scores, {1: "TRP", 2: "K2P"})
        assert list(hm) == sorted(hm) == ["K2P", "TRP"]
        for fields in hm.values():
            assert list(fields) == sorted(fields)


class TestFieldTotals:
    def test_conditional_denominator_is_applicable_set(self):
        # one INDENTATION record (velocity + geometry applicable) with
        # both missing, one STRETCH record (inapplicable) with them
        # missing too — totals must NOT count the stretch record
        scores = _scores(
            _rec(stimulus_type="INDENTATION"),
            _rec(maicdb_id="B", stimulus_type="STRETCH"),
        )
        totals = field_totals(scores)
        assert totals["stimulus_velocity"].applicable == 1
        assert totals["stimulus_velocity"].not_extracted == 1
        assert totals["probe_geometry"].applicable == 1
        # always-applicable field counts both records
        assert totals["recording_mode"].applicable == 2

    def test_always_applicable_equals_populated_share(self):
        scores = _scores(
            _rec(temperature_c=25.0),
            _rec(maicdb_id="B"),
        )
        cell = field_totals(scores)["temperature_c"]
        assert cell.applicable == 2 and cell.reported == 1
        assert cell.compliance == pytest.approx(0.5)


class TestComplianceByYear:
    def test_era_boundary_is_piezo_cloning_year(self):
        assert PIEZO_YEAR == 2010
        scores = [score_record(_rec(maicdb_id=i)) for i in ("A", "B", "C")]
        years = {"A": 2009, "B": 2010, "C": 2011}
        era = compliance_by_year(scores, years)
        assert era.pre_k == 1 and era.post_k == 2
        assert [y.year for y in era.years] == [2009, 2010, 2011]
        assert era.unassigned_k == 0

    def test_missing_year_is_unassigned_not_dropped_silently(self):
        scores = _scores(_rec(maicdb_id="A"), _rec(maicdb_id="B"))
        era = compliance_by_year(scores, {"A": 2001})  # B unknown
        assert era.unassigned_k == 1
        assert era.pre_k == 1 and era.post_k == 0
        assert era.post_mean == 0.0
        assert [y.year for y in era.years] == [2001]

    def test_year_mean_is_mean_of_per_record_scores(self):
        # A reports temperature (higher compliance), B does not
        scores = [
            score_record(_rec(maicdb_id="A", temperature_c=25.0)),
            score_record(_rec(maicdb_id="B")),
        ]
        era = compliance_by_year(scores, {"A": 2005, "B": 2005})
        (row,) = era.years
        assert row.k == 2
        assert row.mean == pytest.approx(
            (scores[0].score + scores[1].score) / 2
        )


class TestBreakdown:
    def test_groups_sorted_with_k_and_mean(self):
        from maicdb.analysis.audit import RecordMeta

        scores = [
            score_record(_rec(maicdb_id="A", temperature_c=25.0)),
            score_record(_rec(maicdb_id="B")),
            score_record(_rec(maicdb_id="C", recording_mode="TEVC")),
        ]
        meta = {
            "A": RecordMeta("PIEZO", 2010, "Nature", "WHOLE_CELL", "STRETCH"),
            "B": RecordMeta("K2P", 2005, "Science", "INSIDE_OUT", "PRESSURE_CLAMP"),
            "C": RecordMeta("TMC", 2015, "Nature", None, None),
        }
        by_journal = breakdown(scores, meta, "journal")
        assert [g.group for g in by_journal] == ["Nature", "Science"]
        assert by_journal[0].k == 2
        assert by_journal[1].k == 1
        # by recording_mode: None dropped
        by_mode = breakdown(scores, meta, "recording_mode")
        assert {g.group for g in by_mode} == {"WHOLE_CELL", "INSIDE_OUT"}
        assert sum(g.k for g in by_mode) == 2  # C dropped (None)

    def test_bad_key_raises(self):
        with pytest.raises(ValueError):
            breakdown([], {}, "gene_symbol")

    def test_empty_key_value_dropped(self):
        from maicdb.analysis.audit import RecordMeta

        scores = [score_record(_rec(maicdb_id="A"))]
        meta = {"A": RecordMeta("PIEZO", 2010, "", "WHOLE_CELL", "STRETCH")}
        by_journal = breakdown(scores, meta, "journal")
        assert by_journal == []  # empty string is not a group


class TestWeightedScore:
    def test_all_ones_weights_reproduce_unweighted(self):
        score = score_record(_rec(temperature_c=25.0))
        assert weighted_score(score, {c: 1.0 for c in score.categories}) == (
            pytest.approx(score.score)
        )

    def test_sparse_weights_ignore_unlisted_categories(self):
        # contract: unlisted categories default to weight 0 (sparse
        # weighting — "re-weight these categories" semantics)
        score = score_record(_rec(temperature_c=25.0))
        stimulus_rep, stimulus_app = score.categories["stimulus"]
        assert (stimulus_rep, stimulus_app) == (0, 3)  # temp is environment
        # only the stimulus category counts: 0 reported of 3 applicable
        assert weighted_score(score, {"stimulus": 10.0}) == 0.0
        # environment-only: temperature 1 of 3, weight cancels
        assert weighted_score(score, {"environment": 2.0}) == pytest.approx(1 / 3)
        # two categories: (1 + 0) / (3 + 3)
        two = weighted_score(score, {"environment": 1.0, "analysis": 1.0})
        assert two == pytest.approx(1 / 6)
        # sparse-only reweighting drags the unweighted score down here
        assert weighted_score(score, {"stimulus": 10.0}) < score.score

    def test_validation(self):
        score = score_record(_rec())
        with pytest.raises(ValueError):
            weighted_score(score, {})
        with pytest.raises(ValueError):
            weighted_score(score, {"not_a_category": 1.0})
        with pytest.raises(ValueError):
            weighted_score(score, {"stimulus": -1.0})

    def test_weighted_mean_of_many(self):
        scores = [score_record(_rec(maicdb_id="A", temperature_c=25.0)),
                  score_record(_rec(maicdb_id="B"))]
        weights = {"environment": 2.0, "stimulus": 1.0}
        mean = category_weighted_mean(scores, weights)
        assert mean == pytest.approx(
            sum(weighted_score(s, weights) for s in scores) / 2
        )


class TestFourFieldAudit:
    def test_as_written_ignores_applicability(self):
        # velocity missing on a STRETCH record: not an ADR failure
        # (inapplicable) but IS an as-written failure (vault §9's own
        # reading demands the field regardless)
        records = [_rec(stimulus_type="STRETCH", recording_mode="TEVC",
                        cell_type="HEK", temperature_c=25.0)]
        audit = four_field_audit(records)
        vel = audit.fields["stimulus_velocity"]
        assert vel.missing_as_written == 1
        assert vel.applicable == 0
        assert vel.missing_when_applicable == 0
        assert vel.adr_fail_rate is None
        assert vel.as_written_fail_rate == pytest.approx(1.0)

    def test_adr_aware_indentation_missing_geometry_fails_both(self):
        records = [_rec(stimulus_type="INDENTATION", recording_mode="TEVC",
                        cell_type="HEK", temperature_c=25.0)]
        audit = four_field_audit(records)
        assert audit.fields["stimulus_velocity"].missing_when_applicable == 1
        assert audit.fields["probe_geometry"].missing_when_applicable == 1
        assert audit.failing_any_adr == (1, 1)
        assert audit.failing_any_as_written == (1, 1)

    def test_null_stimulus_excludes_dependents(self):
        # ADR-0005: NULL stimulus excludes dependent fields — such a
        # record cannot fail velocity/geometry (the module's None
        # handling matches the NULL-safe census; naive SQL NOT-forms
        # are NULL-poisoned and undercount the clean set)
        records = [_rec(stimulus_type=None, recording_mode="TEVC",
                        cell_type="HEK", temperature_c=25.0)]
        audit = four_field_audit(records)
        assert audit.fields["stimulus_velocity"].missing_when_applicable == 0
        assert audit.fields["probe_geometry"].missing_when_applicable == 0
        assert audit.failing_any_adr == (0, 1)
        # as-written still fails (velocity absent, applicability ignored)
        assert audit.failing_any_as_written == (1, 1)

    def test_context_is_strict_conjunction(self):
        assert CONTEXT_FIELDS == ("cell_type", "temperature_c")
        only_cell = _rec(stimulus_type="STRETCH", recording_mode="TEVC",
                         cell_type="HEK")
        only_temp = _rec(maicdb_id="B", stimulus_type="STRETCH",
                         recording_mode="TEVC", temperature_c=25.0)
        both = _rec(maicdb_id="C", stimulus_type="STRETCH",
                    recording_mode="TEVC", cell_type="HEK", temperature_c=25.0)
        audit = four_field_audit([only_cell, only_temp, both])
        ctx = audit.fields["experimental_context"]
        assert ctx.missing_as_written == 2
        assert ctx.missing_when_applicable == 2
        assert ctx.applicable == 3
        assert ctx.adr_fail_rate == pytest.approx(2 / 3)
        assert audit.failing_any_adr == (2, 3)

    def test_mandated_list_matches_vault_section_nine(self):
        assert MANDATED_FIELDS == (
            "stimulus_velocity",
            "probe_geometry",
            "recording_mode",
            "experimental_context",
        )

    def test_clean_record_fails_nothing(self):
        # fully-populated INDENTATION record: geometry applicable AND
        # present, velocity applicable AND present — passes both readings
        clean = _rec(stimulus_type="INDENTATION", stimulus_velocity=5.0,
                     probe_geometry="sphere", recording_mode="OUTSIDE_OUT",
                     cell_type="HEK", temperature_c=25.0)
        audit = four_field_audit([clean])
        assert audit.failing_any_as_written == (0, 1)
        assert audit.failing_any_adr == (0, 1)
        for row in audit.fields.values():
            assert row.missing_when_applicable == 0

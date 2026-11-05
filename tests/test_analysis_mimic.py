"""Pure MIMIC-scoring tests for maicdb.analysis.mimic (no artifact).

Fixtures are synthetic records exercising the ADR-0005 applicability
matrix and tri-state semantics — format/contract tests, not data claims.
Live behavior is pinned separately in ``tests/test_analysis_mimic_artifact.py``.
"""

from __future__ import annotations

from maicdb.analysis.mimic import (
    CATEGORIES,
    MIMIC_FIELDS,
    applicable_fields,
    score_record,
)


def _rec(**over: object) -> dict[str, object]:
    base: dict[str, object] = {"maicdb_id": "MAIC:BX:TEST", "channel_id": 1}
    base.update(over)
    return base


class TestApplicability:
    def test_twelve_always_applicable(self):
        # empty record: only the 12 ADR-unconditional fields apply
        app = applicable_fields(_rec())
        assert sum(app.values()) == 12
        assert not app["stimulus_velocity"]
        assert not app["probe_geometry"]
        assert not app["pipette_solution"]
        assert not app["sampling_rate_khz"]

    def test_pressure_clamp_cell_attached(self):
        # stimulus not moving-probe; mode is pipette-based + ephys
        app = applicable_fields(
            _rec(stimulus_type="PRESSURE_CLAMP", recording_mode="CELL_ATTACHED")
        )
        assert sum(app.values()) == 16  # 12 + pipette 2 + ephys 2
        assert app["pipette_solution"] and app["holding_potential_mv"]
        assert app["sampling_rate_khz"] and app["filter_khz"]
        assert not app["stimulus_velocity"] and not app["probe_geometry"]

    def test_indentation_inside_out_all_19(self):
        app = applicable_fields(
            _rec(stimulus_type="INDENTATION", recording_mode="INSIDE_OUT")
        )
        assert sum(app.values()) == 19

    def test_shear_stress_counts_as_moving_probe(self):
        app = applicable_fields(_rec(stimulus_type="SHEAR_STRESS"))
        assert app["stimulus_velocity"] is True
        assert app["probe_geometry"] is False  # geometry only for INDENTATION

    def test_tevc_not_pipette_but_ephys(self):
        app = applicable_fields(_rec(recording_mode="TEVC"))
        assert app["sampling_rate_khz"] is True
        assert app["pipette_solution"] is False

    def test_proteoliposome_ephys_not_pipette(self):
        app = applicable_fields(_rec(recording_mode="RECONSTITUTED_PROTEOLIPOSOME"))
        assert app["sampling_rate_khz"] is True
        assert app["pipette_solution"] is False

    def test_other_mode_defaults_not_applicable(self):
        # ADR-0005: OTHER is P3's per-record call with disclosure;
        # P2 defaults it to not-applicable
        app = applicable_fields(_rec(recording_mode="OTHER"))
        assert not app["pipette_solution"]
        assert not app["sampling_rate_khz"]

    def test_vocabulary_completeness(self):
        assert len(MIMIC_FIELDS) == 19  # the §4.3 vocabulary
        assert set(CATEGORIES) == {
            "stimulus",
            "recording",
            "cell_context",
            "environment",
            "analysis",
        }


class TestScoring:
    def test_score_fraction(self):
        rec = _rec(
            stimulus_type="PRESSURE_CLAMP",
            recording_mode="WHOLE_CELL",
            temperature_c=25.0,
            bath_solution="NaCl bath",
            ph=7.4,
        )
        s = score_record(rec)
        assert s.applicable == 16
        assert s.reported == 5  # stimulus_type, recording_mode, temp, bath, ph
        assert s.score == 5 / 16

    def test_empty_record_scores_zero(self):
        s = score_record(_rec())
        assert s.reported == 0
        assert s.score == 0.0

    def test_tri_state_distinction(self):
        # empty temperature: not_extracted without gaps, not_reported with
        rec = _rec(stimulus_type="PRESSURE_CLAMP", recording_mode="WHOLE_CELL")
        plain = score_record(rec)
        gapped = score_record(rec, mimic_gaps=["temperature_c"])
        assert plain.fields["temperature_c"].status == "not_extracted"
        assert gapped.fields["temperature_c"].status == "not_reported"
        # status differs, score identical (both are non-reported)
        assert plain.score == gapped.score

    def test_not_applicable_never_counts(self):
        rec = _rec(recording_mode="OTHER")
        s = score_record(rec)
        assert s.applicable == 12
        assert s.fields["pipette_solution"].status == "not_applicable"

    def test_n_cells_coalesce_counts_as_reported(self):
        # n_cells INTEGER empty but legacy n text has a range
        s = score_record(_rec(n_cells=None, n="5-9"))
        assert s.fields["n_cells"].status == "reported"

    def test_n_cells_unparsed_stays_not_extracted(self):
        s = score_record(_rec(n_cells=None, n=">4"))
        assert s.fields["n_cells"].status == "not_extracted"

    def test_empty_string_counts_as_not_extracted(self):
        # gate MINOR-1 regression: spec §3's NULLIF convention — a future
        # release carrying '' in a text column must not score reported
        s = score_record(_rec(cell_type=""))
        assert s.fields["cell_type"].status == "not_extracted"

    def test_zero_values_still_reported(self):
        # the '' normalization must not eat legitimate zeros
        s = score_record(_rec(temperature_c=0.0, ph=0))
        assert s.fields["temperature_c"].status == "reported"
        assert s.fields["ph"].status == "reported"

    def test_category_sums_match_totals(self):
        rec = _rec(
            stimulus_type="PRESSURE_CLAMP",
            recording_mode="INSIDE_OUT",
            cell_type="HEK293T",
            expression_system="heterologous",
        )
        s = score_record(rec)
        assert sum(v[0] for v in s.categories.values()) == s.reported
        assert sum(v[1] for v in s.categories.values()) == s.applicable
        assert s.categories["cell_context"] == (2, 2)

    def test_to_dict_round_trips(self):
        import json

        s = score_record(_rec(stimulus_type="INDENTATION", recording_mode="OTHER"))
        payload = json.loads(json.dumps(s.to_dict()))
        assert payload["maicdb_id"] == "MAIC:BX:TEST"
        assert payload["applicable"] == 15  # 12 always + velocity + geometry pair
        assert payload["fields"]["probe_geometry"]["applicable"] is True
        assert payload["fields"]["pipette_solution"]["applicable"] is False

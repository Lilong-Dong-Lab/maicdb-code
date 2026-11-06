"""Pure pActivity tests for maicdb.analysis.activity (no artifact).

Landmarks are exact logarithms: 100 µM = 1e-4 M → pActivity 4.0;
10 nM → 8.0. The micro-sign normalization is a data-driven requirement:
data-v1.0 carries both U+00B5 (µM, 75 rows) and U+03BC (μM, 12 rows) —
census SQL in ``tests/test_analysis_artifact.py``.
"""

from __future__ import annotations

import pytest

from maicdb.analysis.activity import p_activity, to_molar


class TestToMolar:
    def test_micro_signs_normalized(self):
        # U+00B5 MICRO SIGN and U+03BC GREEK SMALL LETTER MU
        assert to_molar(1.0, "µM") == to_molar(1.0, "μM") == 1e-6

    def test_scale_ladder(self):
        assert to_molar(1.0, "M") == 1.0
        assert to_molar(1.0, "mM") == 1e-3
        assert to_molar(1.0, "nM") == 1e-9

    def test_unknown_unit_none(self):
        # free-text column: unknown unit -> None (caller decides policy)
        assert to_molar(1.0, "%") is None


class TestPActivity:
    def test_molar_landmark_100um(self):
        pa = p_activity(100.0, "µM")
        assert pa.value == pytest.approx(4.0)
        assert pa.basis == "molar"

    def test_molar_landmark_10nm(self):
        assert p_activity(10.0, "nM").value == pytest.approx(8.0)

    def test_greek_micro_same_result(self):
        assert p_activity(100.0, "µM").value == p_activity(100.0, "μM").value

    def test_already_plog_passthrough(self):
        pa = p_activity(8.12, "-log M")
        assert pa.value == 8.12
        assert pa.basis == "already_plog"
        assert pa.as_reported == 8.12

    def test_mass_with_mw(self):
        # 10 μg/ml with MW 500 g/mol -> 1e-3*10/500 = 2e-5 M -> p 4.6990
        pa = p_activity(10.0, "μg/ml", molecular_weight=500.0)
        assert pa.value == pytest.approx(4.6990, rel=1e-4)
        assert pa.basis == "mass_from_mw"

    def test_mass_without_mw_honest_none(self):
        pa = p_activity(10.0, "μg/ml", molecular_weight=None)
        assert pa.value is None
        assert pa.basis == "mass_no_mw"
        assert pa.detail is not None

    def test_mass_micro_sign_b5_accepted(self):
        # gate n2 regression: U+00B5 µg/ml must behave like U+03BC μg/ml
        pa_b5 = p_activity(10.0, "µg/ml", molecular_weight=500.0)
        pa_bc = p_activity(10.0, "μg/ml", molecular_weight=500.0)
        assert pa_b5.basis == pa_bc.basis == "mass_from_mw"
        assert pa_b5.value == pa_bc.value

    def test_missing_value(self):
        assert p_activity(None, "nM").basis == "missing_value"
        assert p_activity(1.0, None).basis == "missing_value"

    def test_nonpositive_molar(self):
        pa = p_activity(0.0, "M")
        assert pa.value is None
        assert pa.basis == "nonpositive_value"

    def test_unknown_unit_graceful(self):
        pa = p_activity(50.0, "%")
        assert pa.value is None
        assert pa.basis == "unknown_unit"
        assert pa.as_reported == 50.0  # raw pair preserved

    def test_as_reported_preserved(self):
        pa = p_activity(75.0, "µM")
        assert (pa.as_reported, pa.as_reported_unit) == (75.0, "µM")

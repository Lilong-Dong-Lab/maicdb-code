"""Pure unit-conversion tests for maicdb.analysis.units (no artifact).

Expectations are physics-anchored landmarks, not re-runs of the module:
1 atm = 101325 Pa (exact, SI definition) sits on 759.9999 conventional
mmHg (101325 / 133.322387415 = 759.99989…, 4dp) and 14.6959488 psi; the
conventional mmHg differs from the torr by ~0.5 ppm, hence NOT exactly
760. 1 dyn/cm is exactly 1 mN/m (1e-5 N / 1e-2 m).
"""

from __future__ import annotations

import pytest

from maicdb.analysis.units import (
    Converted,
    length_to_um,
    pressure_to_mmhg,
    tension_to_mnm,
)

# 101325 / 133.322387415 at 4 decimal places (Decimal-verified).
_ATM_MMHG_4DP = 759.9999


class TestPressureToMmhg:
    def test_atm_landmark_from_pa(self):
        conv = pressure_to_mmhg(101325.0, "Pa")
        assert round(conv.value, 4) == _ATM_MMHG_4DP
        assert conv.converted is True

    def test_atm_landmark_from_psi(self):
        # 14.6959488 psi (independent psi expression of 1 atm)
        conv = pressure_to_mmhg(14.6959488, "psi")
        assert round(conv.value, 4) == _ATM_MMHG_4DP

    def test_atm_landmark_from_mbar(self):
        conv = pressure_to_mmhg(1013.25, "mbar")  # 1 atm in mbar
        assert round(conv.value, 4) == _ATM_MMHG_4DP

    def test_identity_mmhg(self):
        conv = pressure_to_mmhg(76.3, "mmHg")
        assert conv.value == 76.3
        assert conv.converted is False
        assert conv.as_reported == 76.3
        assert conv.as_reported_unit == "mmHg"

    def test_kpa_and_cmh2o(self):
        assert pressure_to_mmhg(1.0, "kPa").value == pytest.approx(
            1000.0 / 133.322387415
        )
        assert pressure_to_mmhg(1.0, "cmH2O").value == pytest.approx(
            98.0665 / 133.322387415
        )

    def test_negative_preserved(self):
        # suction-axis values are negative in the artifact's sign convention
        conv = pressure_to_mmhg(-27.0, "mmHg")
        assert conv.value == -27.0
        assert conv.converted is False

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError, match="torr"):
            pressure_to_mmhg(1.0, "torr")

    def test_all_check_constraint_units_accepted(self):
        # the pressureunit CHECK vocabulary from src/maicdb/schema.sql
        for unit in ("mmHg", "kPa", "Pa", "mbar", "cmH2O", "psi"):
            conv = pressure_to_mmhg(1.0, unit)
            assert isinstance(conv, Converted)


class TestTensionToMnm:
    def test_dyn_cm_identity_exact(self):
        conv = tension_to_mnm(11.8, "dyn/cm")
        assert conv.value == 11.8
        assert conv.converted is False

    def test_nm_per_um_row(self):
        assert tension_to_mnm(1.0, "pN/um").value == pytest.approx(0.001)
        assert tension_to_mnm(1.0, "N/m").value == 1000.0

    def test_identity_mnm(self):
        conv = tension_to_mnm(12.5, "mN/m")
        assert conv.value == 12.5
        assert conv.converted is False

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError, match="unknown tension unit"):
            tension_to_mnm(1.0, "psi")


class TestLengthToUm:
    def test_nm_to_um(self):
        conv = length_to_um(27.0, "nm")
        assert conv.value == pytest.approx(0.027)
        assert conv.converted is True

    def test_mm_to_um(self):
        assert length_to_um(1.0, "mm").value == 1000.0

    def test_identity_um(self):
        conv = length_to_um(5.0, "um")
        assert conv.value == 5.0
        assert conv.converted is False

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError, match="unknown length unit"):
            length_to_um(1.0, "cm")

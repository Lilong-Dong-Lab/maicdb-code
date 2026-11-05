"""pActivity derivation for the analysis layer (P1).

``pActivity = −log10(activity_value [M])`` — spec §7.3 (final, ADR-0005).

``bioactivity.activity_units`` is free text (no CHECK constraint), so this
module is deliberately graceful where ``units.py`` is strict: unknown unit
strings yield ``basis="unknown_unit"`` with the raw pair preserved, instead
of raising. The observed data-v1.0 vocabulary (census SQL in
``tests/test_analysis_artifact.py``) is: nM, µM, μM (TWO different micro
signs — U+00B5 and U+03BC — normalized here), mM, M, "-log M" (value is
already a −log10), "μg/ml" (mass concentration: molar only via the
compound's molecular weight; the data-v1.0 μg/ml rows are silica
nanoparticles without MW → ``basis="mass_no_mw"``), and NULL.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["PActivity", "p_activity", "to_molar"]

# Factor multiplying the source value into mol/L. Both micro signs
# (U+00B5 MICRO SIGN, U+03BC GREEK SMALL LETTER MU) map to 1e-6.
_MOLAR_PER_UNIT: dict[str, float] = {
    "M": 1.0,
    "mM": 1e-3,
    "µM": 1e-6,  # U+00B5
    "μM": 1e-6,  # U+03BC
    "nM": 1e-9,
}

# g per L for the mass-concentration form: 1 μg/ml = 1 mg/L = 1e-3 g/L.
_G_PER_L_PER_UG_PER_ML = 1e-3


@dataclass(frozen=True)
class PActivity:
    """A derived pActivity with its basis disclosed."""

    value: float | None  # −log10(mol/L) where derivable
    basis: str  # "molar" | "already_plog" | "mass_from_mw" | "mass_no_mw"
    # | "missing_value" | "nonpositive_value" | "unknown_unit"
    as_reported: float | None  # input value, untouched
    as_reported_unit: str | None  # input unit, untouched
    detail: str | None  # disclosure line for the non-derivable bases


def to_molar(value: float, unit: str) -> float | None:
    """Convert a molar-unit concentration to mol/L; None for an unknown
    unit (caller decides strictness — the vocabulary is free text)."""
    factor = _MOLAR_PER_UNIT.get(unit)
    if factor is None:
        return None
    return value * factor


def p_activity(
    value: float | None, unit: str | None, molecular_weight: float | None = None
) -> PActivity:
    """Derive pActivity from an as-reported activity value.

    ``molecular_weight`` is the compound's MW in g/mol (from
    ``compound.molecular_weight``), needed only for the μg/ml form.
    """
    if value is None or unit is None:
        return PActivity(None, "missing_value", value, unit, None)
    if unit == "-log M":
        # The stored value IS already −log10(mol/L) — pass through.
        return PActivity(value, "already_plog", value, unit, None)
    molar = to_molar(value, unit)
    if molar is not None:
        if molar <= 0:
            return PActivity(
                None,
                "nonpositive_value",
                value,
                unit,
                "log10 undefined for non-positive molar concentration",
            )
        return PActivity(
            value=-math.log10(molar),
            basis="molar",
            as_reported=value,
            as_reported_unit=unit,
            detail=None,
        )
    if unit == "μg/ml":
        if molecular_weight is None or molecular_weight <= 0:
            return PActivity(
                None,
                "mass_no_mw",
                value,
                unit,
                "mass concentration without compound molecular_weight — "
                "not convertible to molar",
            )
        molar = value * _G_PER_L_PER_UG_PER_ML / molecular_weight
        return PActivity(-math.log10(molar), "mass_from_mw", value, unit, None)
    return PActivity(None, "unknown_unit", value, unit, f"unit {unit!r}")

"""Canonical-unit conversions for the analysis layer (P1).

Authority: ADR-0005 (``docs/adr/0005-mimic-tri-state-hybrid.md`` §unit
policy) — analysis converts row-level values to one canonical unit per
modality (pressure → mmHg, membrane tension → mN/m, indentation → µm) and
always preserves the as-reported pair.

Scope seam vs ``maicdb.query``: the M1 query layer never inter-converts
within a modality and groups aggregates per stored unit (its docstring,
"Modality separation"); that rule binds ``maicdb.query`` outputs. This
module is a different consumer with a different contract — the conversion
itself — defined by ADR-0005. Nothing here writes to the artifact.

Unit vocabularies mirror the CHECK constraints in ``src/maicdb/schema.sql``
(``pressureunit``, ``tensionunit``, ``indentationunit``); an unknown unit
raises ``ValueError`` (strict, loader-style), because enum-backed columns
guarantee the vocabulary.

Physical constants (pointable in the table below):

* conventional mmHg := 133.322387415 Pa (BIPM conventional millimetre of
  mercury, 10th CGPM 1954);
* psi := lbf/in² with lbf = 4.4482216152605 N (exact SI definition of the
  pound-force) and 1 in = 0.0254 m (exact) — computed by division, not a
  magic float;
* conventional cmH2O := 98.0665 Pa (9806.65 Pa/m × 0.01 m);
* mbar = 100 Pa and kPa = 1000 Pa (exact SI decimal prefixes);
* dyn/cm ≡ mN/m exactly (1e-5 N / 1e-2 m = 1e-3 N/m) — the well-known
  membrane-biophysics identity, visible as the equal factors below;
* pN/µm = 1e-12 N / 1e-6 m = 1e-6 N/m = 0.001 mN/m.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "Converted",
    "length_to_um",
    "pressure_to_mmhg",
    "tension_to_mnm",
]

# Pa per source unit (pressure family; canonical target mmHg).
_PA_PER_UNIT: dict[str, float] = {
    "Pa": 1.0,
    "mbar": 100.0,  # exact SI decimal prefix
    "kPa": 1000.0,  # exact SI decimal prefix
    "mmHg": 133.322387415,  # conventional mmHg (BIPM)
    "cmH2O": 98.0665,  # conventional cm of water
    "psi": 4.4482216152605 / (0.0254**2),  # exact lbf / in²
}
_MMHG_PER_PA = 1.0 / 133.322387415

# Factor multiplying the source value into mN/m (tension family).
_MNM_PER_UNIT: dict[str, float] = {
    "mN/m": 1.0,
    "dyn/cm": 1.0,  # exact identity: 1 dyn/cm ≡ 1 mN/m
    "pN/um": 0.001,  # 1e-12 N / 1e-6 m = 1e-6 N/m
    "N/m": 1000.0,
}

# Factor multiplying the source value into µm (indentation family).
_UM_PER_UNIT: dict[str, float] = {
    "um": 1.0,
    "mm": 1000.0,
    "nm": 0.001,
}


@dataclass(frozen=True)
class Converted:
    """A converted measurement with its as-reported pair preserved."""

    value: float  # canonical-unit value
    unit: str  # canonical unit name ("mmHg", "mN/m", or "um")
    as_reported: float  # the input value, untouched
    as_reported_unit: str  # the input unit, untouched
    converted: bool  # False when the source unit IS the canonical unit


def _to_canonical(
    value: float, unit: str, table: dict[str, float], target: str, family: str
) -> Converted:
    factor = table.get(unit)
    if factor is None:
        known = ", ".join(sorted(table))
        raise ValueError(
            f"unknown {family} unit {unit!r}; known units: {known}"
        )
    if unit == target or factor == 1.0:
        # identity (same unit) or exact renaming (e.g. dyn/cm ≡ mN/m):
        # no arithmetic, numerically unchanged
        return Converted(value, target, value, unit, converted=False)
    return Converted(
        value=value * factor,
        unit=target,
        as_reported=value,
        as_reported_unit=unit,
        converted=True,
    )


def pressure_to_mmhg(value: float, unit: str) -> Converted:
    """Convert a pressure value to canonical mmHg via the Pa pivot."""
    if unit == "mmHg":
        return Converted(value, "mmHg", value, unit, converted=False)
    factor = _PA_PER_UNIT.get(unit)
    if factor is None:
        known = ", ".join(sorted(_PA_PER_UNIT))
        raise ValueError(
            f"unknown pressure unit {unit!r}; known units: {known}"
        )
    return Converted(
        value=value * factor * _MMHG_PER_PA,
        unit="mmHg",
        as_reported=value,
        as_reported_unit=unit,
        converted=True,
    )


def tension_to_mnm(value: float, unit: str) -> Converted:
    """Convert a membrane-tension value to canonical mN/m."""
    return _to_canonical(value, unit, _MNM_PER_UNIT, "mN/m", "tension")


def length_to_um(value: float, unit: str) -> Converted:
    """Convert an indentation-depth value to canonical µm (unit token "um")."""
    return _to_canonical(value, unit, _UM_PER_UNIT, "um", "length")

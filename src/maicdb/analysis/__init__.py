"""Analysis layer for MAIC-DB (P1 harmonization).

Reads the published artifact read-only; deterministic — same input tag,
same outputs. Authority chain: ``docs/analytics-pipeline-spec.md`` (scope)
→ ``docs/adr/0005-mimic-tri-state-hybrid.md`` (tri-state, applicability,
unit policy) → this package.

Scope seam vs ``maicdb.query``: the M1 query layer never inter-converts
within a modality (its "Modality separation" discipline). This package
converts row-level values to canonical units under ADR-0005's unit policy,
always preserving the as-reported pair alongside the converted value.

P1 modules:

* :mod:`maicdb.analysis.units` — canonical-unit conversions (mmHg / mN/m /
  µm pivots) with as-reported preservation.
* :mod:`maicdb.analysis.replicates` — coalesce of ``n_cells`` and the
  legacy text ``n`` column.
* :mod:`maicdb.analysis.activity` — pActivity derivation with micro-sign
  normalization and honest non-derivable bases.
* :mod:`maicdb.analysis.joins` — same-fit row discovery + deterministic
  narrowing (P50×slope split-row join, ADR-mandated).
"""

from maicdb.analysis.activity import PActivity, p_activity, to_molar
from maicdb.analysis.joins import (
    MarkerHit,
    SameFitCandidate,
    narrow_by_condition_key,
    same_fit_candidates,
    same_fit_marker_hits,
)
from maicdb.analysis.replicates import Replicates, coalesce_replicates, parse_n
from maicdb.analysis.units import (
    Converted,
    length_to_um,
    pressure_to_mmhg,
    tension_to_mnm,
)

__all__ = [
    "Converted",
    "MarkerHit",
    "PActivity",
    "Replicates",
    "SameFitCandidate",
    "coalesce_replicates",
    "length_to_um",
    "narrow_by_condition_key",
    "p_activity",
    "parse_n",
    "pressure_to_mmhg",
    "same_fit_candidates",
    "same_fit_marker_hits",
    "tension_to_mnm",
    "to_molar",
]

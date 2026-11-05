"""Per-record MIMIC compliance scoring (P2).

Authority: ADR-0005 (``docs/adr/0005-mimic-tri-state-hybrid.md`` —
tri-state semantics, applicability rules, unweighted score) and spec §5.1
(the audit track). Field vocabulary = the 19 MIMIC columns of vault
schema-design §4.3, grouped into the five README categories.

Semantics per field, per record (ADR-0005 tri-state):

* value present → ``reported``;
* listed in the record's ``mimic_gaps`` → ``not_reported`` (checked,
  absent in the paper);
* empty and not listed → ``not_extracted`` (ambiguous — must shrink).

The artifact at data-v1.0 carries no ``mimic_gaps`` column (its loader
home lands with data-v1.1), so every empty field scores
``not_extracted``; pass ``mimic_gaps`` per record once curation provides
it.

Score = reported ÷ applicable, unweighted (ADR-0005). Applicability is
strictly the ADR-0005 rule set — fields the ADR does not make conditional
are always applicable, including ``stimulus_waveform`` and
``stimulus_duration_ms``; a NULL ``stimulus_type``/``recording_mode``
excludes the dependent conditional fields (you cannot demand velocity for
an unknown stimulus), and ``OTHER`` recording modes are P3's per-record
call with disclosure (P2 defaults them to not-applicable).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

from sqlalchemy import text as sql_text
from sqlalchemy.engine import Engine

from maicdb.analysis.replicates import coalesce_replicates

__all__ = [
    "CATEGORIES",
    "MIMIC_FIELDS",
    "FieldStatus",
    "MIMICScore",
    "applicable_fields",
    "score_record",
    "score_all",
]

# Pipette-based recording modes (ADR-0005 applicability rule).
PIPETTE_MODES = frozenset(
    {
        "CELL_ATTACHED",
        "INSIDE_OUT",
        "OUTSIDE_OUT",
        "WHOLE_CELL",
        "PERFORATED_PATCH",
        "PLANAR_PATCH",
    }
)

# Named electrophysiological recording modes (ADR-0005 applicability rule).
EPHYS_MODES = PIPETTE_MODES | {"TEVC", "RECONSTITUTED_PROTEOLIPOSOME"}

# Stimuli whose protocols report an application velocity (ADR-0005).
MOVING_PROBE_STIMULI = frozenset({"INDENTATION", "TOUCH", "SHEAR_STRESS"})

CATEGORIES = ("stimulus", "recording", "cell_context", "environment", "analysis")

# field name -> (artifact column, category, needs replicate coalescing).
# ``n_cells`` is the vocabulary token (ADR-0005); its value coalesces from
# the ``n_cells`` INTEGER plus the legacy text ``n`` column.
MIMIC_FIELDS: dict[str, tuple[str, str, bool]] = {
    "stimulus_type": ("stimulus_type", "stimulus", False),
    "stimulus_waveform": ("stimulus_waveform", "stimulus", False),
    "stimulus_velocity": ("stimulus_velocity", "stimulus", False),
    "stimulus_duration_ms": ("stimulus_duration_ms", "stimulus", False),
    "probe_geometry": ("probe_geometry", "stimulus", False),
    "probe_diameter_um": ("probe_diameter_um", "stimulus", False),
    "recording_mode": ("recording_mode", "recording", False),
    "holding_potential_mv": ("holding_potential_mv", "recording", False),
    "sampling_rate_khz": ("sampling_rate_khz", "recording", False),
    "filter_khz": ("filter_khz", "recording", False),
    "expression_system": ("expression_system", "cell_context", False),
    "cell_type": ("cell_type", "cell_context", False),
    "temperature_c": ("temperature_c", "environment", False),
    "ph": ("ph", "environment", False),
    "bath_solution": ("bath_solution", "environment", False),
    "pipette_solution": ("pipette_solution", "environment", False),
    "n_cells": ("n", "analysis", True),
    "analysis_method": ("analysis_method", "analysis", False),
    "protocol_ref": ("protocol_ref", "analysis", False),
}

_ALWAYS_APPLICABLE = frozenset(MIMIC_FIELDS) - {
    "stimulus_velocity",
    "probe_geometry",
    "probe_diameter_um",
    "pipette_solution",
    "holding_potential_mv",
    "sampling_rate_khz",
    "filter_khz",
}

_SELECT_SQL = sql_text(
    "SELECT * FROM biophysics_experiment ORDER BY maicdb_id"
)


def field_value(record: Mapping[str, object], field_name: str) -> object:
    """The harmonized value of a MIMIC field from a record mapping.

    ``n_cells`` coalesces from ``n_cells`` INTEGER + legacy text ``n``
    (ADR-0005); a parsed integer OR range counts as present.
    """
    column, _, coalesce = MIMIC_FIELDS[field_name]
    if coalesce:
        rep = coalesce_replicates(
            record.get("n_cells"),  # type: ignore[arg-type]
            record.get("n"),  # type: ignore[arg-type]
        )
        return None if rep.value is None and rep.low is None else rep
    return record.get(column)


def applicable_fields(record: Mapping[str, object]) -> dict[str, bool]:
    """ADR-0005 applicability for each of the 19 fields on one record."""
    stim = record.get("stimulus_type")
    mode = record.get("recording_mode")
    out = {name: True for name in _ALWAYS_APPLICABLE}
    out["stimulus_velocity"] = stim in MOVING_PROBE_STIMULI
    out["probe_geometry"] = stim == "INDENTATION"
    out["probe_diameter_um"] = stim == "INDENTATION"
    out["pipette_solution"] = mode in PIPETTE_MODES
    out["holding_potential_mv"] = mode in PIPETTE_MODES
    out["sampling_rate_khz"] = mode in EPHYS_MODES
    out["filter_khz"] = mode in EPHYS_MODES
    return out


@dataclass(frozen=True)
class FieldStatus:
    """One field's tri-state status and applicability on one record."""

    field_name: str
    category: str
    applicable: bool
    status: str  # "reported" | "not_reported" | "not_extracted" | "not_applicable"


@dataclass(frozen=True)
class MIMICScore:
    """The compliance verdict for one experiment record."""

    maicdb_id: str
    channel_id: int
    score: float  # reported / applicable, unweighted (ADR-0005)
    reported: int
    applicable: int
    fields: dict[str, FieldStatus] = field(default_factory=dict)
    categories: dict[str, tuple[int, int]] = field(default_factory=dict)  # (reported, applicable)

    def to_dict(self) -> dict[str, object]:
        """JSON-able form for the site's channel-card badge (P7 consumer)."""
        return {
            "maicdb_id": self.maicdb_id,
            "channel_id": self.channel_id,
            "score": round(self.score, 4),
            "reported": self.reported,
            "applicable": self.applicable,
            "categories": {k: list(v) for k, v in self.categories.items()},
            "fields": {
                name: {
                    "category": st.category,
                    "status": st.status,
                    "applicable": st.applicable,
                }
                for name, st in self.fields.items()
            },
        }


def score_record(
    record: Mapping[str, object],
    mimic_gaps: Collection[str] | None = None,
) -> MIMICScore:
    """Score one experiment record (tri-state; ADR-0005)."""
    gaps = set(mimic_gaps) if mimic_gaps else set()
    applicability = applicable_fields(record)
    fields: dict[str, FieldStatus] = {}
    cat_rep: dict[str, int] = dict.fromkeys(CATEGORIES, 0)
    cat_app: dict[str, int] = dict.fromkeys(CATEGORIES, 0)
    for name, (column, category, _co) in MIMIC_FIELDS.items():
        applicable = applicability[name]
        if not applicable:
            status = "not_applicable"
        elif field_value(record, name) is not None:
            status = "reported"
        elif name in gaps:
            status = "not_reported"
        else:
            status = "not_extracted"
        fields[name] = FieldStatus(name, category, applicable, status)
        if applicable:
            cat_app[category] += 1
            if status == "reported":
                cat_rep[category] += 1
    reported = sum(cat_rep.values())
    total = sum(cat_app.values())
    score = reported / total if total else 0.0
    return MIMICScore(
        maicdb_id=str(record.get("maicdb_id", "")),
        channel_id=int(record.get("channel_id", 0)),
        score=score,
        reported=reported,
        applicable=total,
        fields=fields,
        categories={c: (cat_rep[c], cat_app[c]) for c in CATEGORIES},
    )


def score_all(engine: Engine) -> list[MIMICScore]:
    """Score every biophysics_experiment row, deterministic order.

    data-v1.0 caveat: no ``mimic_gaps`` column exists in the artifact, so
    empty fields score ``not_extracted`` (ADR-0005 hybrid — the column
    activates with future curation batches).
    """
    out: list[MIMICScore] = []
    with engine.connect() as conn:
        for row in conn.execute(_SELECT_SQL).mappings():
            out.append(score_record(dict(row)))
    return out

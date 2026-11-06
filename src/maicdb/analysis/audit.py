"""MIMIC compliance audit analyses (P3, Track A).

Authority: spec §5.1 (the audit track's views) on top of ADR-0005
tri-state scoring (``maicdb.analysis.mimic``). Every aggregate is
descriptive (spec §6: the audit track runs no hypothesis tests at v1);
every table-shaped output carries k/n counts.

Views implemented (spec §5.1):

* completeness heatmap — field × family, tri-state cells (counts);
* compliance vs publication year with the pre/post-PIEZO era contrast
  (boundary 2010: Coste et al., Science 2010, PIEZO1/2 cloning);
* breakdowns by journal, recording_mode, stimulus_type, family —
  "assay format" has no dedicated column; recording_mode is its data
  proxy (disclosed simplification, spec §6's no-pooling rule reads the
  pair recording_mode × stimulus_type);
* the vault §9 four-field enforcement headline, under BOTH readings:
  as-written (applicability ignored — the vault list's own reading,
  which fails ~100% of data-v1.0) and ADR-aware (applicability-filtered).
  Stating the pair is the paper's motivation figure (spec §5.1).

Mean conventions, disclosed: heatmap cells are count ratios
(reported ÷ applicable in the cell); the year/era and breakdown views
report the mean of per-record scores (spec §5.1 defines the score
per experiment). The weighted sensitivity analysis re-weights the five
MIMIC categories within each record (unweighted stays the headline).

Category weighting and grouping keys are validated; outputs are
deterministic (sorted keys; records consumed in ``score_all`` order).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text as sql_text
from sqlalchemy.engine import Engine

from maicdb.analysis.mimic import (
    CATEGORIES,
    MIMICScore,
    applicable_fields,
    field_value,
)

__all__ = [
    "PIEZO_YEAR",
    "MANDATED_FIELDS",
    "CONTEXT_FIELDS",
    "BREAKDOWN_KEYS",
    "RecordMeta",
    "HeatmapCell",
    "YearCompliance",
    "EraContrast",
    "GroupCompliance",
    "FieldEnforcement",
    "EnforcementAudit",
    "load_meta",
    "load_families",
    "heatmap",
    "field_totals",
    "compliance_by_year",
    "breakdown",
    "weighted_score",
    "category_weighted_mean",
    "four_field_audit",
]

# Era boundary: Coste et al., Science 2010 (PIEZO1/PIEZO2 cloning). A
# record whose publication year is < 2010 is "pre"; >= 2010 is "post".
PIEZO_YEAR = 2010

# Vault schema-design §9 "MIMIC enforcement (loader)": the four mandated
# fields. "Experimental context (cell type, temperature)" is one mandated
# item naming two columns; the strict reading — BOTH must be present —
# is what an insert-time validator would enforce, so the audit counts a
# record as context-complete only when cell_type AND temperature_c are
# both populated.
MANDATED_FIELDS = (
    "stimulus_velocity",
    "probe_geometry",
    "recording_mode",
    "experimental_context",
)
CONTEXT_FIELDS = ("cell_type", "temperature_c")

BREAKDOWN_KEYS = ("family", "journal", "recording_mode", "stimulus_type")

_META_SQL = sql_text(
    "SELECT e.maicdb_id AS maicdb_id, c.family AS family, p.year AS year,"
    " p.journal AS journal, e.recording_mode AS recording_mode,"
    " e.stimulus_type AS stimulus_type"
    " FROM biophysics_experiment e"
    " LEFT JOIN channel c ON e.channel_id = c.id"
    " LEFT JOIN publication p ON e.publication_id = p.id"
    " ORDER BY e.maicdb_id"
)

_FAMILIES_SQL = sql_text("SELECT id, family FROM channel ORDER BY id")


@dataclass(frozen=True)
class RecordMeta:
    """Grouping keys for one experiment (spec §5.1's breakdown views)."""

    family: str | None
    year: int | None
    journal: str | None
    recording_mode: str | None
    stimulus_type: str | None


def load_meta(engine: Engine) -> dict[str, RecordMeta]:
    """Load grouping keys for every experiment, keyed by maicdb_id.

    Deterministic order; LEFT JOINs so partial metadata still yields a
    row (None keys) — coverage is pinned by the artifact tests.
    """
    out: dict[str, RecordMeta] = {}
    with engine.connect() as conn:
        for row in conn.execute(_META_SQL).mappings():
            out[str(row["maicdb_id"])] = RecordMeta(
                family=row["family"],
                year=row["year"],
                journal=row["journal"],
                recording_mode=row["recording_mode"],
                stimulus_type=row["stimulus_type"],
            )
    return out


def load_families(engine: Engine) -> dict[int, str | None]:
    """channel_id → family name, the heatmap's slice key (``heatmap``).

    Deterministic order; a None family (non-enum value) still yields a
    key so ``heatmap`` routes the record to its reserved ``"?"`` slice.
    """
    out: dict[int, str | None] = {}
    with engine.connect() as conn:
        for row in conn.execute(_FAMILIES_SQL).mappings():
            out[int(row["id"])] = row["family"]
    return out


# --- completeness heatmap (field × family, tri-state counts) ------------


@dataclass(frozen=True)
class HeatmapCell:
    """Tri-state counts for one field in one slice (family or overall).

    ``compliance`` is the count ratio reported ÷ applicable — ``None``
    when the field is inapplicable to the whole slice (renderers show
    "n/a", not 0.0).
    """

    reported: int
    not_reported: int
    not_extracted: int
    applicable: int

    @property
    def compliance(self) -> float | None:
        if self.applicable == 0:
            return None
        return self.reported / self.applicable


def _bump(cell: list[int], status: str, applicable: bool) -> None:
    """Accumulate one field status into ``[reported, not_reported,
    not_extracted, applicable]`` (in place)."""
    if applicable:
        cell[3] += 1
        if status == "reported":
            cell[0] += 1
        elif status == "not_reported":
            cell[1] += 1
        else:  # not_extracted — the ambiguity ADR-0005 demands we shrink
            cell[2] += 1


def _cell(acc: list[int]) -> HeatmapCell:
    rep, nrep, nex, app = acc
    return HeatmapCell(rep, nrep, nex, app)


def heatmap(
    scores: Iterable[MIMICScore],
    families: Mapping[int, str | None],
) -> dict[str, dict[str, HeatmapCell]]:
    """Field × family tri-state counts.

    ``families`` maps channel_id → family name (``load_meta``'s family
    column keyed differently — the artifact loader assembles it).
    Records whose channel has no family are counted under the reserved
    slice ``"?"``; no slice is dropped. Family slices are sorted.
    """
    acc: dict[str, dict[str, list[int]]] = {}
    for score in scores:
        family = families.get(score.channel_id) or "?"
        per_family = acc.setdefault(family, {})
        for name, st in score.fields.items():
            cell = per_family.setdefault(name, [0, 0, 0, 0])
            _bump(cell, st.status, st.applicable)
    return {
        family: {name: _cell(c) for name, c in sorted(fields.items())}
        for family, fields in sorted(acc.items())
    }


def field_totals(scores: Iterable[MIMICScore]) -> dict[str, HeatmapCell]:
    """Overall tri-state counts per field, family axis collapsed.

    For an always-applicable field this is the populated share of the
    corpus (spec §3's census table); for conditional fields the
    denominator is the applicable set (ADR-0005).
    """
    acc: dict[str, list[int]] = {}
    for score in scores:
        for name, st in score.fields.items():
            cell = acc.setdefault(name, [0, 0, 0, 0])
            _bump(cell, st.status, st.applicable)
    return {name: _cell(c) for name, c in sorted(acc.items())}


# --- compliance vs publication year, pre/post-PIEZO eras ---------------


@dataclass(frozen=True)
class YearCompliance:
    """Mean per-record compliance in one publication year."""

    year: int
    k: int  # records (guardrails: every table carries k)
    mean: float


@dataclass(frozen=True)
class EraContrast:
    """Per-year series plus the pre/post-PIEZO era summary."""

    years: list[YearCompliance]  # sorted by year
    pre_k: int
    pre_mean: float
    post_k: int
    post_mean: float
    unassigned_k: int  # records with no year (excluded from both eras)


def compliance_by_year(
    scores: Iterable[MIMICScore],
    years: Mapping[str, int | None],
    piezo_year: int = PIEZO_YEAR,
) -> EraContrast:
    """Mean per-record compliance by publication year and era.

    Era: year < ``piezo_year`` is pre, >= is post (2010 = the PIEZO
    cloning paper). Records without a year are counted in
    ``unassigned_k`` and excluded from both eras and the year series.
    """
    by_year: dict[int, list[float]] = {}
    pre: list[float] = []
    post: list[float] = []
    unassigned = 0
    for score in scores:
        year = years.get(score.maicdb_id)
        if year is None:
            unassigned += 1
            continue
        by_year.setdefault(year, []).append(score.score)
        (pre if year < piezo_year else post).append(score.score)
    year_rows = [
        YearCompliance(year=y, k=len(v), mean=sum(v) / len(v))
        for y, v in sorted(by_year.items())
    ]
    return EraContrast(
        years=year_rows,
        pre_k=len(pre),
        pre_mean=sum(pre) / len(pre) if pre else 0.0,
        post_k=len(post),
        post_mean=sum(post) / len(post) if post else 0.0,
        unassigned_k=unassigned,
    )


# --- breakdowns (journal / recording_mode / stimulus_type / family) ----


@dataclass(frozen=True)
class GroupCompliance:
    """Mean per-record compliance in one group, with k."""

    group: str
    k: int
    mean: float


def breakdown(
    scores: Iterable[MIMICScore],
    meta: Mapping[str, RecordMeta],
    key: str,
) -> list[GroupCompliance]:
    """Group mean compliance by one of ``BREAKDOWN_KEYS``.

    Records whose key value is missing (None or empty) are dropped —
    the artifact tests cross-foot the retained k against the coverage
    census so a silent coverage change cannot hide behind this view.
    Groups sort by name; empty keys yield ValueError.
    """
    if key not in BREAKDOWN_KEYS:
        raise ValueError(f"key must be one of {BREAKDOWN_KEYS}, got {key!r}")
    acc: dict[str, list[float]] = {}
    for score in scores:
        m = meta.get(score.maicdb_id)
        value = getattr(m, key) if m is not None else None
        if value is None or value == "":
            continue
        acc.setdefault(str(value), []).append(score.score)
    return [
        GroupCompliance(group=g, k=len(v), mean=sum(v) / len(v))
        for g, v in sorted(acc.items())
    ]


# --- weighted sensitivity analysis (category weights) -------------------


def weighted_score(score: MIMICScore, weights: Mapping[str, float]) -> float:
    """Category-weighted per-record compliance (spec §5.1 sensitivity).

    ``Σ_c w_c · reported_c ÷ Σ_c w_c · applicable_c`` over the five
    MIMIC categories; all-ones weights reproduce the unweighted score.
    Weights must be positive and their keys a subset of ``CATEGORIES``;
    an empty mapping raises. The denominator is positive for any
    non-empty weight set (every category has ≥1 always-applicable field).
    """
    if not weights:
        raise ValueError("weights must be a non-empty mapping")
    unknown = set(weights) - set(CATEGORIES)
    if unknown:
        raise ValueError(f"unknown categories: {sorted(unknown)}")
    for cat, w in weights.items():
        if w <= 0:
            raise ValueError(f"weight for {cat!r} must be positive, got {w}")
    num = 0.0
    den = 0.0
    for cat, rep_app in score.categories.items():
        w = weights.get(cat, 0.0)
        rep, app = rep_app
        num += w * rep
        den += w * app
    return num / den if den else 0.0


def category_weighted_mean(
    scores: Iterable[MIMICScore], weights: Mapping[str, float]
) -> float:
    """Mean ``weighted_score`` over records (unweighted ≡ plain mean)."""
    vals = [weighted_score(s, weights) for s in scores]
    return sum(vals) / len(vals) if vals else 0.0


# --- vault §9 four-field enforcement headline ---------------------------


@dataclass(frozen=True)
class FieldEnforcement:
    """One mandated field's failure counts under both readings."""

    field_name: str
    total: int
    missing_as_written: int  # value absent, applicability ignored (vault §9)
    applicable: int  # ADR-0005 applicable set
    missing_when_applicable: int

    @property
    def as_written_fail_rate(self) -> float:
        return self.missing_as_written / self.total if self.total else 0.0

    @property
    def adr_fail_rate(self) -> float | None:
        if self.applicable == 0:
            return None
        return self.missing_when_applicable / self.applicable


@dataclass(frozen=True)
class EnforcementAudit:
    """The §9 headline: per-field rows plus any-field failure counts."""

    fields: dict[str, FieldEnforcement]
    failing_any_as_written: tuple[int, int]  # (failures, total)
    failing_any_adr: tuple[int, int]


def four_field_audit(
    records: list[Mapping[str, object]],
) -> EnforcementAudit:
    """Enforcement failure rates for the vault §9 four-field list.

    Two readings of the same list, both reported (spec §5.1: "State
    both numbers"):

    * *as written* — the vault list's own reading, applicability
      ignored: a record fails a mandated field when its value is
      absent. This is the ~100% motivation number: velocity and probe
      geometry are 0% populated corpus-wide, so as-written every
      data-v1.0 record fails the list.
    * *ADR-aware* — a record fails only when the field is applicable
      (ADR-0005 rules) AND absent; a NULL stimulus_type/recording_mode
      excludes the dependent fields (one cannot demand velocity for an
      unknown stimulus), so such records cannot fail them. The naive
      SQL complement of the as-written form is NULL-poisoned and
      undercounts the clean set — the artifact test pins the NULL-safe
      CASE-form census instead.

    Context is the strict conjunction over ``CONTEXT_FIELDS`` (docstring
    of ``MANDATED_FIELDS``). Records are consumed in list order;
    per-field counts do not depend on order.
    """
    per_field: dict[str, tuple[int, int, int, int]] = {
        name: (0, 0, 0, 0) for name in MANDATED_FIELDS
    }  # total, as_written_missing, applicable, missing_when_applicable
    fail_any_written = 0
    fail_any_adr = 0
    # Only velocity and geometry are conditional (ADR-0005); recording
    # mode and context are always applicable.
    conditional = ("stimulus_velocity", "probe_geometry")
    for record in records:
        applicability = applicable_fields(record)
        missed_written = False
        missed_adr = False
        for name in MANDATED_FIELDS:
            columns = CONTEXT_FIELDS if name == "experimental_context" else (name,)
            missing = any(field_value(record, c) is None for c in columns)
            total, mw, app, ma = per_field[name]
            total += 1
            if missing:
                mw += 1
                missed_written = True
            if name in conditional:
                applicable = applicability[name]
            else:
                applicable = True
            if applicable:
                app += 1
                if missing:
                    ma += 1
                    missed_adr = True
            per_field[name] = (total, mw, app, ma)
        if missed_written:
            fail_any_written += 1
        if missed_adr:
            fail_any_adr += 1
    n = len(records)
    rows = {
        name: FieldEnforcement(
            field_name=name,
            total=t,
            missing_as_written=mw,
            applicable=app,
            missing_when_applicable=ma,
        )
        for name, (t, mw, app, ma) in per_field.items()
    }
    return EnforcementAudit(
        fields=rows,
        failing_any_as_written=(fail_any_written, n),
        failing_any_adr=(fail_any_adr, n),
    )

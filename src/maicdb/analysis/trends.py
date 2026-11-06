"""Field-trend analyses (P6, Track D).

Authority: spec §5.4 — "Publications per year by family; which
parameters the field measured over time; assay-format and model-system
drift. Descriptive counts only." Needs P1's loaders only, not the P2
scoring (spec §4: "P6 needs P1 only — no per-record scoring"); this
module reads the frozen artifact's own columns directly.

Three views, all descriptive counts (spec §6: every table carries k;
the audit guardrail against hypothesis tests applies a fortiori here):

* publications per year — per (year, family) distinct-publication
  counts via the experiment join, plus the overall per-year distinct
  count. The two are NOT additive in general (one publication can cover
  two families in one year); at data-v1.0 they coincide (both 184 rows
  — census-pinned), which is itself a fact about the corpus, not a
  license to sum later.
* parameter adoption — full year × parameter cross-tab of
  ``biophysics_experiment`` value columns (k may be 0); "which
  parameters the field measured over time".
* assay-format drift — year × recording_mode counts (NULL modes as a
  None-keyed row: completeness is part of the trend);
  model-system drift — year × expression_system, SPARSE (only observed
  combinations; the column is free text with 224 distinct values at
  data-v1.0 — a full cross-tab would be ~7k mostly-zero rows and the
  rendering truncation belongs to P7).

Outputs are deterministic: sorted keys everywhere, ``PARAMETERS`` fixed
order, records consumed in loader order (``ORDER BY maicdb_id``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text as sql_text
from sqlalchemy.engine import Engine

__all__ = [
    "PARAMETERS",
    "TrendRecord",
    "PubYearRow",
    "ParamYearRow",
    "ModeYearRow",
    "ExprYearRow",
    "load_trend_records",
    "pubs_per_year_by_family",
    "pubs_per_year_total",
    "parameter_adoption",
    "assay_drift",
    "model_system_drift",
]

# The parameter vocabulary: biophysics_experiment value columns, in
# schema order. Presence = column IS NOT NULL (spec §3's census counts;
# text/enum columns count the same way — no empty strings exist at
# data-v1.0, census-pinned in the artifact tests).
PARAMETERS: tuple[tuple[str, str], ...] = (
    ("p50_value", "p50"),
    ("t50_value", "t50"),
    ("x50_value", "x50"),
    ("slope", "slope"),
    ("tau_act_ms", "tau_act"),
    ("tau_inact_ms", "tau_inact"),
    ("tau_deact_ms", "tau_deact"),
    ("conductance_ps", "conductance"),
    ("reversal_potential_mv", "reversal_potential"),
    ("iv_relation", "iv_relation"),
    ("delta_p50_value", "delta_p50"),
    ("ion_selectivity_ratio", "ion_selectivity"),
    ("ca_permeability", "ca_permeability"),
    ("threshold_fold_shift_value", "threshold_fold_shift"),
    ("macroscopic_rise_time_ms", "rise_time"),
    ("thermal_threshold_c", "thermal_threshold"),
    ("osmotic_threshold_value", "osmotic_threshold"),
)

_TREND_SQL = sql_text(
    "SELECT e.maicdb_id AS maicdb_id, e.channel_id AS channel_id,"
    " c.family AS family, p.year AS year, e.publication_id AS publication_id,"
    " e.recording_mode AS recording_mode,"
    " e.expression_system AS expression_system,"
    + ", ".join(f"e.{col} AS {col}" for col, _ in PARAMETERS)
    + " FROM biophysics_experiment e"
    " LEFT JOIN channel c ON e.channel_id = c.id"
    " LEFT JOIN publication p ON e.publication_id = p.id"
    " ORDER BY e.maicdb_id"
)


@dataclass(frozen=True)
class TrendRecord:
    """One experiment's trend-relevant projection (spec §5.4's inputs).

    ``parameters`` carries the set of present parameter labels (see
    ``PARAMETERS``); values are out of scope here — Track D counts
    measurements, it does not analyze them (that is Track B, P4).
    """

    maicdb_id: str
    channel_id: int
    family: str | None
    year: int | None
    publication_id: int | None
    recording_mode: str | None
    expression_system: str | None
    parameters: frozenset[str]


def load_trend_records(engine: Engine) -> list[TrendRecord]:
    """Load every experiment's trend projection, deterministic order."""
    out: list[TrendRecord] = []
    with engine.connect() as conn:
        for row in conn.execute(_TREND_SQL).mappings():
            present = frozenset(
                label
                for (_, label), value in zip(
                    PARAMETERS,
                    (row[col] for col, _ in PARAMETERS),
                )
                if value is not None
            )
            out.append(
                TrendRecord(
                    maicdb_id=str(row["maicdb_id"]),
                    channel_id=int(row["channel_id"]),
                    family=row["family"],
                    year=row["year"],
                    publication_id=row["publication_id"],
                    recording_mode=row["recording_mode"],
                    expression_system=row["expression_system"],
                    parameters=present,
                )
            )
    return out


# --- publications per year ----------------------------------------------


@dataclass(frozen=True)
class PubYearRow:
    """Distinct publications in one (year, family) cell."""

    year: int
    family: str
    k: int  # distinct publication_id values


def pubs_per_year_by_family(
    records: Sequence[TrendRecord],
) -> list[PubYearRow]:
    """Distinct publications per (year, family), sorted.

    Records without a family or year are excluded from this view (the
    coverage censuses pin both to 948/948 at data-v1.0, so nothing is
    dropped in practice); a record with a NULL publication_id cannot
    contribute (nothing to count).
    """
    cells: dict[tuple[int, str], set[int]] = {}
    for r in records:
        if r.year is None or r.family is None or r.publication_id is None:
            continue
        cells.setdefault((r.year, r.family), set()).add(r.publication_id)
    return [
        PubYearRow(year=y, family=f, k=len(pubs))
        for (y, f), pubs in sorted(cells.items())
    ]


@dataclass(frozen=True)
class PubYearTotal:
    """Distinct publications in one year, family axis collapsed."""

    year: int
    k: int


def pubs_per_year_total(
    records: Sequence[TrendRecord],
) -> list[PubYearTotal]:
    """Distinct publications per year overall (NOT the row sums of
    ``pubs_per_year_by_family`` — one publication covering two families
    in one year would double-count; at data-v1.0 the two coincide,
    census-pinned)."""
    cells: dict[int, set[int]] = {}
    for r in records:
        if r.year is None or r.publication_id is None:
            continue
        cells.setdefault(r.year, set()).add(r.publication_id)
    return [PubYearTotal(year=y, k=len(pubs)) for y, pubs in sorted(cells.items())]


# --- parameter adoption over time ---------------------------------------


@dataclass(frozen=True)
class ParamYearRow:
    """Experiments measuring one parameter in one year (full cross-tab).

    ``of_year`` is that year's total experiment count, so a renderer
    can show the adoption share; ``k`` may be 0.
    """

    year: int
    parameter: str
    k: int
    of_year: int


def parameter_adoption(
    records: Sequence[TrendRecord],
) -> list[ParamYearRow]:
    """Year × parameter presence counts, full cross-tab (k may be 0).

    Rows for every year present in the data and every ``PARAMETERS``
    entry, sorted by year then fixed parameter order — a stable grid a
    site page can plot without sparse handling.
    """
    years = sorted({r.year for r in records if r.year is not None})
    per_year_k: dict[int, int] = {y: 0 for y in years}
    counts: dict[tuple[int, str], int] = {}
    for r in records:
        if r.year is None:
            continue
        per_year_k[r.year] += 1
        for label in r.parameters:
            counts[(r.year, label)] = counts.get((r.year, label), 0) + 1
    return [
        ParamYearRow(
            year=y,
            parameter=label,
            k=counts.get((y, label), 0),
            of_year=per_year_k[y],
        )
        for y in years
        for _, label in PARAMETERS
    ]


# --- assay-format and model-system drift --------------------------------


@dataclass(frozen=True)
class ModeYearRow:
    """Experiments in one recording_mode in one year (full cross-tab).

    ``recording_mode`` is None for records with no mode (39 at
    data-v1.0) — the completeness trend is part of the drift story.
    """

    year: int
    recording_mode: str | None
    k: int


def assay_drift(records: Sequence[TrendRecord]) -> list[ModeYearRow]:
    """Year × recording_mode counts, full cross-tab over the modes
    observed anywhere in the corpus (plus the None bucket if any record
    has no mode), sorted by year then mode name (None first)."""
    years = sorted({r.year for r in records if r.year is not None})
    modes = sorted({r.recording_mode for r in records}, key=lambda m: (m is not None, m or ""))
    cells: dict[tuple[int, str | None], int] = {}
    for r in records:
        if r.year is None:
            continue
        cells[(r.year, r.recording_mode)] = cells.get((r.year, r.recording_mode), 0) + 1
    return [
        ModeYearRow(year=y, recording_mode=m, k=cells.get((y, m), 0))
        for y in years
        for m in modes
    ]


@dataclass(frozen=True)
class ExprYearRow:
    """Experiments in one expression_system in one year (SPARSE).

    Only observed (year, system) combinations appear — the column is
    free text (224 distinct values at data-v1.0) and a full cross-tab
    would be mostly zeros. Sorted by year then system name (None first).
    """

    year: int
    expression_system: str | None
    k: int


def model_system_drift(records: Sequence[TrendRecord]) -> list[ExprYearRow]:
    """Year × expression_system counts, SPARSE (observed combos only)."""
    cells: dict[tuple[int, str | None], int] = {}
    for r in records:
        if r.year is None:
            continue
        cells[(r.year, r.expression_system)] = (
            cells.get((r.year, r.expression_system), 0) + 1
        )
    return [
        ExprYearRow(year=y, expression_system=s, k=k)
        for (y, s), k in sorted(
            cells.items(), key=lambda kv: (kv[0][0], kv[0][1] is not None, kv[0][1] or "")
        )
    ]

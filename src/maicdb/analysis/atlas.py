"""Variant and compound atlas (P5, Track C).

Authority: spec §5.3 — the ΔP50 effect-size table (variant →
functional_effect → ΔP50 normalized, mapped to structural domains
where the variant position falls inside a covered structure; no
inferential statistics at this n) and the compound × channel matrix
(pActivity heatmap, per-compound selectivity index, honest about
sparsity — cells show "no data" rather than zeros). Values reuse P1's
``p_activity`` (−log10 molar; ADR-0005 unit policy) — no new
dependencies (spec: P5 needs none).

data-v1.0 reality, disclosed (artifact-census-pinned):

* ``structure.residues_covered`` / ``coverage_pct`` are NULL on all 12
  structure rows, so the ΔP50 → structural-domain mapping is VACUOUS
  at this tag — the mapping code is implemented generally (a variant
  position inside a covered range maps to that structure) and the
  artifact test pins today's zero mappings; future curation activates
  it. This is the same "defines the curation demand" pattern as the
  spec's own tension-conversion note (§5.2).
* Only 2 of the 3 variant-linked ΔP50 rows carry a variant position.
* ``bioactivity.pchembl`` is NULL on all 136 rows — ``p_activity`` on
  (activity_value, activity_units) is the only value axis.
* The matrix is sparse by construction: 73 populated compound ×
  channel cells of 69 × 9 = 621 possible (~12%); a pair with several
  measurements aggregates to the MEAN of its pActivities (n carried
  per cell).

Selectivity index (disclosed definition): per compound with populated
pActivity values on ≥2 distinct channels, best-channel pActivity minus
best off-target pActivity (the second-best). Single-channel compounds
have no measurable off-target gap → None.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field as dataclass_field

from sqlalchemy import text as sql_text
from sqlalchemy.engine import Engine

from maicdb.analysis.activity import p_activity

__all__ = [
    "EffectRow",
    "MatrixCell",
    "SelectivityRow",
    "delta_p50_table",
    "compound_channel_matrix",
    "selectivity_index",
]

_DP50_SQL = sql_text(
    "SELECT e.maicdb_id AS maicdb_id, e.channel_id AS channel_id,"
    " c.gene_symbol AS gene_symbol,"
    " c.family AS family, e.delta_p50_value AS delta_p50_value,"
    " e.delta_p50_unit AS delta_p50_unit, e.publication_id AS publication_id,"
    " e.variant_id AS variant_id, v.hgvs_protein AS hgvs_protein,"
    " v.position AS position, v.functional_effect AS functional_effect"
    " FROM biophysics_experiment e"
    " JOIN channel c ON e.channel_id = c.id"
    " LEFT JOIN variant v ON e.variant_id = v.id"
    " WHERE e.delta_p50_value IS NOT NULL"
    " ORDER BY e.maicdb_id"
)

_COVERED_SQL = sql_text(
    "SELECT s.id AS structure_id, s.pdb_id AS pdb_id,"
    " s.channel_id AS channel_id, s.residues_covered AS residues_covered"
    " FROM structure s WHERE s.residues_covered IS NOT NULL"
)

_MATRIX_SQL = sql_text(
    "SELECT b.maicdb_id AS maicdb_id, cp.name AS compound_name,"
    " c.gene_symbol AS gene_symbol, c.family AS family,"
    " b.activity_value AS activity_value, b.activity_units AS activity_units"
    " FROM bioactivity b"
    " JOIN compound cp ON b.compound_id = cp.id"
    " JOIN channel c ON b.channel_id = c.id"
    " ORDER BY cp.name, c.gene_symbol, b.maicdb_id"
)


def _in_covered_range(position: int, residues_covered: str) -> bool:
    """True when ``position`` falls inside a coverage spec like
    ``"1-2547"`` or ``"1-200, 300-500"`` (ranges inclusive; bare
    numbers treated as single residues). Malformed segments are
    skipped — coverage text is curated free text."""
    for segment in residues_covered.split(","):
        part = segment.strip()
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-", 1)
            try:
                lo, hi = int(bounds[0]), int(bounds[1])
            except ValueError:
                continue
            if lo <= position <= hi:
                return True
        else:
            try:
                if int(part) == position:
                    return True
            except ValueError:
                continue
    return False


@dataclass(frozen=True)
class EffectRow:
    """One ΔP50 effect-size row (spec: no inferential statistics)."""

    maicdb_id: str
    gene_symbol: str
    family: str
    delta_p50: float  # as reported (all data-v1.0 rows are mmHg)
    unit: str  # as reported
    variant_linked: bool  # the row cites a variant (e.at data-v1.0 the
    # 3 linked rows carry NULL hgvs_protein — linkage without notation)
    variant: str | None  # hgvs_protein (None on all data-v1.0 rows)
    functional_effect: str | None
    variant_position: int | None
    domains: tuple[str, ...]  # structures covering the variant position
    # (empty at data-v1.0 — residues_covered is NULL on all 12
    # structure rows; the mapping activates with future curation)


def delta_p50_table(engine: Engine) -> list[EffectRow]:
    """The ΔP50 effect-size table, deterministic order; structural
    domains resolved where a variant position falls inside a covered
    structure's range (vacuous at data-v1.0 — see module docstring)."""
    covered = {}
    with engine.connect() as conn:
        for row in conn.execute(_COVERED_SQL).mappings():
            covered.setdefault(int(row["channel_id"]), []).append(row)
        out: list[EffectRow] = []
        for row in conn.execute(_DP50_SQL).mappings():
            position = row["position"]
            domains: list[str] = []
            if position is not None:
                channel_id = row["channel_id"]
                for s in covered.get(int(channel_id) if channel_id is not None else -1, []):
                    if _in_covered_range(int(position), s["residues_covered"] or ""):
                        domains.append(str(s["pdb_id"] or s["structure_id"]))
            out.append(
                EffectRow(
                    maicdb_id=str(row["maicdb_id"]),
                    gene_symbol=str(row["gene_symbol"]),
                    family=str(row["family"]),
                    delta_p50=float(row["delta_p50_value"]),
                    unit=row["delta_p50_unit"] or "",
                    variant_linked=row["variant_id"] is not None,
                variant=row["hgvs_protein"],
                    functional_effect=row["functional_effect"],
                    variant_position=position,
                    domains=tuple(domains),
                )
            )
    return out


@dataclass(frozen=True)
class MatrixCell:
    """One compound × channel cell of the activity matrix.

    ``pactivity`` is None when no measurement of the pair resolved to
    a pActivity (e.g. mass-concentration rows without MW) — the cell
    EXISTS (measurements do) but carries no value: "no data" ≠ zero.
    """

    compound_name: str
    gene_symbol: str
    family: str
    k: int  # measurements behind the cell
    pactivity: float | None  # mean of resolved pActivities
    basis_counts: tuple[tuple[str, int], ...]  # sorted (basis, n)


@dataclass
class _CellAcc:
    """Mutable accumulator behind one matrix cell."""

    family: str
    n: int = 0
    p_sum: float = 0.0
    p_n: int = 0
    basis: dict[str, int] = dataclass_field(default_factory=dict)


def compound_channel_matrix(engine: Engine) -> list[MatrixCell]:
    """The compound × channel activity matrix, sparse (populated cells
    only), deterministic order (compound, then gene)."""
    groups: dict[tuple[str, str], _CellAcc] = {}
    with engine.connect() as conn:
        for row in conn.execute(_MATRIX_SQL).mappings():
            key = (str(row["compound_name"]), str(row["gene_symbol"]))
            cell = groups.setdefault(key, _CellAcc(family=str(row["family"])))
            cell.n += 1
            act = p_activity(row["activity_value"], row["activity_units"] or "")
            cell.basis[act.basis] = cell.basis.get(act.basis, 0) + 1
            if act.value is not None:
                cell.p_sum += act.value
                cell.p_n += 1
    out: list[MatrixCell] = []
    for (compound, gene), cell in sorted(groups.items()):
        out.append(
            MatrixCell(
                compound_name=compound,
                gene_symbol=gene,
                family=cell.family,
                k=cell.n,
                pactivity=(cell.p_sum / cell.p_n) if cell.p_n else None,
                basis_counts=tuple(sorted(cell.basis.items())),
            )
        )
    return out


@dataclass(frozen=True)
class SelectivityRow:
    """Per-compound selectivity: best-channel pActivity minus best
    off-target (second-best). None when fewer than 2 populated
    channels — no measurable off-target gap."""

    compound_name: str
    channels_with_value: int
    best_pactivity: float
    best_channel: str
    selectivity_gap: float | None
    best_off_target_channel: str | None


def selectivity_index(cells: Sequence[MatrixCell]) -> list[SelectivityRow]:
    """Selectivity rows over matrix cells with resolved values.

    Aggregation rule when a compound has several cells tied at the
    best value: the first in gene-symbol order wins both slots —
    deterministic and disclosed; the tie never occurs in data-v1.0
    (artifact-pinned) and the pure tests pin the rule on a synthetic
    tie.
    """
    by_compound: dict[str, list[MatrixCell]] = {}
    for c in cells:
        if c.pactivity is not None:
            by_compound.setdefault(c.compound_name, []).append(c)
    out: list[SelectivityRow] = []
    for compound in sorted(by_compound):
        populated = sorted(
            by_compound[compound], key=lambda c: (-c.pactivity, c.gene_symbol)  # type: ignore[operator]
        )
        best = populated[0]
        if len(populated) >= 2:
            runner = populated[1]
            gap = best.pactivity - runner.pactivity  # type: ignore[operator]
            off_channel: str | None = runner.gene_symbol
        else:
            gap = None
            off_channel = None
        out.append(
            SelectivityRow(
                compound_name=compound,
                channels_with_value=len(populated),
                best_pactivity=best.pactivity,  # type: ignore[arg-type]
                best_channel=best.gene_symbol,
                selectivity_gap=gap,
                best_off_target_channel=off_channel,
            )
        )
    return out

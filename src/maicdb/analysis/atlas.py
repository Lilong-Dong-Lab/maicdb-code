"""Variant and compound atlas (P5, Track C).

Authority: spec §5.3 — the ΔP50 effect-size table (variant →
functional_effect → ΔP50 normalized, mapped to structural domains
where the variant position falls inside a covered structure; no
inferential statistics at this n) and the compound × channel matrix
(pActivity heatmap, per-compound selectivity index, honest about
sparsity — cells show "no data" rather than zeros). Values reuse P1's
``p_activity`` (−log10 molar; ADR-0005 unit policy) — no new
dependencies (spec: P5 needs none).

Frozen-corpus reality, disclosed (census keys per test):

* ``structure.residues_covered`` / ``coverage_pct`` are NULL on every
  structure row, so the ΔP50 → structural-domain mapping is VACUOUS
  at this tag (census-pinned as ``atlas.domain_covered_total``) — the
  mapping code is implemented generally (a variant
  position inside a covered range maps to that structure) and the
  artifact test pins today's zero mappings; future curation activates
  it. This is the same "defines the curation demand" pattern as the
  spec's own tension-conversion note (§5.2).
* Only some of the variant-linked ΔP50 rows carry a variant position
  (census-pinned as ``atlas.variant_linked_rows`` /
  ``atlas.variant_positions``).
* ``bioactivity.pchembl`` is NULL on every bioactivity row
  (census-pinned as ``corpus.bioactivity_pchembl_null``) —
  ``p_activity`` on (activity_value, activity_units) is the only value
  axis.
* The matrix is sparse by construction (census-pinned as
  ``atlas.matrix_cells`` / ``atlas.matrix_basis_totals``); a pair with
  several measurements aggregates to the MEAN of its pActivities (n
  carried per cell).

Selectivity index (disclosed definition): per compound with populated
pActivity values on ≥2 distinct channels, best-channel pActivity minus
best off-target pActivity (the second-best). Single-channel compounds
have no measurable off-target gap → None.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field as dataclass_field

from sqlalchemy.engine import Engine

from maicdb.analysis.harmonization import (
    DeltaP50Record as EffectRow,
)
from maicdb.analysis.harmonization import (
    in_covered_range as _in_covered_range,  # noqa: F401  (re-exported: unit tests pin it here)
)
from maicdb.analysis.harmonization import harmonize

__all__ = [
    "EffectRow",
    "MatrixCell",
    "SelectivityRow",
    "delta_p50_table",
    "compound_channel_matrix",
    "selectivity_index",
]


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


def delta_p50_table(engine: Engine) -> list[EffectRow]:
    """The ΔP50 effect-size table, deterministic order; structural
    domains resolved where a variant position falls inside a covered
    structure's range (vacuous at data-v1.2 — see module docstring).

    Thin delegate over the harmonization corpus (``EffectRow`` is the
    corpus's ``DeltaP50Record``) — the read and the domain mapping live
    in :mod:`maicdb.analysis.harmonization`.
    """
    return list(harmonize(engine).delta_p50)


def compound_channel_matrix(engine: Engine) -> list[MatrixCell]:
    """The compound × channel activity matrix, sparse (populated cells
    only), deterministic order (compound, then gene).

    ``compound.molecular_weight`` is deliberately NOT passed to
    ``p_activity``: the data-v1.2 μg/ml rows are silica nanoparticles
    with NULL MW, so ``mass_from_mw`` is unreachable today. When
    curation adds MW values, passing them here activates mass→molar
    resolution for this surface. Reads the harmonization corpus; each
    row's ``p_activity`` resolution is reused, not recomputed.
    """
    groups: dict[tuple[str, str], _CellAcc] = {}
    for row in harmonize(engine).bioactivity:
        key = (row.compound_name, row.gene_symbol)
        cell = groups.setdefault(key, _CellAcc(family=row.family))
        cell.n += 1
        act = row.pa  # resolved at harmonization (NULL unit → missing_value)
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
    deterministic and disclosed; the tie never occurs in data-v1.2
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

"""Read-only query layer for MAIC-DB (M1).

Pure functions over the published SQLite artifact — the CLI in this module
is the library's *first consumer*, not its implementation; later interfaces
(website, API, MCP server) wrap the same functions (vault ``handoff.md`` §4).

Binding rules (``HANDOFF.md`` §3):

* **Read-only** — the engine is always opened with the SQLite ``mode=ro``
  URI; the shipped artifact is never mutated.
* **Evidence chain everywhere** — every number this module returns is
  traceable to its measurement row and verbatim quote.
* **Frozen-layer wording** — PIEZO1/PIEZO2 evidence quotes are
  frozen-layer *unverified*; outputs touching those channels carry the
  §6.7 boilerplate and never render an affirmative verification status.
* **No hardcoded data** — gene lists, counts and gap disclosures are
  computed from SQL, never transcribed.
* **Caliber discipline** — one row = one curated measurement; aggregates
  are count/min/median/max with n printed, never inferential.
* **Determinism** — same input, byte-identical output; no timestamps.
* **Modality separation** — P50 (pressure) / T50 (tension) / X50
  (indentation) are distinct physical quantities and are never pooled or
  inter-converted; aggregates additionally group **per stored unit**
  (mmHg/psi, dyn/cm·mN/m, nm/um coexist by design — the loader's
  pre-authorized conversions are cross-magnitude only, so within-modality
  unit splits in the artifact are intentional).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.parse import quote

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Connection, Engine

from maicdb.models import BiophysicsExperiment, Bioactivity, Channel, UnmappedMeasurement

__all__ = [
    "open_readonly",
    "DEFAULT_DB_PATH",
    "PARAMETERS",
    "FROZEN_GENE_SYMBOLS",
    "FROZEN_LAYER_DISCLOSURE",
    "SIGN_CONVENTION_NOTE",
    "RATIO_MEDIAN_NOTE",
    "UnknownGeneError",
    "AmbiguousGeneError",
    "UnknownParameterError",
    "channel_card",
    "parameter_comparison",
    "provenance",
    "export",
    "main",
]

#: Default artifact location (repository layout; override with ``--db``).
DEFAULT_DB_PATH = Path("db") / "maicdb.sqlite"

#: Channels whose evidence quotes are frozen-layer **unverified** (vault
#: data notes §6.7 — an auto-fail wording rule everywhere in this project).
FROZEN_GENE_SYMBOLS = frozenset({"PIEZO1", "PIEZO2"})

#: The §6.7 required boilerplate, verbatim. Outputs touching a frozen
#: channel carry this and never render an affirmative verification status.
FROZEN_LAYER_DISCLOSURE = (
    "PIEZO1/PIEZO2 rows are frozen-layer data whose evidence quotes "
    "have not been re-verified; verification percentages cover the "
    "10 non-frozen layers only."
)

#: Threshold sign-convention wording (vault data notes §6.1 — a caption
#: rule, not data): values keep their as-recorded sign; we never pool or
#: take |value|, so no per-display annotation is owed beyond this note.
SIGN_CONVENTION_NOTE = (
    "values are as recorded (negative P50 = suction; K2P layers all-negative); "
    "no |value| pooling is performed (data notes §6.1)"
)

#: Why direction-blind ratio parameters carry no median: ``ratio_direction``
#: is NULL on every row this load, and cross-direction medians are
#: meaningless. A1 panel p4 semantics: direction-unstated groups report
#: count/min/max only, median left empty.
RATIO_MEDIAN_NOTE = (
    "median omitted: ratio_direction is NULL on every row this load, and "
    "cross-direction medians are meaningless (A1 panel p4 semantics — "
    "direction-unstated groups report count/min/max only)"
)


class UnknownGeneError(ValueError):
    """Raised when a gene symbol matches no channel row."""


class AmbiguousGeneError(ValueError):
    """Raised when a gene symbol matches multiple channel rows — the schema
    splits one gene across organisms (``UNIQUE(gene_symbol, organism_taxid)``;
    e.g. human + mouse PIEZO1). M1 refuses to pick one organism or pool
    across them silently; organism-disambiguated queries are future work."""


class UnknownParameterError(ValueError):
    """Raised when a parameter name is not in the registry."""


@dataclass(frozen=True)
class ParameterSpec:
    """Schema mapping for one Mechano-Gating Card parameter (M1 registry).

    ``column``/``unit_column`` are :class:`BiophysicsExperiment` attribute
    names. Fixed-unit parameters (τ in ms, conductance in pS, …) have the
    unit baked into the column name; threshold value+unit pairs keep both.
    This is *schema* mapping, not data — no measurement values live here.
    """

    column: str
    label: str
    unit_column: str | None = None
    fixed_unit: str | None = None
    #: Ratio parameters whose numerator/denominator direction is unrecorded
    #: (``ratio_direction`` NULL this load) — medians are omitted (see
    #: :data:`RATIO_MEDIAN_NOTE`); count/min/max still reported.
    direction_blind_ratio: bool = False


#: The M1 parameter registry (name → schema mapping). Names follow the
#: HANDOFF §2 examples (``p50``, ``tau_inact``).
PARAMETERS: dict[str, ParameterSpec] = {
    "p50": ParameterSpec("p50_value", "P50 pressure threshold", "p50_unit"),
    "t50": ParameterSpec("t50_value", "T50 tension threshold", "t50_unit"),
    "x50": ParameterSpec("x50_value", "X50 indentation threshold", "x50_unit"),
    "slope": ParameterSpec("slope", "Boltzmann/Hill slope", "slope_unit"),
    "tau_act": ParameterSpec("tau_act_ms", "activation time constant", fixed_unit="ms"),
    "tau_inact": ParameterSpec(
        "tau_inact_ms", "inactivation time constant", fixed_unit="ms"
    ),
    "tau_deact": ParameterSpec(
        "tau_deact_ms", "deactivation time constant", fixed_unit="ms"
    ),
    "conductance": ParameterSpec(
        "conductance_ps", "single-channel conductance", fixed_unit="pS"
    ),
    "reversal_potential": ParameterSpec(
        "reversal_potential_mv", "reversal potential", fixed_unit="mV"
    ),
    "delta_p50": ParameterSpec(
        "delta_p50_value", "ligand/variant-induced P50 shift", "delta_p50_unit"
    ),
    "ion_selectivity_ratio": ParameterSpec(
        "ion_selectivity_ratio", "ion selectivity ratio", direction_blind_ratio=True
    ),
    "ca_permeability": ParameterSpec(
        "ca_permeability", "Ca²⁺ permeability ratio", direction_blind_ratio=True
    ),
    "threshold_fold_shift": ParameterSpec(
        "threshold_fold_shift_value", "threshold fold shift", "threshold_fold_shift_unit"
    ),
    "macroscopic_rise_time": ParameterSpec(
        "macroscopic_rise_time_ms", "macroscopic rise time", fixed_unit="ms"
    ),
    "thermal_threshold": ParameterSpec(
        "thermal_threshold_c", "thermal threshold", fixed_unit="°C"
    ),
    "osmotic_threshold": ParameterSpec(
        "osmotic_threshold_value", "osmotic threshold", "osmotic_threshold_unit"
    ),
}

#: Evidence-chain columns rendered with every number (HANDOFF §3 rule 2).
_EVIDENCE_COLUMNS = (
    "measurement_id",
    "evidence_quote",
    "evidence_location",
    "confidence",
    "extractor_note",
    "condition_key",
    "n",
)


def _enum_str(value: object, attr: str) -> str:
    """Render a possibly-enum column value as the plain string stored in
    the DB (``attr`` is ``"name"`` for name-stored, ``"value"`` for
    value-stored enum columns)."""
    return cast(str, getattr(value, attr, value))


def _require_parameters(names: list[str]) -> None:
    """Raise :class:`UnknownParameterError` listing any unregistered names."""
    unknown = [n for n in names if n not in PARAMETERS]
    if unknown:
        raise UnknownParameterError(
            f"unknown parameter(s) {', '.join(map(repr, unknown))}; "
            f"known: {', '.join(PARAMETERS)}"
        )


def _gene_identity(conn: Connection, gene: str) -> dict:
    """Fetch the identity block for *gene*; raise if unknown.

    The known-gene list in the error is computed from SQL (no hardcoded
    data — HANDOFF §3 rule 4).
    """
    rows = conn.execute(
        select(
            Channel.maicdb_id,
            Channel.gene_symbol,
            Channel.gene_aliases,
            Channel.organism,
            Channel.organism_taxid,
            Channel.uniprot_accession,
            Channel.protein_name,
            Channel.family,
            Channel.activation_mechanism,
            Channel.ortholog_group,
            Channel.summary,
        ).where(Channel.gene_symbol == gene)
    ).mappings().all()
    if not rows:
        known = [r[0] for r in conn.execute(select(Channel.gene_symbol).order_by(Channel.gene_symbol))]
        raise UnknownGeneError(
            f"unknown gene {gene!r}; known genes: {', '.join(known)}"
        )
    if len(rows) > 1:
        # One gene, several organisms (schema: UNIQUE(gene_symbol,
        # organism_taxid)) — refuse to pick one silently.
        variants = ", ".join(
            f"{r['organism']} (taxid {r['organism_taxid']})" for r in rows
        )
        raise AmbiguousGeneError(
            f"gene {gene!r} spans {len(rows)} organisms: {variants}; "
            "organism-disambiguated queries are not yet supported"
        )
    identity = dict(rows[0])
    # Render name-stored enum members as their stored names.
    for key in ("family", "activation_mechanism"):
        identity[key] = _enum_str(identity.get(key), "name")
    return identity


def channel_card(engine: Engine, gene: str, parameters: list[str] | None = None) -> dict:
    """Identity block + parameter blocks with per-row evidence for *gene*.

    ``parameters=None`` renders **every** registry parameter — blocks with
    zero rows are reported (``n_rows: 0``), never hidden (HANDOFF §5).
    Rows are ordered by ``measurement_id`` for byte-stable output.
    """
    names = list(PARAMETERS) if parameters is None else list(parameters)
    _require_parameters(names)

    with engine.connect() as conn:
        card: dict = {"gene": _gene_identity(conn, gene), "parameters": {}}
        if gene in FROZEN_GENE_SYMBOLS:
            card["frozen_layer_disclosure"] = FROZEN_LAYER_DISCLOSURE
        for name in names:
            spec = PARAMETERS[name]
            value_col = getattr(BiophysicsExperiment, spec.column)
            cols = [value_col]
            if spec.unit_column is not None:
                cols.append(getattr(BiophysicsExperiment, spec.unit_column))
            # value/unit_as_reported ride along for every parameter — the
            # loader stores the pre-conversion original whenever it converted
            cols.append(BiophysicsExperiment.value_as_reported)
            cols.append(BiophysicsExperiment.unit_as_reported)
            cols.extend(getattr(BiophysicsExperiment, c) for c in _EVIDENCE_COLUMNS)
            rows = [
                dict(r)
                for r in conn.execute(
                    select(*cols)
                    .where(
                        BiophysicsExperiment.channel_id
                        == select(Channel.id)
                        .where(Channel.gene_symbol == gene)
                        .scalar_subquery(),
                        value_col.is_not(None),
                    )
                    .order_by(BiophysicsExperiment.measurement_id)
                ).mappings()
            ]
            for r in rows:
                # Normalize column names to the card vocabulary: the value
                # column is always "value", the unit column always "unit"
                # (plain str — value-stored enum members render as "mmHg").
                r["value"] = r.pop(spec.column)
                if spec.unit_column is not None:
                    r["unit"] = _enum_str(r.pop(spec.unit_column), "value")
                else:
                    r["unit"] = spec.fixed_unit
            card["parameters"][name] = {
                "label": spec.label,
                "n_rows": len(rows),
                "rows": rows,
            }
    return card


def parameter_comparison(engine: Engine, parameter: str) -> list[dict]:
    """Gene × parameter aggregate table: count/min/median/max **per stored
    unit**, every channel row included (zero-count genes reported, not
    hidden — HANDOFF §3 rules 4–5).

    Caliber discipline: one row = one curated measurement; ``count`` is the
    aggregate n. The per-row replicate counts (TEXT, often ranges) are *not*
    parsed into aggregates — they surface per-row in :func:`channel_card`.
    Each aggregate row carries its ``measurement_ids`` (rule 2: every
    printed number stays one step from its verbatim quote via
    :func:`provenance`). As-recorded value/unit strings are not aggregable
    across a unit group and are preserved per-row in :func:`channel_card`
    and :func:`provenance` — this table aggregates the normalized columns.

    Units are never pooled or inter-converted (rule 7): a gene measuring in
    both mmHg and psi gets two rows. A NULL stored unit (``slope`` in
    data-v1.0; unit-less parameters such as ``ion_selectivity_ratio``) is
    likewise its own bucket — those rows aggregate under ``unit=None`` and
    are reported, never erased (rule 5; rendered as an empty CSV cell /
    JSON ``null``). Fixed-unit parameters (τ ms, pS, …) aggregate under
    their baked-in unit. Output ordering is deterministic: gene asc, then
    unit (``None`` first within a gene).
    """
    _require_parameters([parameter])
    spec = PARAMETERS[parameter]
    value_col = getattr(BiophysicsExperiment, spec.column)

    with engine.connect() as conn:
        # Gene list computed from SQL (rule 4) — family rides along so
        # consumers can group without a second query. A gene spanning
        # organisms (schema-supported) would pool or duplicate rows
        # silently, so it fails loudly instead.
        gene_rows = conn.execute(
            select(
                Channel.gene_symbol,
                Channel.family,
                Channel.organism,
                Channel.organism_taxid,
            ).order_by(Channel.gene_symbol, Channel.organism)
        ).all()
        by_gene: dict[str, list] = {}
        for g in gene_rows:
            by_gene.setdefault(g[0], []).append(g)
        for gene_symbol, entries in by_gene.items():
            if len(entries) > 1:
                variants = ", ".join(
                    f"{e[2]} (taxid {e[3]})" for e in entries
                )
                raise AmbiguousGeneError(
                    f"gene {gene_symbol!r} spans {len(entries)} organisms: "
                    f"{variants}; organism-disambiguated comparisons are "
                    "not yet supported"
                )
        genes = [(g, entries[0][1]) for g, entries in by_gene.items()]
        unit_col = (
            getattr(BiophysicsExperiment, spec.unit_column)
            if spec.unit_column is not None
            else None
        )
        rows = conn.execute(
            select(
                Channel.gene_symbol,
                value_col,
                BiophysicsExperiment.measurement_id,
                *([unit_col] if unit_col is not None else []),
            )
            .join(Channel, BiophysicsExperiment.channel_id == Channel.id)
            .where(value_col.is_not(None))
        ).all()

    grouped: dict[tuple[str, str | None], list[tuple[float, str | None]]] = {}
    for row in rows:
        gene, value, mid = row[0], row[1], row[2]
        unit = row[3] if unit_col is not None else spec.fixed_unit
        unit = _enum_str(unit, "value")  # plain str ("mmHg", not member)
        grouped.setdefault((gene, unit), []).append((value, mid))

    out: list[dict] = []
    for gene, family in genes:
        family_name = _enum_str(family, "name")
        # NULL units are their own bucket (reported, never erased — rule 5);
        # ``key`` keeps the sort total and matches the tested ordering
        # contract (``unit or ""`` → None sorts first within a gene).
        gene_units = sorted(
            (u for (g, u) in grouped if g == gene), key=lambda u: u or ""
        )
        if gene_units:
            for unit in gene_units:
                # deterministic order even when measurement_id is NULL
                # (nullable column) or values tie
                pairs = sorted(grouped[(gene, unit)], key=lambda p: (p[0], p[1] or ""))
                values = [v for v, _ in pairs]
                # round(..., 6) mirrors the loader's converted-value precision
                # and keeps exports byte-stable across float repr changes.
                row = {
                    "gene": gene,
                    "family": family_name,
                    "parameter": parameter,
                    "unit": unit,
                    "count": len(values),
                    "min": round(values[0], 6),
                    "median": round(statistics.median(values), 6),
                    "max": round(values[-1], 6),
                    "measurement_ids": [mid for _, mid in pairs],
                }
                _decorate_aggregate_row(row, gene, spec)
                out.append(row)
        else:
            row = {
                "gene": gene,
                "family": family_name,
                "parameter": parameter,
                "unit": None,
                "count": 0,
                "min": None,
                "median": None,
                "max": None,
                "measurement_ids": [],
            }
            _decorate_aggregate_row(row, gene, spec)
            out.append(row)
    return out


def _decorate_aggregate_row(row: dict, gene: str, spec: ParameterSpec) -> None:
    """Attach the wording/caliber riders an aggregate row owes:

    * rule 3 — rows of a frozen-layer channel carry the §6.7 boilerplate on
      the row itself (counted **and** zero rows: library consumers render
      rows standalone, and a zero-count PIEZO row is still a PIEZO row);
    * A1 ratio-direction rule — direction-blind ratio rows omit the median
      (cross-direction medians are meaningless) and say so in ``note``.
    """
    if gene in FROZEN_GENE_SYMBOLS:
        row["frozen_layer_disclosure"] = FROZEN_LAYER_DISCLOSURE
    if spec.direction_blind_ratio and row["count"] > 0:
        row["median"] = None
        row["note"] = RATIO_MEDIAN_NOTE


#: Every table carrying a measurement evidence chain (searched in this
#: order by :func:`provenance`).
_EVIDENCE_TABLES = (BiophysicsExperiment, Bioactivity, UnmappedMeasurement)


def provenance(engine: Engine, measurement_id: str) -> dict | None:
    """The full evidence row for *measurement_id*, or None if unknown.

    Searches every evidence-carrying table (biophysics, bioactivity,
    unmapped gap archive) and returns the row with its ``table`` name and
    gene symbol attached — one-click provenance for any printed number.
    Rows belonging to a frozen-layer channel carry the §6.7 boilerplate
    (rule 3: the wording rule follows the evidence itself, so it holds on
    this path too).
    """
    with engine.connect() as conn:
        for model in _EVIDENCE_TABLES:
            row = conn.execute(
                select(model).where(model.measurement_id == measurement_id)
            ).mappings().first()
            if row is not None:
                out = {k: v for k, v in dict(row).items() if k != "channel_id"}
                out["table"] = model.__tablename__
                gene = conn.execute(
                    select(Channel.gene_symbol).where(Channel.id == row["channel_id"])
                ).scalar_one_or_none()
                out["gene"] = gene
                if gene in FROZEN_GENE_SYMBOLS:
                    out["frozen_layer_disclosure"] = FROZEN_LAYER_DISCLOSURE
                return out
    return None


#: Column order of the comparison export (CSV header and JSON row order).
#: ``note`` is empty except on rows carrying a caliber rider (e.g. the
#: ratio-median omission); the frozen-layer disclosure rides CSV exports
#: via stderr, not a column.
_EXPORT_COLUMNS = (
    "gene",
    "family",
    "parameter",
    "unit",
    "count",
    "min",
    "median",
    "max",
    "measurement_ids",
    "note",
)

#: Parameters whose sign convention is disclosed alongside aggregates
#: (vault data notes §6.1 — thresholds keep as-recorded signs).
_THRESHOLD_PARAMETERS = frozenset({"p50", "t50", "x50", "delta_p50"})


def export(
    engine: Engine, parameter: str, format: Literal["csv", "json"] = "csv"
) -> str:
    """Deterministic serialization of a parameter comparison (rule 6).

    * ``csv`` — pure data on stdout; when the result touches a frozen
      channel, the §6.7 boilerplate goes to **stderr** so the data stream
      stays clean while the wording rule still holds everywhere.
      ``measurement_ids`` cells are ``;``-joined.
    * ``json`` — ``{"parameter": …, "rows": […], "frozen_layer_disclosure": …}``
      (the disclosure field appears whenever a frozen gene is listed, zero-
      count rows included; threshold parameters add a ``sign_convention``
      note; direction-blind ratio rows carry a per-row ``note`` and no
      median).

    No timestamps anywhere; identical inputs produce byte-identical output.
    """
    rows = parameter_comparison(engine, parameter)

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(_EXPORT_COLUMNS)
        for r in rows:
            writer.writerow(
                [
                    ";".join(r["measurement_ids"])
                    if col == "measurement_ids"
                    else r.get(col, "")
                    for col in _EXPORT_COLUMNS
                ]
            )
        _disclose_to_stderr(rows, parameter)
        return buf.getvalue()

    if format == "json":
        doc: dict = {"parameter": parameter, "rows": rows}
        if parameter in _THRESHOLD_PARAMETERS:
            doc["sign_convention"] = SIGN_CONVENTION_NOTE
        if _touches_frozen(rows):
            doc["frozen_layer_disclosure"] = FROZEN_LAYER_DISCLOSURE
        return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    raise ValueError(f"unknown format {format!r}; expected 'csv' or 'json'")


def _touches_frozen(rows: list[dict]) -> bool:
    """True when any row — counted or zero — belongs to a frozen-layer
    channel. Zero-count PIEZO rows are still PIEZO rows: exports listing
    them carry the boilerplate (same policy as a zero-row PIEZO2 card)."""
    return any(r["gene"] in FROZEN_GENE_SYMBOLS for r in rows)


def _disclose_to_stderr(rows: list[dict], parameter: str) -> None:
    """CSV companion for the wording rule: the boilerplate must accompany
    piezo numbers, but stdout must remain pure data (rule 6). Threshold
    parameters also disclose the sign convention (§6.1)."""
    if parameter in _THRESHOLD_PARAMETERS:
        print(f"sign convention: {SIGN_CONVENTION_NOTE}", file=sys.stderr)
    if _touches_frozen(rows):
        print(FROZEN_LAYER_DISCLOSURE, file=sys.stderr)


# --------------------------------------------------------------------------- #
# Rendering + CLI (the library's first consumer)
# --------------------------------------------------------------------------- #
def _render_card(card: dict) -> str:
    """Human-readable channel card — deterministic plain text."""
    gene = card["gene"]
    lines = [
        f"{gene['gene_symbol']} — {gene['organism']} (family {gene['family']})"
    ]
    if gene.get("uniprot_accession"):
        lines.append(f"UniProt: {gene['uniprot_accession']}")
    if gene.get("ortholog_group"):
        lines.append(f"ortholog group: {gene['ortholog_group']}")
    if "frozen_layer_disclosure" in card:
        lines.append(f"NOTE: {card['frozen_layer_disclosure']}")

    for name, block in card["parameters"].items():
        suffix = "" if block["n_rows"] else "  [reported, not hidden]"
        lines.append("")
        lines.append(
            f"{name} — {block['label']} ({block['n_rows']} row"
            f"{'s' if block['n_rows'] != 1 else ''}){suffix}"
        )
        if name in _THRESHOLD_PARAMETERS:
            lines.append(f"    sign convention: {SIGN_CONVENTION_NOTE}")
        for r in block["rows"]:
            as_reported = ""
            if r.get("value_as_reported") is not None:
                as_reported = (
                    f"  (as reported: {r['value_as_reported']}"
                    f"{' ' + r['unit_as_reported'] if r.get('unit_as_reported') else ''})"
                )
            lines.append(
                f"  {r['measurement_id']}  {r['value']} {r['unit'] or ''}"
                f"{as_reported}  confidence={r['confidence']}  n={r['n']}"
            )
            if r.get("evidence_quote"):
                lines.append(f"    quote: {r['evidence_quote']}")
            if r.get("evidence_location"):
                lines.append(f"    location: {r['evidence_location']}")
            if r.get("extractor_note"):
                lines.append(f"    extractor_note: {r['extractor_note']}")
    return "\n".join(lines) + "\n"


def _render_provenance(ev: dict) -> str:
    """Human-readable evidence row."""
    lines = [f"{ev['measurement_id']} ({ev['table']}, gene {ev['gene']})"]
    if "frozen_layer_disclosure" in ev:
        lines.append(f"NOTE: {ev['frozen_layer_disclosure']}")
    for key in ("maicdb_id", "evidence_quote", "evidence_location",
                "confidence", "extractor_note", "condition_key", "n"):
        if ev.get(key) is not None:
            lines.append(f"{key}: {ev[key]}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """``maicdb-query`` — the library's first consumer (argparse, mirroring
    the repo's existing console scripts).

    Subcommands:
      channel GENE [--parameter P ...]   channel card with evidence
      export --parameter P [--format F]  comparison table (csv|json)
      provenance MEASUREMENT_ID          full evidence row
    """
    parser = argparse.ArgumentParser(
        prog="maicdb-query",
        description="Query the published MAIC-DB artifact (read-only).",
    )
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB_PATH,
        help=f"path to the SQLite artifact (default: {DEFAULT_DB_PATH})",
    )
    # --db is also accepted *after* the subcommand (SUPPRESS keeps the
    # subparser default from clobbering an explicit pre-subcommand value).
    db_parent = argparse.ArgumentParser(add_help=False)
    db_parent.add_argument("--db", type=Path, default=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    p_channel = sub.add_parser(
        "channel", parents=[db_parent], help="channel card + evidence"
    )
    p_channel.add_argument("gene", help="gene symbol, e.g. PIEZO1")
    p_channel.add_argument(
        "--parameter", action="append", metavar="P",
        help="restrict the card to parameter P (repeatable); default: all",
    )

    p_export = sub.add_parser(
        "export", parents=[db_parent], help="gene × parameter comparison table"
    )
    p_export.add_argument("--parameter", required=True, help="e.g. p50, tau_inact")
    p_export.add_argument(
        "--format", choices=("csv", "json"), default="csv",
        help="output format (default: csv)",
    )

    p_prov = sub.add_parser(
        "provenance", parents=[db_parent], help="full evidence row"
    )
    p_prov.add_argument("measurement_id", help="e.g. PIEZO1-EX-00005")

    args = parser.parse_args(argv)
    try:
        engine = open_readonly(args.db)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        if args.command == "channel":
            card = channel_card(engine, args.gene, parameters=args.parameter)
            sys.stdout.write(_render_card(card))
        elif args.command == "export":
            sys.stdout.write(export(engine, args.parameter, format=args.format))
        else:
            ev = provenance(engine, args.measurement_id)
            if ev is None:
                print(
                    f"error: unknown measurement_id {args.measurement_id!r}",
                    file=sys.stderr,
                )
                return 1
            sys.stdout.write(_render_provenance(ev))
    except UnknownGeneError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except AmbiguousGeneError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except UnknownParameterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    return 0


def open_readonly(path: str | Path) -> Engine:
    """Open *path* as a read-only SQLite engine (``mode=ro`` URI).

    Raises ``FileNotFoundError`` for a missing artifact — a query layer
    should never silently create an empty database.
    """
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"MAIC-DB artifact not found: {resolved}")
    # Canonical read-only form from the SQLAlchemy 2.0 sqlite docs ("URI
    # Connections"); the in-URL ``uri=true`` is required for the query
    # string to reach sqlite3 intact.
    return create_engine(
        f"sqlite:///file:{quote(str(resolved))}?mode=ro&uri=true",
        connect_args={"uri": True},
        future=True,
    )

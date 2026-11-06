"""JSON site payloads for the Analysis section (P7, spec §8).

The site's data layer (``site/build.py``) serializes the P3/P4/P5/P6
analysis modules' outputs verbatim into ``site/_data/analysis/*.json``;
pages never query the DB (the site's thin-consumer rule). Each payload
carries its provenance header — the artifact's own ``data_freeze_tag``
from ``db_meta`` — so a page can never show numbers without their
release identity. Serialization is generic (``dataclasses.asdict``), so
a module-field change surfaces here without a hand-copied field list.
Numbers keep full precision; pages round at render.

Disclosed serialization rules:

* ``HeatmapCell.compliance`` is a property (``asdict`` skips
  properties) — added explicitly, preserving the P3 rule: None when
  ``applicable == 0``.
* Trends year-series rows keep their module order (the modules sort);
  nothing is re-sorted here.
* The atlas selectivity rows consume the SAME ``compound_channel_matrix``
  call as the matrix block — the two JSON blocks cannot disagree.
* The channel MIMIC badge aggregates at FIELD level
  (Σreported / Σapplicable — P3 ``field_totals``' convention), not as a
  mean of per-record scores: small-n channels cannot inflate.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from sqlalchemy import text as sql_text

from maicdb.analysis.atlas import (
    compound_channel_matrix,
    delta_p50_table,
    selectivity_index,
)
from maicdb.analysis.audit import (
    BREAKDOWN_KEYS,
    PIEZO_YEAR,
    breakdown,
    compliance_by_year,
    field_totals,
    four_field_audit,
    heatmap,
    load_families,
    load_meta,
)
from maicdb.analysis.biophysics import (
    boltzmann_demo,
    kinetics_atlas,
    lab_spread,
    load_p50_records,
    threshold_meta,
)
from maicdb.analysis.mimic import score_all
from maicdb.analysis.trends import (
    assay_drift,
    load_trend_records,
    model_system_drift,
    parameter_adoption,
    pubs_per_year_by_family,
    pubs_per_year_total,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

__all__ = [
    "analysis_payloads",
    "channel_mimic_blocks",
    "data_freeze_tag",
    "mimic_blocks_from_scores",
]


def data_freeze_tag(engine: Engine) -> str:
    """The artifact's own release identity (``db_meta`` key-value row
    ``data_freeze_tag``)."""
    with engine.connect() as conn:
        tag = conn.execute(
            sql_text(
                "SELECT value FROM db_meta WHERE key = 'data_freeze_tag'"
            )
        ).scalar()
    return str(tag) if tag is not None else ""


def _rows(objs) -> list[dict]:
    return [asdict(o) for o in objs]


def _cell_payload(cell):
    d = asdict(cell)
    d["compliance"] = cell.compliance
    return d


def audit_payload(engine: Engine) -> dict:
    """P3 (Track A, spec §5.1): tri-state heatmap, field totals, era
    contrast, breakdowns, the §9 four-field headline under both
    readings."""
    scores = score_all(engine)
    meta = load_meta(engine)
    families = load_families(engine)
    era = compliance_by_year(
        scores, {mid: m.year for mid, m in meta.items()}
    )
    with engine.connect() as conn:
        records = [
            dict(r)
            for r in conn.execute(
                sql_text(
                    "SELECT * FROM biophysics_experiment ORDER BY maicdb_id"
                )
            ).mappings()
        ]
    return {
        "data_freeze_tag": data_freeze_tag(engine),
        "provenance": (
            "maicdb.analysis.audit (P3, spec §5.1) — tri-state MIMIC "
            "counts, census-anchored; ADR-0005 applicability"
        ),
        "n_records": len(scores),
        "mean_score": (
            sum(s.score for s in scores) / len(scores) if scores else None
        ),
        "field_totals": {
            k: _cell_payload(v) for k, v in field_totals(scores).items()
        },
        "heatmap": {
            fam: {k: _cell_payload(c) for k, c in fields.items()}
            for fam, fields in heatmap(scores, families).items()
        },
        "compliance_by_year": {**asdict(era), "piezo_year": PIEZO_YEAR},
        "breakdowns": {
            key: _rows(breakdown(scores, meta, key))
            for key in BREAKDOWN_KEYS
        },
        "four_field_audit": asdict(four_field_audit(records)),
    }


def biophysics_payload(engine: Engine) -> dict:
    """P4 (Track B, spec §5.2): D–L pooled |P50| per (family, stimulus),
    kinetics atlas, between-publication spread, the same-fit ΔG demo."""
    records = load_p50_records(engine)
    with engine.connect() as conn:
        ck = {
            str(r["maicdb_id"]): (r["condition_key"] or "")
            for r in conn.execute(
                sql_text(
                    "SELECT maicdb_id, condition_key FROM "
                    "biophysics_experiment"
                )
            ).mappings()
        }
    return {
        "data_freeze_tag": data_freeze_tag(engine),
        "provenance": (
            "maicdb.analysis.biophysics (P4, spec §5.2) — "
            "DerSimonian–Laird on log10 |P50|, publication-level "
            "clusters, identifiability-gated inference"
        ),
        "threshold_meta": _rows(threshold_meta(records)),
        "kinetics_atlas": _rows(kinetics_atlas(engine)),
        "lab_spread": _rows(lab_spread(records)),
        "boltzmann_demo": boltzmann_demo(engine, ck),
    }


def atlas_payload(engine: Engine) -> dict:
    """P5 (Track C, spec §5.3): ΔP50 effect sizes, the compound ×
    channel pActivity matrix, per-compound selectivity."""
    matrix = compound_channel_matrix(engine)
    return {
        "data_freeze_tag": data_freeze_tag(engine),
        "provenance": (
            "maicdb.analysis.atlas (P5, spec §5.3) — variant and "
            "compound surfaces on P1's p_activity axis; structural "
            "domains vacuous at this tag (residues_covered NULL)"
        ),
        "n_cells": len(matrix),
        "n_compounds": len({c.compound_name for c in matrix}),
        "n_channels": len({c.gene_symbol for c in matrix}),
        "delta_p50": _rows(delta_p50_table(engine)),
        "matrix": _rows(matrix),
        "selectivity": _rows(selectivity_index(matrix)),
    }


def trends_payload(engine: Engine) -> dict:
    """P6 (Track D, spec §5.4): publications per year, parameter
    adoption, assay-mode drift, expression-system drift."""
    records = load_trend_records(engine)
    return {
        "data_freeze_tag": data_freeze_tag(engine),
        "provenance": (
            "maicdb.analysis.trends (P6, spec §5.4) — corpus growth and "
            "field-adoption views; per-family year cells are NOT "
            "additive to the total (distinct-publication counting)"
        ),
        "pubs_per_year_by_family": _rows(pubs_per_year_by_family(records)),
        "pubs_per_year_total": _rows(pubs_per_year_total(records)),
        "parameter_adoption": _rows(parameter_adoption(records)),
        "assay_drift": _rows(assay_drift(records)),
        "model_system_drift": _rows(model_system_drift(records)),
    }


def analysis_payloads(engine: Engine) -> dict[str, dict]:
    """All four track payloads in one call (the site build's entry)."""
    return {
        "audit": audit_payload(engine),
        "biophysics": biophysics_payload(engine),
        "atlas": atlas_payload(engine),
        "trends": trends_payload(engine),
    }


def mimic_blocks_from_scores(scores) -> dict[int, dict]:
    """Per-channel MIMIC badge aggregation over scored records.

    Field-level aggregation (Σreported / Σapplicable — the P3
    ``field_totals`` convention), so a small-n channel cannot inflate a
    mean-of-means. Keys are channel ids; a channel with zero records
    gets no block (the card renders no badge rather than a lie). Pure
    function over ``MIMICScore`` objects — the artifact wrapper feeds it
    ``score_all``; the pure tests exercise the rule on synthetic scores.
    """
    blocks: dict[int, dict] = {}
    for score in scores:
        b = blocks.setdefault(
            score.channel_id,
            {"n_records": 0, "reported": 0, "applicable": 0, "fields": {}},
        )
        b["n_records"] += 1
        b["reported"] += score.reported
        b["applicable"] += score.applicable
        for name, st in score.fields.items():
            cell = b["fields"].setdefault(name, {"reported": 0, "applicable": 0})
            if st.status == "reported":
                cell["reported"] += 1
            if st.applicable:
                cell["applicable"] += 1
    for b in blocks.values():
        b["score"] = (b["reported"] / b["applicable"]) if b["applicable"] else None
    return blocks


def channel_mimic_blocks(engine: Engine) -> dict[int, dict]:
    """Badge blocks from the artifact (``score_all`` behind
    ``mimic_blocks_from_scores``)."""
    return mimic_blocks_from_scores(score_all(engine))

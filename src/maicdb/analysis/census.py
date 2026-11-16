"""Generated census snapshot for the frozen data artifact.

Every census-class pin in the artifact tests is a value this module
computes: raw corpus counts over ``db/maicdb.sqlite`` plus compositions of
the analysis loaders, namespaced by track (corpus, replicates, activity,
joins, audit, biophysics, atlas, trends, mimic, site_payloads).

The pin mechanism (CODING_STANDARDS.md §6, "generated pins"):

- ``maicdb-census --write`` regenerates ``tests/census_snapshot.json``
  from the current artifact. Byte stability comes from ``json.dumps`` with
  ``sort_keys=True`` and a fixed indent, plus the deterministic ordering of
  every loader this module calls.
- A freeze retarget replaces the artifact and regenerates the snapshot;
  the PR diff of the snapshot IS the reviewed derivation of the new pins.
  Before writing, the module cross-anchors the engine against
  ``db/load-manifest.json``: the ``db_meta`` freeze tag must carry the
  manifest's ``freeze_tag`` prefix, every direct-table count in the
  manifest must equal a fresh ``COUNT(*)`` over the same table, and the
  manifest's ``freeze_manifest_sha256`` must match the actual bytes of
  ``db/freeze-manifest.json`` (the chain db → load manifest → freeze
  manifest → vault bytes, ADR-0007)
  (loader-derived manifest counts — ``structure_publication_links``,
  ``unit_conversions`` — are not checked here because no single SQL
  statement re-derives them).
- Artifact tests recompute a track with :func:`compute_census` and compare
  it to the snapshot. Hand-transcribing a corpus number into a test is a
  finding.

Out of scope by decision (they stay transcribed pins with docstring
derivation trails): scalar float analysis outputs, accession ids, and
structural checks. This module emits JSON-native types only (str keys,
lists, ints, bools) so a computed track compares equal to the loaded
snapshot without conversion.

Paths are resolved relative to the repository root (the parent of the
installed ``src/`` tree), so the CLI targets ``db/maicdb.sqlite`` and
``tests/census_snapshot.json`` there.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from sqlalchemy import text
from sqlalchemy.engine import Engine

from maicdb.analysis.activity import p_activity
from maicdb.analysis.atlas import compound_channel_matrix, delta_p50_table, selectivity_index
from maicdb.analysis.audit import (
    MANDATED_FIELDS,
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
from maicdb.analysis.joins import same_fit_candidates, same_fit_marker_hits
from maicdb.analysis.mimic import score_all
from maicdb.analysis.replicates import coalesce_replicates
from maicdb.analysis.site_payloads import analysis_payloads, channel_mimic_blocks, data_freeze_tag
from maicdb.analysis.trends import (
    PARAMETERS,
    assay_drift,
    load_trend_records,
    model_system_drift,
    parameter_adoption,
    pubs_per_year_by_family,
    pubs_per_year_total,
)
from maicdb.query import open_readonly

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Manifest "counts" keys that map 1:1 to a SQL table (models.py
# __tablename__). The two loader-derived manifest counts are excluded.
_MANIFEST_TABLES = (
    ("publication", "publication"),
    ("channel", "channel"),
    ("external_reference", "external_reference"),
    ("compound", "compound"),
    ("variant", "variant"),
    ("structure", "structure"),
    ("biophysics", "biophysics_experiment"),
    ("bioactivity", "bioactivity"),
    ("unmapped", "unmapped_measurement"),
)


def render_snapshot(census: dict) -> str:
    """Serialize a census dict to the canonical snapshot bytes."""
    return json.dumps(census, sort_keys=True, indent=2) + "\n"


def compute_census(engine: Engine) -> dict:
    """Compute every census track against the artifact behind *engine*."""
    return {
        "freeze_tag": data_freeze_tag(engine),
        "corpus": _corpus_track(engine),
        "replicates": _replicates_track(engine),
        "activity": _activity_track(engine),
        "joins": _joins_track(engine),
        "audit": _audit_track(engine),
        "biophysics": _biophysics_track(engine),
        "atlas": _atlas_track(engine),
        "trends": _trends_track(engine),
        "mimic": _mimic_track(engine),
        "site_payloads": _site_payloads_track(engine),
    }


def manifest_anchor_problems(engine: Engine, repo_root: Path = _REPO_ROOT) -> list[str]:
    """Cross-anchor the artifact against ``db/load-manifest.json``.

    Returns a list of human-readable problems; empty means anchored.
    """
    manifest_path = repo_root / "db" / "load-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    tag = data_freeze_tag(engine)
    expected_prefix = manifest["freeze_tag"] + "@"
    if not tag.startswith(expected_prefix):
        problems.append(
            f"freeze tag mismatch: db_meta {tag!r} does not carry the "
            f"manifest freeze_tag prefix {expected_prefix!r}"
        )
    counts = manifest["counts"]
    for key, table in _MANIFEST_TABLES:
        n = _scalar(engine, f"SELECT COUNT(*) FROM {table}")
        if counts.get(key) != n:
            problems.append(f"count mismatch for {key}: manifest {counts.get(key)} != db {n}")
    freeze_manifest_path = repo_root / "db" / "freeze-manifest.json"
    freeze_manifest_sha = hashlib.sha256(
        freeze_manifest_path.read_bytes()).hexdigest()
    declared = manifest.get("freeze_manifest_sha256")
    if declared != freeze_manifest_sha:
        problems.append(
            "freeze-manifest chain broken: load manifest declares "
            f"{str(declared)[:12]!r} but db/freeze-manifest.json hashes to "
            f"{freeze_manifest_sha[:12]!r}"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="maicdb-census",
        description=(
            "Compute the corpus census for the frozen artifact. Default mode "
            "verifies tests/census_snapshot.json against the artifact; "
            "--write regenerates it."
        ),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="regenerate tests/census_snapshot.json from the current artifact",
    )
    parser.add_argument(
        "database",
        nargs="?",
        default=None,
        help="path to the artifact (default: <repo>/db/maicdb.sqlite)",
    )
    args = parser.parse_args(argv)
    repo_root = _REPO_ROOT
    db_path = Path(args.database) if args.database else repo_root / "db" / "maicdb.sqlite"
    engine = open_readonly(db_path)
    census = compute_census(engine)
    problems = manifest_anchor_problems(engine, repo_root)
    if problems:
        for problem in problems:
            print(f"manifest anchor FAILED: {problem}", file=sys.stderr)
        print(
            "the artifact and db/load-manifest.json disagree — refusing to "
            "verify or write the census snapshot",
            file=sys.stderr,
        )
        return 2
    snapshot_path = repo_root / "tests" / "census_snapshot.json"
    fresh = render_snapshot(census)
    if args.write:
        snapshot_path.write_text(fresh, encoding="utf-8")
        print(f"wrote {snapshot_path} ({len(fresh)} bytes, freeze {census['freeze_tag']})")
        return 0
    if not snapshot_path.exists():
        print(f"no snapshot at {snapshot_path}; run `maicdb-census --write` first", file=sys.stderr)
        return 2
    if snapshot_path.read_text(encoding="utf-8") == fresh:
        print(f"census matches {snapshot_path} (freeze {census['freeze_tag']})")
        return 0
    print(f"census DRIFT vs {snapshot_path} (freeze {census['freeze_tag']}):", file=sys.stderr)
    current = json.loads(snapshot_path.read_text(encoding="utf-8"))
    for track in sorted(set(current) | set(census)):
        old, new = current.get(track), census.get(track)
        if old == new:
            continue
        if isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(set(old) | set(new)):
                if old.get(key) != new.get(key):
                    print(f"  {track}.{key}: snapshot {old.get(key)!r} -> computed {new.get(key)!r}", file=sys.stderr)
        else:
            print(f"  {track}: snapshot {old!r} -> computed {new!r}", file=sys.stderr)
    return 1


def _scalar(engine: Engine, sql: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar_one()


def _count_pair(engine: Engine, sql: str) -> list[int]:
    """Run a two-column aggregate query and return ``[col0, col1]``."""
    with engine.connect() as conn:
        row = conn.execute(text(sql)).one()
    return [row[0], row[1]]


def _records(engine: Engine) -> list[Mapping[str, object]]:
    with engine.connect() as conn:
        return cast(
            "list[Mapping[str, object]]",
            [
                dict(r)
                for r in conn.execute(
                    text("SELECT * FROM biophysics_experiment ORDER BY maicdb_id")
                ).mappings()
            ],
        )


def _condition_key_map(engine: Engine) -> dict[str, str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT maicdb_id, condition_key FROM biophysics_experiment")).all()
    return {row[0]: (row[1] or "") for row in rows}


def _corpus_track(engine: Engine) -> dict:
    return {
        "experiment_count": _scalar(
            engine, "SELECT COUNT(*) FROM biophysics_experiment"
        ),
        "p50_psi_rows": _scalar(
            engine, "SELECT COUNT(*) FROM biophysics_experiment WHERE p50_unit = 'psi'"
        ),
        "t50_dyncm_rows": _scalar(
            engine, "SELECT COUNT(*) FROM biophysics_experiment WHERE t50_unit = 'dyn/cm'"
        ),
        "x50_nm_rows": _scalar(
            engine, "SELECT COUNT(*) FROM biophysics_experiment WHERE x50_unit = 'nm'"
        ),
        "bioactivity_pchembl_null": _scalar(
            engine, "SELECT COUNT(*) FROM bioactivity WHERE pchembl IS NULL"
        ),
    }


def _replicates_track(engine: Engine) -> dict:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT n_cells, n FROM biophysics_experiment")).all()
    buckets = Counter(coalesce_replicates(n_cells, n).source for n_cells, n in rows)
    return {"coalesce_buckets": dict(buckets)}


def _activity_track(engine: Engine) -> dict:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT ba.activity_value, ba.activity_units, c.molecular_weight "
                "FROM bioactivity AS ba LEFT JOIN compound AS c ON c.id = ba.compound_id"
            )
        ).all()
    bases = Counter(p_activity(value, unit, mw).basis for value, unit, mw in rows)
    return {"pactivity_bases": dict(bases)}


def _joins_track(engine: Engine) -> dict:
    slope_only = _scalar(
        engine,
        "SELECT COUNT(*) FROM biophysics_experiment "
        "WHERE slope IS NOT NULL AND p50_value IS NULL "
        "AND t50_value IS NULL AND x50_value IS NULL",
    )
    return {
        "slope_only_rows": slope_only,
        "marker_hit_count": len(same_fit_marker_hits(engine)),
        "candidate_count": len(same_fit_candidates(engine)),
    }


def _audit_track(engine: Engine) -> dict:
    scores = score_all(engine)
    meta = load_meta(engine)
    families = load_families(engine)
    era = compliance_by_year(scores, {mid: m.year for mid, m in meta.items()})
    totals = field_totals(scores)
    hm = heatmap(scores, families)
    audit = four_field_audit(_records(engine))
    mode_groups = breakdown(scores, meta, "recording_mode")
    family_groups = breakdown(scores, meta, "family")
    journal_groups = breakdown(scores, meta, "journal")
    temperature = totals["temperature_c"]
    ph = totals["ph"]
    recording_mode = totals["recording_mode"]
    velocity = totals["stimulus_velocity"]
    cell_type = totals["cell_type"]
    return {
        "channel_count": len(families),
        "meta_join_vacuity": {
            f: sum(1 for m in meta.values() if getattr(m, f) is None)
            for f in ("family", "year", "journal")
        },
        "family_slice_counts": dict(Counter(families[s.channel_id] for s in scores)),
        "era_split": {"pre": era.pre_k, "post": era.post_k, "unassigned": era.unassigned_k},
        "era_year_k": [[y.year, y.k] for y in era.years],
        "field_total_temperature_c": [temperature.reported, temperature.not_extracted, temperature.applicable],
        "field_total_ph": [ph.reported, ph.applicable],
        "field_total_recording_mode": [recording_mode.reported, recording_mode.not_extracted, recording_mode.applicable],
        "field_total_stimulus_velocity": [velocity.reported, velocity.applicable],
        "field_total_cell_type": [cell_type.reported, cell_type.not_extracted, cell_type.applicable],
        "heatmap_family_keys": len(hm),
        "heatmap_temperature_reported": {f: hm[f]["temperature_c"].reported for f in hm},
        "as_written_missing": {name: audit.fields[name].missing_as_written for name in MANDATED_FIELDS},
        "failing_any_as_written": list(audit.failing_any_as_written),
        "adr_missing": {
            name: [audit.fields[name].applicable, audit.fields[name].missing_when_applicable]
            for name in MANDATED_FIELDS
        },
        "failing_any_adr": list(audit.failing_any_adr),
        "adr_clean_records": audit.failing_any_adr[1] - audit.failing_any_adr[0],
        "breakdown_mode_crossfoot_k": sum(g.k for g in mode_groups),
        "breakdown_cell_attached_k": next(g.k for g in mode_groups if g.group == "CELL_ATTACHED"),
        "breakdown_family_rows": len(family_groups),
        "breakdown_family_crossfoot_k": sum(g.k for g in family_groups),
        "breakdown_mscl_k": next(g.k for g in family_groups if g.group == "MSCL_MSCS"),
        "breakdown_journal_rows": len(journal_groups),
        "breakdown_journal_crossfoot_k": sum(g.k for g in journal_groups),
    }


def _biophysics_track(engine: Engine) -> dict:
    records = load_p50_records(engine)
    cells = {(c.family, c.stimulus_type): c for c in threshold_meta(records)}
    kinetics = kinetics_atlas(engine)
    spread = lab_spread(records)
    demos = boltzmann_demo(engine, _condition_key_map(engine))
    n_by_cell: Counter = Counter()
    pubs_by_cell: defaultdict = defaultdict(set)
    for r in records:
        key = (r.family, r.stimulus_type)
        n_by_cell[key] += 1
        pubs_by_cell[key].add(r.publication_id)
    piezo_pc = cells[("PIEZO", "PRESSURE_CLAMP")]
    asic_inact = next(c for c in kinetics if c.gene_symbol == "ASIC" and c.kind == "tau_inact")
    piezo1_pc = next(c for c in spread if c.gene_symbol == "PIEZO1" and c.stimulus_type == "PRESSURE_CLAMP")
    mscl_suction = next(c for c in spread if c.gene_symbol == "MscL" and c.stimulus_type == "SUCTION")
    return {
        "p50_records": len(records),
        "p50_unit_split": dict(Counter(r.p50_unit for r in records)),
        "p50_sign_split": [
            sum(1 for r in records if r.p50_mmhg < 0),
            sum(1 for r in records if r.p50_mmhg > 0),
            sum(1 for r in records if r.p50_mmhg == 0),
        ],
        "p50_condition_key_degeneracy": _count_pair(
            engine,
            "SELECT COUNT(*), COUNT(DISTINCT condition_key) FROM biophysics_experiment "
            "WHERE p50_value IS NOT NULL AND condition_key IS NOT NULL",
        ),
        "p50_cell_census": {
            f"{f}/{s}": [n_by_cell[(f, s)], len(pubs_by_cell[(f, s)])] for f, s in n_by_cell
        },
        "threshold_meta_cells": len(cells),
        "meta_piezo_pc": {"k": piezo_pc.k, "n": piezo_pc.n},
        "cell_identifiability": {
            "K2P/PRESSURE_CLAMP": cells[("K2P", "PRESSURE_CLAMP")].identifiable,
            "TMC/PRESSURE_CLAMP": cells[("TMC", "PRESSURE_CLAMP")].identifiable,
            "TRP/PRESSURE_CLAMP": cells[("TRP", "PRESSURE_CLAMP")].identifiable,
        },
        "cell_negative_n": {
            f"{c.family}/{c.stimulus_type}": c.negative_n
            for c in sorted(cells.values(), key=lambda c: (c.family, c.stimulus_type or ""))
        },
        "kinetics_cells": len(kinetics),
        "kinetics_totals": {
            kind: _scalar(
                engine,
                f"SELECT COUNT(*) FROM biophysics_experiment WHERE {col} IS NOT NULL",
            )
            for kind, col in (
                ("tau_act", "tau_act_ms"),
                ("tau_inact", "tau_inact_ms"),
                ("tau_deact", "tau_deact_ms"),
            )
        },
        "kinetics_genes": sorted({c.gene_symbol for c in kinetics}),
        "kinetics_asic_tau_inact": {"k": asic_inact.k, "n_pubs": asic_inact.n_pubs},
        "lab_spread_cells": len(spread),
        "lab_spread_piezo1_pc": {"k": piezo1_pc.k, "n": piezo1_pc.n},
        "lab_spread_mscl_suction": {"k": mscl_suction.k, "n": mscl_suction.n},
        "boltzmann_pairs": len(demos),
        "boltzmann_top_token_overlap": max(cast("int", d["token_overlap"]) for d in demos),
    }


def _atlas_track(engine: Engine) -> dict:
    effects = delta_p50_table(engine)
    matrix = compound_channel_matrix(engine)
    selectivity = selectivity_index(matrix)
    with engine.connect() as conn:
        unit_rows = conn.execute(
            text(
                "SELECT delta_p50_unit, COUNT(*) FROM biophysics_experiment "
                "WHERE delta_p50_value IS NOT NULL GROUP BY delta_p50_unit"
            )
        ).all()
        gene_rows = conn.execute(
            text(
                "SELECT c.gene_symbol, COUNT(*) FROM biophysics_experiment e "
                "JOIN channel c ON e.channel_id = c.id "
                "WHERE e.delta_p50_value IS NOT NULL GROUP BY c.gene_symbol"
            )
        ).all()
    basis_totals: dict[str, int] = {}
    for c in matrix:
        for basis, n in c.basis_counts:
            basis_totals[basis] = basis_totals.get(basis, 0) + n
    return {
        "delta_p50_rows": len(effects),
        "delta_p50_units": dict(unit_rows),
        "variant_linked_rows": sum(1 for r in effects if r.variant_linked),
        "variant_hgvs_nonnull": sum(1 for r in effects if r.variant is not None),
        "variant_effect_nonnull": sum(1 for r in effects if r.functional_effect is not None),
        "variant_positions": sorted(r.variant_position for r in effects if r.variant_position is not None),
        "domain_covered_total": sum(len(r.domains) for r in effects),
        "delta_p50_gene_split": dict(gene_rows),
        "matrix_cells": len(matrix),
        "matrix_activity_rows": sum(c.k for c in matrix),
        "matrix_multi_channel_excess": sum(c.k - 1 for c in matrix),
        "cells_with_pactivity": sum(1 for c in matrix if c.pactivity is not None),
        "matrix_basis_totals": basis_totals,
        "matrix_family_split": dict(Counter(c.family for c in matrix)),
        "selectivity_rows": len(selectivity),
        "selectivity_gapped_rows": sum(1 for r in selectivity if r.selectivity_gap is not None),
    }


def _trends_track(engine: Engine) -> dict:
    records = load_trend_records(engine)
    by_family = pubs_per_year_by_family(records)
    total = pubs_per_year_total(records)
    adoption = parameter_adoption(records)
    drift = assay_drift(records)
    model = model_system_drift(records)
    year_k = {t.year: t.k for t in total}
    adoption_cells = {(r.parameter, r.year): r.k for r in adoption}
    adoption_years = {r.year for r in adoption}
    none_2011 = next(r.k for r in model if r.year == 2011 and r.expression_system is None)
    return {
        "record_count": len(records),
        "join_vacuity": {
            f: sum(1 for r in records if getattr(r, f) is None) for f in ("year", "family")
        },
        "parameter_census": {
            label: sum(1 for r in records if label in r.parameters)
            for label in ("p50", "conductance", "tau_inact", "x50")
        },
        "pubs_by_family_rows": len(by_family),
        "pubs_by_family_k_total": sum(r.k for r in by_family),
        "pub_years": len(total),
        "pubs_total_k": sum(t.k for t in total),
        "pub_year_anchors": {str(y): year_k[y] for y in (2010, 2015, 2020, 2023)},
        "pub_2010_family_split": [
            [r.family, r.k] for r in sorted(by_family, key=lambda r: r.family) if r.year == 2010
        ],
        "parameter_adoption_rows": len(adoption),
        "parameter_label_count": len(PARAMETERS),
        "parameter_adoption_year_span": [min(adoption_years), max(adoption_years), len(adoption_years)],
        "of_year_2010": next(r.of_year for r in adoption if r.year == 2010),
        "adoption_cell_anchors": {
            "conductance@1986": adoption_cells[("conductance", 1986)],
            "p50@1998": adoption_cells[("p50", 1998)],
            "thermal_threshold@2002": adoption_cells[("thermal_threshold", 2002)],
        },
        "adoption_corpus_totals": {
            label: sum(r.k for r in adoption if r.parameter == label)
            for label in ("p50", "conductance")
        },
        "assay_drift_rows": len(drift),
        "assay_mode_count": len({r.recording_mode for r in drift}),
        "assay_none_bucket_k": sum(r.k for r in drift if r.recording_mode is None),
        "assay_2010_split": {
            str(r.recording_mode): r.k for r in drift if r.year == 2010 and r.k > 0
        },
        "model_drift_rows": len(model),
        "expression_system_count": len({r.expression_system for r in model}),
        "expression_none_bucket_k": sum(r.k for r in model if r.expression_system is None),
        "expression_none_2011": none_2011,
    }


def _mimic_track(engine: Engine) -> dict:
    scores = score_all(engine)
    score_values = [s.score for s in scores]
    reported = Counter()
    for s in scores:
        for st in s.fields.values():
            if st.status == "reported":
                reported[st.field_name] += 1
    categories = {
        cat: [0, 0] for cat in ("stimulus", "recording", "cell_context", "environment", "analysis")
    }
    for s in scores:
        for cat, (rep, app) in s.categories.items():
            categories[cat][0] += rep
            categories[cat][1] += app
    distribution = Counter(s.applicable for s in scores)
    return {
        "applicability_trigger_counts": [
            _scalar(
                engine,
                "SELECT COUNT(*) FROM biophysics_experiment WHERE stimulus_type IN "
                "('INDENTATION','TOUCH','SHEAR_STRESS')",
            ),
            _scalar(
                engine,
                "SELECT COUNT(*) FROM biophysics_experiment WHERE stimulus_type = 'INDENTATION'",
            ),
            _scalar(
                engine,
                "SELECT COUNT(*) FROM biophysics_experiment WHERE recording_mode IN "
                "('CELL_ATTACHED','INSIDE_OUT','OUTSIDE_OUT','WHOLE_CELL',"
                "'PERFORATED_PATCH','PLANAR_PATCH')",
            ),
            _scalar(
                engine,
                "SELECT COUNT(*) FROM biophysics_experiment WHERE recording_mode IS NULL",
            ),
        ],
        "field_reported_counts": {
            name: reported[name] for name in ("recording_mode", "stimulus_type", "temperature_c", "n_cells")
        },
        "score_count": len(scores),
        "score_threshold_counts": {
            "eq_1": sum(1 for v in score_values if v == 1.0),
            "ge_05": sum(1 for v in score_values if v >= 0.5),
            "lt_05": sum(1 for v in score_values if v < 0.5),
            "lt_03": sum(1 for v in score_values if v < 0.3),
        },
        "applicable_distribution": {str(k): v for k, v in distribution.items()},
        "category_totals": categories,
        "category_crossfoot": {
            "reported": sum(v[0] for v in categories.values()),
            "applicable": sum(v[1] for v in categories.values()),
        },
    }


def _site_payloads_track(engine: Engine) -> dict:
    payloads = analysis_payloads(engine)
    blocks = channel_mimic_blocks(engine)
    atlas = payloads["atlas"]
    biophysics = payloads["biophysics"]
    trends = payloads["trends"]
    total = trends["pubs_per_year_total"]
    with engine.connect() as conn:
        cid = conn.execute(text("SELECT id FROM channel WHERE gene_symbol = 'PIEZO1'")).scalar_one()
        n_stim_raw = conn.execute(
            text(
                "SELECT COUNT(*) FROM biophysics_experiment "
                "WHERE channel_id = :cid AND stimulus_type IS NOT NULL"
            ),
            {"cid": cid},
        ).scalar_one()
    piezo = blocks[cid]
    stim = piezo["fields"]["stimulus_type"]
    return {
        "data_freeze_tag": data_freeze_tag(engine),
        "audit_n_records": payloads["audit"]["n_records"],
        "badge_channels": len(blocks),
        "badge_record_total": sum(b["n_records"] for b in blocks.values()),
        "badge_piezo1": {
            "n_records": piezo["n_records"],
            "n_stim_raw": n_stim_raw,
            "reported": piezo["reported"],
            "applicable": piezo["applicable"],
            "stimulus_type_reported": stim["reported"],
            "stimulus_type_applicable": stim["applicable"],
        },
        "atlas_header_counts": [atlas["n_cells"], atlas["n_compounds"], atlas["n_channels"]],
        "atlas_list_lengths": {
            "matrix": len(atlas["matrix"]),
            "selectivity": len(atlas["selectivity"]),
            "delta_p50": len(atlas["delta_p50"]),
        },
        "biophysics_list_lengths": {
            "threshold_meta": len(biophysics["threshold_meta"]),
            "kinetics_atlas": len(biophysics["kinetics_atlas"]),
            "lab_spread": len(biophysics["lab_spread"]),
            "boltzmann_demo": len(biophysics["boltzmann_demo"]),
        },
        "trends_total_rows": len(total),
        "trends_total_k": sum(r["k"] for r in total),
        "trends_first_year": [total[0]["year"], total[0]["k"]],
        "trends_last_year": [total[-1]["year"], total[-1]["k"]],
        "parameter_adoption_rows": len(trends["parameter_adoption"]),
        "parameter_label_count": len({r["parameter"] for r in trends["parameter_adoption"]}),
        "assay_drift_rows": len(trends["assay_drift"]),
        "model_drift_rows": len(trends["model_system_drift"]),
    }

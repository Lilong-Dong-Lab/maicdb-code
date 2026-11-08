"""Artifact-gated pins for the P7 site-payload layer.

Two pin kinds (the P3/P5 convention):

* census-cited pins — numbers trivially re-derivable from
  ``db/maicdb.sqlite`` by the SQL quoted alongside (record counts, the
  freeze tag, per-channel record/stimulus counts, matrix cell count);
* module-output determinism pins — the payload layer's Σ badge
  aggregation, headline row totals, and the serialization rules; their
  INPUTS are owned by the per-module artifact files
  (``test_analysis_{audit,biophysics,atlas,trends}_artifact.py`` pin
  the module numbers with their own censuses — this file pins that the
  SERIALIZED payloads carry those numbers unchanged, so a page and its
  module output cannot disagree).

All numbers derived on ``data-v1.1@037c841f4832``, 2026-11-08, by
execution of ``analysis_payloads`` against the published artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from maicdb.analysis.figures import FIGURES
from maicdb.analysis.mimic import score_all
from maicdb.analysis.site_payloads import (
    analysis_payloads,
    channel_mimic_blocks,
)
from maicdb.query import open_readonly
from tests.test_site_build import run_build

DB_PATH = Path(__file__).parents[1] / "db" / "maicdb.sqlite"

requires_db = pytest.mark.skipif(
    not DB_PATH.exists(), reason=f"published DB not found at {DB_PATH}"
)


@pytest.fixture(scope="module")
def engine():
    eng = open_readonly(DB_PATH)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def payloads(engine):
    return analysis_payloads(engine)


@pytest.fixture(scope="module")
def blocks(engine):
    return channel_mimic_blocks(engine)


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #


@requires_db
def test_all_payloads_share_the_freeze_tag(payloads, engine):
    """Every payload carries the artifact's own release identity, read
    from the same ``db_meta`` row the census cites."""
    with engine.connect() as conn:
        tag = conn.execute(
            text("SELECT value FROM db_meta WHERE key = 'data_freeze_tag'")
        ).scalar()
    assert tag == "data-v1.2@dd49d8e65ac1"
    assert {p["data_freeze_tag"] for p in payloads.values()} == {tag}


@requires_db
def test_payloads_are_json_round_trippable(payloads):
    """Serialization is generic (``dataclasses.asdict``) — the whole
    structure must survive ``json.dumps`` (the site data layer's dump
    path). Tuples (e.g. the atlas ``domains`` field) serialize as
    arrays; a new non-JSON-able field type fails here, not in prod."""
    dumped = json.dumps(payloads, sort_keys=True, indent=2)
    assert json.loads(dumped)["audit"]["n_records"] == payloads["audit"]["n_records"]


# --------------------------------------------------------------------------- #
# audit payload (P3 consumer) — census SQL cited inline
# --------------------------------------------------------------------------- #


@requires_db
def test_audit_payload_census(payloads, engine):
    audit = payloads["audit"]
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM biophysics_experiment")
        ).scalar()
    assert n == 960  # census: SELECT COUNT(*) FROM biophysics_experiment
    assert audit["n_records"] == n == 960
    # module-output determinism pin: the mean per-record score (inputs —
    # join coverage, applicable counts — are pinned by
    # test_analysis_audit_artifact.py)
    assert audit["mean_score"] == pytest.approx(0.42102, abs=1e-4)
    # Σ field totals cross-check against the scorer itself
    scores = score_all(engine)
    assert sum(c["reported"] for c in audit["field_totals"].values()) == sum(
        s.reported for s in scores
    )
    assert sum(c["applicable"] for c in audit["field_totals"].values()) == sum(
        s.applicable for s in scores
    )


@requires_db
def test_audit_payload_keeps_the_compliance_property(payloads):
    """The disclosed serialization rule: ``HeatmapCell.compliance`` is a
    property, which ``asdict`` skips — the payload adds it explicitly,
    preserving the None-when-applicable-0 contract in JSON too."""
    for cell in payloads["audit"]["field_totals"].values():
        assert "compliance" in cell
        if cell["applicable"] == 0:
            assert cell["compliance"] is None


# --------------------------------------------------------------------------- #
# channel MIMIC badge blocks (Σ aggregation, field level)
# --------------------------------------------------------------------------- #


@requires_db
def test_badge_blocks_cross_check_the_scorer(payloads, blocks, engine):
    """12 blocks (one per channel), Σ n_records = 960 = the record
    census, and the Σ reported/applicable totals equal the scorer's
    own — the field-level badge cannot invent or lose a count."""
    scores = score_all(engine)
    assert len(blocks) == 12
    assert sum(b["n_records"] for b in blocks.values()) == 960
    assert sum(b["reported"] for b in blocks.values()) == sum(
        s.reported for s in scores
    )
    assert sum(b["applicable"] for b in blocks.values()) == sum(
        s.applicable for s in scores
    )


@requires_db
def test_badge_block_piezo1_anchor(blocks, engine):
    """PIEZO1 census (SQL cited) and the Σ-derived badge score:
    160 records; 1259 reported / 2649 applicable → 47.5%."""
    with engine.connect() as conn:
        piezo1_id = conn.execute(
            text("SELECT id FROM channel WHERE gene_symbol = 'PIEZO1'")
        ).scalar()
        n_records = conn.execute(
            text(
                "SELECT COUNT(*) FROM biophysics_experiment "
                "WHERE channel_id = :cid"
            ),
            {"cid": piezo1_id},
        ).scalar()
        n_stim = conn.execute(
            text(
                "SELECT COUNT(*) FROM biophysics_experiment "
                "WHERE channel_id = :cid AND stimulus_type IS NOT NULL"
            ),
            {"cid": piezo1_id},
        ).scalar()
    assert n_records == 160  # census: COUNT for gene_symbol = 'PIEZO1'
    assert n_stim == 160
    b = blocks[piezo1_id]
    assert b["n_records"] == 160
    # module-output determinism pins (Σ over the channel's 160 records;
    # per-field inputs pinned by test_analysis_audit_artifact.py)
    assert b["reported"] == 1259
    assert b["applicable"] == 2649
    assert b["score"] == pytest.approx(1259 / 2649)
    # the badge's per-field census: every PIEZO1 record carries
    # stimulus_type (it is how records qualify), never a probe field
    # without an indentation stimulus (ADR-0005)
    assert b["fields"]["stimulus_type"] == {"reported": 160, "applicable": 160}


# --------------------------------------------------------------------------- #
# atlas / biophysics / trends payloads — headline counts
# --------------------------------------------------------------------------- #


@requires_db
def test_atlas_payload_census(payloads, engine):
    at = payloads["atlas"]
    with engine.connect() as conn:
        cells = conn.execute(
            text(
                "SELECT COUNT(*) FROM (SELECT DISTINCT compound_id, "
                "channel_id FROM bioactivity)"
            )
        ).scalar()
        compounds = conn.execute(
            text("SELECT COUNT(DISTINCT compound_id) FROM bioactivity")
        ).scalar()
        genes = conn.execute(
            text(
                "SELECT COUNT(DISTINCT ch.gene_symbol) FROM bioactivity b "
                "JOIN channel ch ON b.channel_id = ch.id"
            )
        ).scalar()
    # census: DISTINCT (compound_id, channel_id) cells / compounds / genes
    assert (cells, compounds, genes) == (73, 69, 9)
    assert at["n_cells"] == cells == 73
    assert at["n_compounds"] == compounds == 69
    assert at["n_channels"] == genes == 9
    # matrix ↔ headline identity: the counts are derived FROM the matrix
    assert len(at["matrix"]) == at["n_cells"]
    assert len(at["selectivity"]) == 66
    assert len(at["delta_p50"]) == 17
    # selectivity rows are a subset surface of the matrix compounds
    assert {r["compound_name"] for r in at["selectivity"]} <= {
        r["compound_name"] for r in at["matrix"]
    }


@requires_db
def test_biophysics_payload_census(payloads):
    """Row counts per block (module-output pins; the P4 artifact file
    owns the per-block censuses and the D–L numbers themselves)."""
    bio = payloads["biophysics"]
    assert len(bio["threshold_meta"]) == 10
    assert len(bio["kinetics_atlas"]) == 23
    assert len(bio["lab_spread"]) == 9
    assert len(bio["boltzmann_demo"]) == 4
    for row in bio["threshold_meta"]:
        assert isinstance(row["identifiable"], bool)
        # the P4 inference gate: CI/PI exist iff the cell is identifiable
        # (≥1 cluster with n ≥ 2) AND k ≥ 2 — a k=1 cell stays descriptive
        # even when its flag is True (K2P PRESSURE_CLAMP, TMC at v1.0)
        inferential = row["identifiable"] and row["k"] >= 2
        if inferential:
            assert row["ci_mmhg"] is not None and len(row["ci_mmhg"]) == 2
            assert row["ci_mmhg"][0] < row["ci_mmhg"][1]
            assert row["pi_mmhg"][0] <= row["ci_mmhg"][0]
            assert row["pi_mmhg"][1] >= row["ci_mmhg"][1]
        else:
            assert row["ci_mmhg"] is None and row["pi_mmhg"] is None


@requires_db
def test_trends_payload_census(payloads):
    """Row counts and the year-series totals (module-output pins; the
    P6 artifact file owns the censuses). Σ k over years is 188, NOT the
    216-publication census: years without a resolvable publication year
    never enter the series and a publication counts once per year it
    appears in (the disclosed not-additive rule, P6 module docstring)."""
    tr = payloads["trends"]
    tot = tr["pubs_per_year_total"]
    assert len(tot) == 33
    assert sum(r["k"] for r in tot) == 188
    assert (tot[0]["year"], tot[0]["k"]) == (1986, 1)
    assert (tot[-1]["year"], tot[-1]["k"]) == (2026, 6)
    assert len(tr["parameter_adoption"]) == 561
    assert len({r["parameter"] for r in tr["parameter_adoption"]}) == 17
    assert len(tr["assay_drift"]) == 330
    assert len(tr["model_system_drift"]) == 258


# --------------------------------------------------------------------------- #
# the build emits the P7 deliverables (real build, read-only)
# --------------------------------------------------------------------------- #


@requires_db
def test_build_emits_analysis_pages_payloads_and_figures(tmp_path):
    """The full P7 surface, from a real build: four payload JSONs under
    ``_data/analysis/``, the five analysis pages per locale tree under
    the render root (``_site/``), and the five-figure set rendered into
    each tree."""
    out = tmp_path / "out"
    run_build(out)
    site = out / "_site"
    tracks = {"audit", "biophysics", "atlas", "trends"}
    assert {p.stem for p in (out / "_data" / "analysis").glob("*.json")} == tracks
    pages = [
        "analysis/index.html",
        "analysis/audit/index.html",
        "analysis/atlas/index.html",
        "analysis/trends/index.html",
        "analysis/methods/index.html",
    ]
    for tree in (site, site / "zh"):
        for rel in pages:
            assert (tree / rel).is_file(), rel
        figs = {p.stem for p in (tree / "analysis" / "figures").glob("*.png")}
        assert figs == set(FIGURES)
    # the audit page shows numbers with their release identity
    audit_html = (site / "analysis" / "audit" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "data-v1.2@dd49d8e65ac1" in audit_html


@requires_db
def test_channel_card_carries_the_mimic_badge(tmp_path):
    """PIEZO1's card renders the badge: the Σ score (47.5%), the
    reported/applicable pair (1259/2649) and the record count (160)."""
    out = tmp_path / "out"
    run_build(out)
    card = (out / "_site" / "channels" / "piezo1" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'class="mimic-badge"' in card
    assert "1259/2649 · 160 records" in card

"""Tests for :mod:`maicdb.query` — the M1 read-only query library + CLI.

Real-data provenance: every fixture value below is pinned against the
published artifact ``db/maicdb.sqlite`` (schema 0.2.0, data freeze
``data-v1.0``, vault head ``5a8ff0e``) or the vault data notes
(``shared/assignments/data/MAICDB_data_notes.md`` — §2 counts, §6.3 small
families, §6.7 frozen wording). Census SQL for each pinned number is quoted
in the test docstring so any drift is re-derivable.

Tests auto-skip when the published DB is absent (mirrors ``requires_vault``
in ``test_loader.py``).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import sqlalchemy as sa

from maicdb.query import channel_card, open_readonly

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "db" / "maicdb.sqlite"

#: Captured at module import (before any test runs) — the final test
#: re-hashes the artifact to prove the whole query suite never touched it.
_DB_HASH_BEFORE = (
    hashlib.sha256(DB_PATH.read_bytes()).hexdigest() if DB_PATH.exists() else None
)

requires_db = pytest.mark.skipif(
    not DB_PATH.exists(), reason=f"published DB not found at {DB_PATH}"
)

pytestmark = requires_db


@pytest.fixture(scope="module")
def engine():
    eng = open_readonly(DB_PATH)
    yield eng
    eng.dispose()


def test_open_readonly_connects_and_blocks_writes(engine):
    """``mode=ro`` URI: reads work, writes raise.

    12 channels: data notes §6.4 ("NULL for 6 of 12 channels"); census
    ``SELECT gene_symbol, COUNT(*) FROM channel GROUP BY 1`` on data-v1.0
    returns 12 single-organism rows.
    """
    with engine.connect() as conn:
        n_channels = conn.execute(sa.text("SELECT COUNT(*) FROM channel")).scalar_one()
        assert n_channels == 12
    with pytest.raises(sa.exc.OperationalError):
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM channel"))


def test_channel_card_identity_and_p50_rows(engine):
    """Channel card: identity block + parameter rows with full evidence chain.

    Pinned against the artifact (data-v1.0, vault head 5a8ff0e):
    * identity — ``SELECT gene_symbol, family, uniprot_accession, organism
      FROM channel WHERE gene_symbol='PIEZO1'`` → PIEZO / Q92508 /
      Homo sapiens.
    * 56 P50 rows — data notes §6.1 ("PIEZO1: 26 of 56 P50 rows negative").
    * the PIEZO1-EX-00005 row — ``SELECT … WHERE measurement_id=
      'PIEZO1-EX-00005'``: p50 −28.0 mmHg, as-reported pair "-28.0"/"mm Hg"
      (pre-normalization spelling), quote/location/confidence/n verbatim.
    """
    card = channel_card(engine, "PIEZO1", parameters=["p50"])

    assert card["gene"]["gene_symbol"] == "PIEZO1"
    assert card["gene"]["family"] == "PIEZO"
    assert card["gene"]["uniprot_accession"] == "Q92508"
    assert card["gene"]["organism"] == "Homo sapiens"

    p50 = card["parameters"]["p50"]
    assert p50["n_rows"] == 56

    row = next(r for r in p50["rows"] if r["measurement_id"] == "PIEZO1-EX-00005")
    assert row["value"] == -28.0
    assert row["unit"] == "mmHg"
    assert row["value_as_reported"] == "-28.0"
    assert row["unit_as_reported"] == "mm Hg"
    assert row["evidence_quote"].startswith(
        "The current-pressure relationship is characterized"
    )
    assert row["evidence_location"] == "Results (Fig. 1F)"
    assert row["confidence"] == "high"
    assert row["n"] == "21"

    # Evidence chain is never optional on a rendered number.
    assert all(r["measurement_id"] and r["evidence_quote"] for r in p50["rows"])


def test_channel_card_unknown_gene_is_clean_error(engine):
    """Unknown gene: a clean lookup error, not an empty card (HANDOFF §5)."""
    from maicdb.query import UnknownGeneError

    with pytest.raises(UnknownGeneError, match="PIEZO9"):
        channel_card(engine, "PIEZO9")


def test_channel_card_zero_row_parameter_reported_not_hidden(engine):
    """PIEZO2 has zero threshold rows of any modality — the blocks stay in
    the card, flagged empty (data notes §6.3: "PIEZO2 has 28 rows and zero
    P50"; census: 0 p50/t50/x50 rows, 15 tau_inact rows of the 28 total).
    """
    card = channel_card(engine, "PIEZO2")
    for threshold in ("p50", "t50", "x50"):
        assert card["parameters"][threshold]["n_rows"] == 0
        assert card["parameters"][threshold]["rows"] == []
    assert card["parameters"]["tau_inact"]["n_rows"] == 15


def test_frozen_layer_wording(engine):
    """HANDOFF §3 rule 3, tested by semantics:

    * PIEZO1/PIEZO2 cards carry the §6.7 boilerplate **verbatim**;
    * a non-frozen gene's card carries no disclosure;
    * no card ever renders an affirmative verification status — there is
      no ``verification``/``verified`` field anywhere in the payload (the
      boilerplate itself contains "not been re-verified", so this is an
      assertion about fields, not a substring hunt).
    """

    def keys_of(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys_of(v)
        elif isinstance(obj, list):
            for item in obj:
                yield from keys_of(item)

    from maicdb.query import FROZEN_LAYER_DISCLOSURE, FROZEN_GENE_SYMBOLS

    assert FROZEN_GENE_SYMBOLS == frozenset({"PIEZO1", "PIEZO2"})
    assert FROZEN_LAYER_DISCLOSURE == (
        "PIEZO1/PIEZO2 rows are frozen-layer data whose evidence quotes "
        "have not been re-verified; verification percentages cover the "
        "10 non-frozen layers only."
    )

    for gene in ("PIEZO1", "PIEZO2"):
        card = channel_card(engine, gene, parameters=["tau_inact"])
        assert card["frozen_layer_disclosure"] == FROZEN_LAYER_DISCLOSURE

    card = channel_card(engine, "TRAAK", parameters=["tau_inact"])
    assert "frozen_layer_disclosure" not in card
    assert not [k for k in keys_of(card) if k.lower().startswith("verif")]


def test_parameter_comparison_per_unit_aggregates(engine):
    """Gene × parameter comparison: count/min/median/max **per stored unit**,
    zero-count genes included (computed from the channel table, never
    hardcoded).

    Pinned (data notes §2 / A1 panel p2a expectations, census on data-v1.0):
    * 152 P50 rows = 148 mmHg + 4 psi; the 4 psi rows are all MscL
      (values 1.0, 1.3, 1.6, 3.6 → median 1.45); MscL also carries 17 mmHg
      p50 rows (census ``SELECT p50_unit, COUNT(*) … WHERE gene_symbol=
      'MscL'`` → mmHg 17, psi 4).
    * Zero-threshold genes: PIEZO2, TRESK (data notes §6.3) and ASIC
      (census ``SELECT c.gene_symbol … WHERE p50/t50/x50 NOT NULL`` lists
      only MscL, MscS, OSCA, PIEZO1, TMC, TRAAK, TREK-1, TREK-2, TRPV4).
    """
    from maicdb.query import parameter_comparison

    cmp_rows = parameter_comparison(engine, "p50")

    # No cross-unit pooling: every counted row carries a stored unit.
    assert all(r["unit"] is not None for r in cmp_rows if r["count"] > 0)

    by_gene_unit = {(r["gene"], r["unit"]): r for r in cmp_rows}
    assert sum(r["count"] for r in cmp_rows) == 152
    assert by_gene_unit[("MscL", "psi")]["count"] == 4
    assert by_gene_unit[("MscL", "psi")]["min"] == 1.0
    assert by_gene_unit[("MscL", "psi")]["median"] == 1.45
    assert by_gene_unit[("MscL", "psi")]["max"] == 3.6
    assert by_gene_unit[("MscL", "mmHg")]["count"] == 17

    # All 12 genes reported; the three zero-threshold genes carry empty stats.
    genes = {r["gene"] for r in cmp_rows}
    assert len(genes) == 12
    for zero_gene in ("ASIC", "PIEZO2", "TRESK"):
        rows = [r for r in cmp_rows if r["gene"] == zero_gene]
        assert len(rows) == 1
        assert rows[0]["count"] == 0
        assert rows[0]["unit"] is None
        assert rows[0]["median"] is None

    # Deterministic ordering: gene asc, then unit.
    ordered = sorted(cmp_rows, key=lambda r: (r["gene"], r["unit"] or ""))
    assert [id(r) for r in cmp_rows] == [id(r) for r in ordered]


def test_parameter_comparison_fixed_unit_parameter(engine):
    """Fixed-unit parameters aggregate under their baked-in unit (τ in ms).

    93 tau_inact rows: census ``SELECT COUNT(*) … WHERE tau_inact_ms IS NOT
    NULL`` on data-v1.0 (HANDOFF §2 example parameter).
    """
    from maicdb.query import parameter_comparison

    cmp_rows = parameter_comparison(engine, "tau_inact")
    assert sum(r["count"] for r in cmp_rows) == 93
    assert all(r["unit"] in (None, "ms") for r in cmp_rows)
    with pytest.raises(Exception):
        parameter_comparison(engine, "not_a_parameter")


def test_provenance_full_evidence_row(engine):
    """``provenance(measurement_id)`` returns the whole evidence row.

    Pinned: PIEZO1-EX-00005 (card test census) — quote prefix, location
    "Results (Fig. 1F)", confidence "high", n "21", and the row's
    ``maicdb_id`` is present. Unknown id → None (clean miss).
    """
    from maicdb.query import provenance

    ev = provenance(engine, "PIEZO1-EX-00005")
    assert ev is not None
    assert ev["measurement_id"] == "PIEZO1-EX-00005"
    assert ev["maicdb_id"]
    assert ev["evidence_quote"].startswith(
        "The current-pressure relationship is characterized"
    )
    assert ev["evidence_location"] == "Results (Fig. 1F)"
    assert ev["confidence"] == "high"
    assert ev["n"] == "21"
    assert ev["extractor_note"]

    assert provenance(engine, "NO-SUCH-MEASUREMENT") is None


def test_export_csv_deterministic_with_stderr_disclosure(engine, capsys):
    """CSV export: pure data on stdout, §6.7 boilerplate on stderr (p50
    includes PIEZO1 rows → disclosure is mandatory), byte-identical across
    calls. 13 lines of data: 12 genes + MscL's second (psi) unit row.
    """
    from maicdb.query import FROZEN_LAYER_DISCLOSURE, export

    csv_a = export(engine, "p50", format="csv")
    err_a = capsys.readouterr().err
    csv_b = export(engine, "p50", format="csv")
    capsys.readouterr()

    assert csv_a == csv_b  # byte-identical (rule 6)
    lines = csv_a.splitlines()
    assert lines[0] == "gene,family,parameter,unit,count,min,median,max"
    assert len(lines) == 14  # header + 13 data rows
    assert err_a.strip() == FROZEN_LAYER_DISCLOSURE

    import csv as csv_mod

    rows = list(csv_mod.reader(lines[1:]))
    assert all(len(r) == 8 for r in rows)


def test_export_json_round_trip_and_disclosure(engine):
    """JSON export: round-trips through json.loads, embeds the frozen-layer
    disclosure as a field (p50 touches PIEZO1), and is byte-stable.
    """
    import json

    from maicdb.query import FROZEN_LAYER_DISCLOSURE, export

    payload_a = export(engine, "p50", format="json")
    payload_b = export(engine, "p50", format="json")
    assert payload_a == payload_b

    doc = json.loads(payload_a)
    assert doc["parameter"] == "p50"
    assert doc["frozen_layer_disclosure"] == FROZEN_LAYER_DISCLOSURE
    assert sum(r["count"] for r in doc["rows"]) == 152


# --------------------------------------------------------------------------- #
# CLI — maicdb-query (channel / export / provenance)
# --------------------------------------------------------------------------- #
CLI_ARGS = ["--db", str(DB_PATH)]


def test_cli_channel_card(capsys):
    """``maicdb-query channel PIEZO1 --parameter p50`` — the HANDOFF §2
    first-consumer target: identity + P50 rows with per-row provenance,
    frozen disclosure inline (human-readable card, stdout is the product).
    """
    from maicdb.query import main

    rc = main(["channel", "PIEZO1", "--parameter", "p50", *CLI_ARGS])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PIEZO1" in out
    assert "Q92508" in out
    assert "-28.0 mmHg" in out
    assert "mm Hg" in out  # as-reported pair
    assert "PIEZO1-EX-00005" in out
    assert "Results (Fig. 1F)" in out
    assert "not been re-verified" in out  # §6.7 boilerplate rendered

    rc2 = main(["channel", "PIEZO1", "--parameter", "p50", *CLI_ARGS])
    assert capsys.readouterr().out == out  # byte-identical (rule 6)


def test_cli_channel_unknown_gene_clean_error(capsys):
    from maicdb.query import main

    rc = main(["channel", "PIEZO9", *CLI_ARGS])
    captured = capsys.readouterr()
    assert rc != 0
    assert "unknown gene" in captured.err
    assert "PIEZO2" in captured.err  # known-gene list is computed, printed
    assert captured.out == ""


def test_cli_export_matches_library_bytes(capsys):
    """``maicdb-query export --parameter tau_inact --format csv`` — stdout
    is byte-identical to the library export and stable across runs (the
    numbers behind the A1 panels).
    """
    from maicdb.query import export, main, open_readonly

    rc = main(["export", "--parameter", "tau_inact", "--format", "csv", *CLI_ARGS])
    out = capsys.readouterr().out
    assert rc == 0

    eng = open_readonly(DB_PATH)
    expected = export(eng, "tau_inact", format="csv")
    eng.dispose()
    assert out == expected

    main(["export", "--parameter", "tau_inact", "--format", "csv", *CLI_ARGS])
    assert capsys.readouterr().out == out


def test_cli_provenance(capsys):
    from maicdb.query import main

    rc = main(["provenance", "PIEZO1-EX-00005", *CLI_ARGS])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PIEZO1-EX-00005" in out
    assert "Results (Fig. 1F)" in out
    assert "The current-pressure relationship is characterized" in out

    rc = main(["provenance", "NO-SUCH-MEASUREMENT", *CLI_ARGS])
    captured = capsys.readouterr()
    assert rc != 0
    assert "NO-SUCH-MEASUREMENT" in captured.err


def test_db_artifact_untouched_by_whole_suite():
    """HANDOFF §3 rule 1: the shipped artifact is never mutated — the DB
    file hash is unchanged by the entire query test suite."""
    import hashlib

    assert _DB_HASH_BEFORE is not None
    assert hashlib.sha256(DB_PATH.read_bytes()).hexdigest() == _DB_HASH_BEFORE

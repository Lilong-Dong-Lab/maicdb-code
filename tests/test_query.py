"""Tests for :mod:`maicdb.query` — the M1 read-only query library + CLI.

Real-data provenance: every fixture value below is pinned against the
published artifact ``db/maicdb.sqlite`` (schema 0.2.0, data freeze
``data-v1.0``, vault head ``5a8ff0e``) or the vault data notes
(``shared/assignments/data/MAICDB_data_notes.md`` — §2 counts, §6.3 small
families, §6.7 frozen wording). Census SQL for each pinned number is quoted
in the test docstring so any drift is re-derivable.

Conscious deviation from the CLAUDE.md fixture-citation rule (vault CSV
path / raw JSON): the pins here are *aggregate counts and exemplar rows*,
not extracted cells, so they cite the data-notes section that asserts the
same number plus the census SQL that re-derives it against any copy of the
artifact — stronger against loader drift than a raw-JSON pointer, and it
keeps the tests runnable without a vault checkout (they auto-skip only on
a missing DB, mirroring ``requires_vault`` in ``test_loader.py``).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import sqlalchemy as sa

from maicdb.query import (
    FROZEN_GENE_SYMBOLS,
    FROZEN_LAYER_DISCLOSURE,
    RATIO_MEDIAN_NOTE,
    AmbiguousGeneError,
    UnknownGeneError,
    UnknownParameterError,
    channel_card,
    export,
    main,
    open_readonly,
    parameter_comparison,
    provenance,
)

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

    # Nullable evidence fields stay present as None in the payload — two of
    # the 56 PIEZO1 p50 rows have no extractor note (census: 00041/00042;
    # ``SELECT measurement_id … WHERE extractor_note IS NULL``); the CLI
    # renders them explicitly (see the CLI card test).
    row41 = next(r for r in p50["rows"] if r["measurement_id"] == "PIEZO1-EX-00041")
    assert row41["extractor_note"] is None


def test_channel_card_unknown_gene_is_clean_error(engine):
    """Unknown gene: a clean lookup error, not an empty card (HANDOFF §5)."""
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
    * no payload ever renders an affirmative verification status — no
      ``verification``/``verified`` KEY anywhere, and no scalar VALUE that
      *is* a status (``{"status": "Verified"}`` must fail). Prose may
      legitimately contain the word (82 evidence quotes/extractor notes in
      data-v1.0 do), so values are matched as exact statuses, not
      substrings — the boilerplate's own "not been re-verified" passes.
    * the same invariant holds on the provenance and comparison surfaces.
    """
    # A value that *is* an affirmative verification status.
    affirmative_statuses = {
        "verified", "re-verified", "verification: verified",
        "status: verified", "verified: true",
    }

    def affirmative_hits(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower().startswith("verif"):
                    yield f"key:{k}"
                yield from affirmative_hits(v)
        elif isinstance(obj, list):
            for item in obj:
                yield from affirmative_hits(item)
        elif isinstance(obj, str) and obj.strip().lower() in affirmative_statuses:
            yield f"value:{obj}"

    # Walker semantics self-test: statuses caught, prose not.
    assert list(affirmative_hits({"status": "Verified"}))
    assert list(affirmative_hits({"quality": "VERIFIED"}))
    assert not list(affirmative_hits({"note": "we verified the recording"}))
    assert not list(affirmative_hits({"note": "not been re-verified"}))

    assert FROZEN_GENE_SYMBOLS == frozenset({"PIEZO1", "PIEZO2"})
    assert FROZEN_LAYER_DISCLOSURE == (
        "PIEZO1/PIEZO2 rows are frozen-layer data whose evidence quotes "
        "have not been re-verified; verification percentages cover the "
        "10 non-frozen layers only."
    )

    for gene in ("PIEZO1", "PIEZO2"):
        card = channel_card(engine, gene, parameters=["tau_inact"])
        assert card["frozen_layer_disclosure"] == FROZEN_LAYER_DISCLOSURE
        # The no-verification-status walker runs on the PIEZO payloads too —
        # the rule is about piezo rows specifically.
        assert not list(affirmative_hits(card))

    card = channel_card(engine, "TRAAK", parameters=["tau_inact"])
    assert "frozen_layer_disclosure" not in card
    assert not list(affirmative_hits(card))

    assert not list(affirmative_hits(provenance(engine, "PIEZO1-EX-00005")))
    assert not list(affirmative_hits(parameter_comparison(engine, "tau_inact")))


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
    cmp_rows = parameter_comparison(engine, "p50")

    # No cross-unit pooling: p50's counted rows each carry one stored unit
    # (data-v1.0 has zero NULL-unit p50 rows — census ``SELECT COUNT(*) …
    # WHERE p50_value IS NOT NULL AND p50_unit IS NULL`` → 0; NULL-unit
    # buckets are pinned in the null-unit test below).
    assert all(isinstance(r["unit"], str) for r in cmp_rows if r["count"] > 0)

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

    # Deterministic ordering: gene asc, then unit under a total order
    # (None first, then empty string, then named units).
    ordered = sorted(
        cmp_rows, key=lambda r: (r["gene"], r["unit"] is not None, r["unit"] or "")
    )
    assert [id(r) for r in cmp_rows] == [id(r) for r in ordered]

    # Rule 2: every aggregate is traceable — ids listed, sorted with values.
    msc_psi = by_gene_unit[("MscL", "psi")]
    assert len(msc_psi["measurement_ids"]) == 4
    assert "MSCL-EX-00037" in msc_psi["measurement_ids"]
    zero = by_gene_unit[("PIEZO2", None)]
    assert zero["measurement_ids"] == []

    # Rule 3 on the row surface: PIEZO rows carry the §6.7 boilerplate
    # (counted and zero rows alike — library consumers render rows
    # standalone); non-frozen rows do not.
    assert (
        by_gene_unit[("PIEZO1", "mmHg")]["frozen_layer_disclosure"]
        == FROZEN_LAYER_DISCLOSURE
    )
    assert zero["frozen_layer_disclosure"] == FROZEN_LAYER_DISCLOSURE
    assert "frozen_layer_disclosure" not in msc_psi


def test_parameter_comparison_fixed_unit_parameter(engine):
    """Fixed-unit parameters aggregate under their baked-in unit (τ in ms).

    93 tau_inact rows: census ``SELECT COUNT(*) … WHERE tau_inact_ms IS NOT
    NULL`` on data-v1.0 (HANDOFF §2 example parameter).
    """
    cmp_rows = parameter_comparison(engine, "tau_inact")
    assert sum(r["count"] for r in cmp_rows) == 93
    assert all(r["unit"] in (None, "ms") for r in cmp_rows)
    with pytest.raises(UnknownParameterError):
        parameter_comparison(engine, "not_a_parameter")


def test_parameter_comparison_null_unit_rows_reported_not_erased(engine):
    """NULL-unit rows aggregate under ``unit=None`` — reported, never erased
    (rule 5). Before the fix these rows were silently dropped and every
    gene exported a false ``count=0``.

    Pinned (census on data-v1.0):
    * ``slope`` — 13 rows over 6 genes (ASIC 1, MscL 3, PIEZO1 2, TRAAK 2,
      TREK-1 3, TREK-2 2), ``slope_unit`` NULL on all 13
      (``SELECT c.gene_symbol, COUNT(*) … WHERE b.slope IS NOT NULL
      GROUP BY 1``).
    * ``ion_selectivity_ratio`` — 66 rows over 7 genes; the parameter has
      no unit column at all (registry ``unit_column=None``).
    * ``threshold_fold_shift`` — MscL carries BOTH buckets (4 rows unit
      NULL + 4 rows "%"), proving a NULL unit never pools with a stored one.
    * direction-blind ratios (``ratio_direction`` NULL on every row —
      loader-mapping §3.4): the median is OMITTED with a note (A1 panel p4
      semantics: direction-unstated groups report count/min/max only);
      fixed-unit parameters keep their medians and carry no note.
    """
    slope_rows = parameter_comparison(engine, "slope")
    assert sum(r["count"] for r in slope_rows) == 13
    assert {r["gene"] for r in slope_rows if r["count"] > 0} == {
        "ASIC", "MscL", "PIEZO1", "TRAAK", "TREK-1", "TREK-2"
    }
    assert all(r["unit"] is None for r in slope_rows if r["count"] > 0)
    # Deterministic ordering still holds with NULL units in play.
    ordered = sorted(
        slope_rows, key=lambda r: (r["gene"], r["unit"] is not None, r["unit"] or "")
    )
    assert [id(r) for r in slope_rows] == [id(r) for r in ordered]

    ion_rows = parameter_comparison(engine, "ion_selectivity_ratio")
    assert sum(r["count"] for r in ion_rows) == 66
    counted = [r for r in ion_rows if r["count"] > 0]
    assert {r["gene"] for r in counted} == {
        "ASIC", "MscS", "OSCA", "PIEZO1", "TMC", "TREK-2", "TRPV4"
    }
    # Every counted NULL-unit aggregate stays traceable (rule 2).
    assert all(r["unit"] is None and r["measurement_ids"] for r in counted)
    # Direction-blind medians omitted, min/max kept (ASIC census:
    # min 0.113, max 14.0 over 11 rows).
    asic = next(r for r in ion_rows if r["gene"] == "ASIC")
    assert asic["count"] == 11 and asic["min"] == 0.113 and asic["max"] == 14.0
    assert asic["median"] is None
    assert asic["note"] == RATIO_MEDIAN_NOTE
    ca_rows = parameter_comparison(engine, "ca_permeability")
    assert all(
        r["median"] is None and r["note"] == RATIO_MEDIAN_NOTE
        for r in ca_rows
        if r["count"] > 0
    )

    tau_rows = parameter_comparison(engine, "tau_inact")
    assert all("note" not in r for r in tau_rows)
    assert all(r["median"] is not None for r in tau_rows if r["count"] > 0)

    tfs = {
        (r["gene"], r["unit"]): r
        for r in parameter_comparison(engine, "threshold_fold_shift")
    }
    assert tfs[("MscL", None)]["count"] == 4
    assert tfs[("MscL", "%")]["count"] == 4


def test_provenance_full_evidence_row(engine):
    """``provenance(measurement_id)`` returns the whole evidence row.

    Pinned: PIEZO1-EX-00005 (card test census) — quote prefix, location
    "Results (Fig. 1F)", confidence "high", n "21", and the row's
    ``maicdb_id`` is present. Unknown id → None (clean miss).
    """
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

    # Nullable evidence fields stay None in the payload and render
    # explicitly: 445 biophysics rows have n IS NULL (census
    # ``SELECT COUNT(*) … WHERE n IS NULL``; ASIC-00042 is the first).
    ev_no_n = provenance(engine, "ASIC-00042")
    assert ev_no_n["n"] is None

    assert provenance(engine, "NO-SUCH-MEASUREMENT") is None


def test_provenance_frozen_layer_disclosure(engine):
    """§6.7 wording rule follows the evidence row itself (HANDOFF §3 rule
    3): a PIEZO measurement's provenance carries the boilerplate verbatim;
    a non-frozen gene's does not; and no affirmative verification status
    is rendered (field-level check, not a substring hunt).
    """
    ev = provenance(engine, "PIEZO1-EX-00005")
    assert ev["frozen_layer_disclosure"] == FROZEN_LAYER_DISCLOSURE
    assert not [k for k in ev if k.lower().startswith("verif")]

    ev_msc = provenance(engine, "MSCL-EX-00037")  # MscL — non-frozen
    assert ev_msc is not None
    assert "frozen_layer_disclosure" not in ev_msc
    assert not [k for k in ev_msc if k.lower().startswith("verif")]


def test_export_csv_deterministic_with_stderr_disclosure(engine, capsys):
    """CSV export: pure data on stdout, §6.7 boilerplate + sign-convention
    note on stderr (p50 is a threshold parameter and includes PIEZO1 rows),
    byte-identical across calls. 13 data lines: 12 genes + MscL's second
    (psi) unit row; every aggregate row carries its measurement_ids.
    """
    csv_a = export(engine, "p50", format="csv")
    err_a = capsys.readouterr().err
    csv_b = export(engine, "p50", format="csv")
    capsys.readouterr()

    assert csv_a == csv_b  # byte-identical (rule 6)
    lines = csv_a.splitlines()
    assert lines[0] == (
        "gene,family,parameter,unit,count,min,median,max,measurement_ids,note"
    )
    assert len(lines) == 14  # header + 13 data rows
    assert FROZEN_LAYER_DISCLOSURE in err_a
    assert "sign convention" in err_a and "as recorded" in err_a

    import csv as csv_mod

    rows = list(csv_mod.reader(lines[1:]))
    assert all(len(r) == 10 for r in rows)
    # Every counted aggregate row is traceable: ids listed, ;-joined.
    msc_psi = next(r for r in rows if r[0] == "MscL" and r[3] == "psi")
    assert msc_psi[8].count(";") == 3  # 4 ids
    assert "MSCL-EX-00037" in msc_psi[8]


def test_export_json_round_trip_and_disclosure(engine):
    """JSON export: round-trips through json.loads, embeds the frozen-layer
    disclosure and the threshold sign-convention note as fields (p50
    touches PIEZO1), and is byte-stable.
    """
    import json

    payload_a = export(engine, "p50", format="json")
    payload_b = export(engine, "p50", format="json")
    assert payload_a == payload_b

    doc = json.loads(payload_a)
    assert doc["parameter"] == "p50"
    assert doc["frozen_layer_disclosure"] == FROZEN_LAYER_DISCLOSURE
    assert "as recorded" in doc["sign_convention"]
    assert sum(r["count"] for r in doc["rows"]) == 152
    assert all(isinstance(r["measurement_ids"], list) for r in doc["rows"])


def test_export_discloses_frozen_even_on_zero_count_piezo_rows(engine, capsys):
    """``_touches_frozen`` counts zero-row PIEZO channels too: tau_act has
    no PIEZO1/PIEZO2 rows in data-v1.0 (census ``SELECT COUNT(*) … WHERE
    tau_act_ms IS NOT NULL AND gene_symbol IN ('PIEZO1','PIEZO2')`` → 0),
    yet the export lists their count=0 rows — so the JSON carries the
    disclosure field, the PIEZO zero rows carry it on the row itself, and
    the CSV prints the §6.7 boilerplate to stderr (same policy as a
    zero-row PIEZO2 card).
    """
    import json

    doc = json.loads(export(engine, "tau_act", format="json"))
    assert doc["frozen_layer_disclosure"] == FROZEN_LAYER_DISCLOSURE
    piezo_rows = [r for r in doc["rows"] if r["gene"] in FROZEN_GENE_SYMBOLS]
    assert len(piezo_rows) == 2
    assert all(
        r["count"] == 0 and r["frozen_layer_disclosure"] == FROZEN_LAYER_DISCLOSURE
        for r in piezo_rows
    )
    assert "sign_convention" not in doc  # tau_act is not a threshold parameter

    export(engine, "tau_act", format="csv")
    err = capsys.readouterr().err
    assert FROZEN_LAYER_DISCLOSURE in err
    assert "sign convention" not in err


def test_multi_organism_gene_symbol_fails_loudly():
    """The schema splits one gene across organisms (UNIQUE(gene_symbol,
    organism_taxid) — see test_schema's two-organism PIEZO1 split). The
    data-v1.0 artifact has none, but a future artifact may: the query layer
    must not silently pick one channel (card) or pool both organisms'
    measurements (comparison) — both surfaces raise AmbiguousGeneError.
    """
    from maicdb.enums import Family
    from maicdb.models import Base, Channel

    eng = sa.create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(
            sa.insert(Channel),
            [
                {
                    "maicdb_id": "MAIC:CH:TST01",
                    "gene_symbol": "PIEZO1",
                    "organism": "Homo sapiens",
                    "organism_taxid": 9606,
                    "uniprot_accession": "Q92508",
                    "sequence_length": 2521,
                    "family": Family.PIEZO,
                    "activation_mechanism": "Force-from-Lipids",
                    "ortholog_group": "PIEZO1",
                },
                {
                    "maicdb_id": "MAIC:CH:TST02",
                    "gene_symbol": "PIEZO1",
                    "organism": "Mus musculus",
                    "organism_taxid": 10090,
                    "uniprot_accession": None,
                    "sequence_length": 2521,
                    "family": Family.PIEZO,
                    "activation_mechanism": "Force-from-Lipids",
                    "ortholog_group": "PIEZO1",
                },
            ],
        )

    with pytest.raises(AmbiguousGeneError, match="Mus musculus"):
        channel_card(eng, "PIEZO1", parameters=["p50"])
    with pytest.raises(AmbiguousGeneError, match="2 organisms"):
        parameter_comparison(eng, "p50")
    eng.dispose()


def test_schema_valid_null_states_render_and_export_cleanly():
    """Schema-valid NULL states data-v1.0 doesn't exercise (all verified
    against an in-memory artifact):

    * ``measurement_id IS NULL`` (nullable column; census: 0 rows in
      data-v1.0) — the aggregate carries it, the CSV join renders an
      explicit ``(unattributed)`` marker instead of crashing, and the
      CARD renders the same marker (not a Python ``None``);
      ``provenance(None)`` is a clean miss, not an ``IS NULL`` match.
    * unit ordering is the documented total order None < "" < named units;
      rows are inserted in the REVERSE order so a stable sort that merely
      preserved insertion order would fail the assertion.
    * two tied NULL-ID rows (equal value) order by the NOT-NULL unique
      ``maicdb_id`` tie-break — the card renders "A quote" before "B
      quote" although B was inserted first.
    """
    from maicdb.enums import Family
    from maicdb.models import Base, BiophysicsExperiment, Channel
    from sqlalchemy.orm import Session

    from maicdb.query import _render_card

    eng = sa.create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as sess:
        ch = Channel(
            maicdb_id="MAIC:CH:TST03",
            gene_symbol="PIEZO1",
            organism="Homo sapiens",
            family=Family.PIEZO,
            activation_mechanism="Force-from-Lipids",
        )
        sess.add(ch)
        sess.flush()
        sess.add_all(
            [
                BiophysicsExperiment(
                    maicdb_id="MAIC:BX:TST03", channel_id=ch.id,
                    measurement_id="PIEZO1-EX-TST03", slope=3.0, slope_unit="S",
                ),
                BiophysicsExperiment(
                    maicdb_id="MAIC:BX:TST02", channel_id=ch.id,
                    measurement_id="PIEZO1-EX-TST02", slope=2.0, slope_unit="",
                ),
                BiophysicsExperiment(
                    maicdb_id="MAIC:BX:TST01", channel_id=ch.id,
                    measurement_id=None, slope=1.0, slope_unit=None,
                    evidence_quote="B quote",
                ),
                # inserted AFTER its tie partner, sorts BEFORE it (maicdb_id)
                BiophysicsExperiment(
                    maicdb_id="MAIC:BX:TST00", channel_id=ch.id,
                    measurement_id=None, slope=1.0, slope_unit=None,
                    evidence_quote="A quote",
                ),
            ]
        )
        sess.commit()

    cmp_rows = parameter_comparison(eng, "slope")
    piezo = [r for r in cmp_rows if r["gene"] == "PIEZO1" and r["count"] > 0]
    assert [r["unit"] for r in piezo] == [None, "", "S"]
    assert piezo[0]["count"] == 2
    assert piezo[0]["measurement_ids"] == [None, None]

    csv_text = export(eng, "slope", format="csv")
    assert "(unattributed);(unattributed)" in csv_text
    assert csv_text.count("\n") == 4  # header + 3 unit-bucket rows

    card = channel_card(eng, "PIEZO1", parameters=["slope"])
    assert "(unattributed)" in _render_card(card)
    # Tied NULL ids order by maicdb_id (TST00 "A quote" < TST01 "B quote"),
    # not by insertion order (B was inserted first).
    quotes = [r["evidence_quote"] for r in card["parameters"]["slope"]["rows"]]
    assert quotes[-2:] == ["A quote", "B quote"]
    assert provenance(eng, None) is None  # clean miss, not an IS-NULL match
    eng.dispose()


# --------------------------------------------------------------------------- #
# CLI — maicdb-query (channel / export / provenance)
# --------------------------------------------------------------------------- #
CLI_ARGS = ["--db", str(DB_PATH)]


def test_cli_channel_card(capsys):
    """``maicdb-query channel PIEZO1 --parameter p50`` — the HANDOFF §2
    first-consumer target: identity + P50 rows with per-row provenance,
    frozen disclosure inline (human-readable card, stdout is the product).
    """
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
    # Missing evidence fields render their absence explicitly (§2): the two
    # note-less PIEZO1 p50 rows (00041/00042 — census in the card test).
    assert out.count("extractor_note: (not recorded)") == 2

    assert main(["channel", "PIEZO1", "--parameter", "p50", *CLI_ARGS]) == 0
    assert capsys.readouterr().out == out  # byte-identical (rule 6)


def test_cli_channel_unknown_gene_clean_error(capsys):
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
    rc = main(["provenance", "PIEZO1-EX-00005", *CLI_ARGS])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PIEZO1-EX-00005" in out
    assert "Results (Fig. 1F)" in out
    assert "The current-pressure relationship is characterized" in out
    assert "not been re-verified" in out  # §6.7 boilerplate on this path too

    rc = main(["provenance", "NO-SUCH-MEASUREMENT", *CLI_ARGS])
    captured = capsys.readouterr()
    assert rc != 0
    assert "NO-SUCH-MEASUREMENT" in captured.err

    rc = main(["provenance", "PIEZO1-EX-00041", *CLI_ARGS])  # note-less row
    out41 = capsys.readouterr().out
    assert rc == 0
    assert "extractor_note: (not recorded)" in out41

    rc = main(["provenance", "ASIC-00042", *CLI_ARGS])  # n-less row (445 like it)
    out_n = capsys.readouterr().out
    assert rc == 0
    assert "n: (not recorded)" in out_n


def test_db_artifact_untouched_by_whole_suite():
    """HANDOFF §3 rule 1: the shipped artifact is never mutated — the DB
    file hash is unchanged by the entire query test suite."""
    import hashlib

    assert _DB_HASH_BEFORE is not None
    assert hashlib.sha256(DB_PATH.read_bytes()).hexdigest() == _DB_HASH_BEFORE

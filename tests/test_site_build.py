"""Site data-layer build tests (M3-T2, issue #37).

Real-data provenance: every pinned value below comes from the published
artifact (data-v1.0, vault head 5a8ff0e) via read-only census SQL,
re-derived independently by the spec gate review (vault digest
``report/ReviewDigest_maicdb-code-m3-website-spec_2026-11-02_agent.md``).
The qualitative-row caliber, verbatim (issue #37's found caliber —
spec §4 records the results):

    SELECT c.gene_symbol, e.measurement_id, e.value_as_reported
      FROM biophysics_experiment e JOIN channel c ON e.channel_id = c.id
     WHERE e.p50_value IS NULL AND e.t50_value IS NULL
       AND e.x50_value IS NULL AND e.slope IS NULL
       AND e.tau_act_ms IS NULL AND e.tau_inact_ms IS NULL
       AND e.tau_deact_ms IS NULL AND e.conductance_ps IS NULL
       AND e.reversal_potential_mv IS NULL AND e.delta_p50_value IS NULL
       AND e.ion_selectivity_ratio IS NULL AND e.ca_permeability IS NULL
       AND e.threshold_fold_shift_value IS NULL
       AND e.macroscopic_rise_time_ms IS NULL
       AND e.thermal_threshold_c IS NULL
       AND e.osmotic_threshold_value IS NULL
    → 12 rows (1×PIEZO2, 1×ASIC, 1×TREK-1, 3×TREK-2, 6×TRPV4); hence
      948 table rows − 12 = 936 parameterized rows.
"""

import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "db" / "maicdb.sqlite"
BUILD_SCRIPT = REPO_ROOT / "site" / "build.py"

requires_db = pytest.mark.skipif(
    not DB_PATH.exists(), reason=f"published DB not found at {DB_PATH}"
)

_DB_HASH_BEFORE = (
    hashlib.sha256(DB_PATH.read_bytes()).hexdigest() if DB_PATH.exists() else None
)

#: The 12 channel slugs (lowercase gene symbols, spec Q7; census SQL in
#: spec §4 — 12 distinct gene_symbols, no slug collision).
EXPECTED_SLUGS = [
    "asic",
    "mscl",
    "mscs",
    "osca",
    "piezo1",
    "piezo2",
    "tmc",
    "traak",
    "trek-1",
    "trek-2",
    "tresk",
    "trpv4",
]


def run_build(out_dir: Path) -> "subprocess.CompletedProcess[str]":
    """Run the site build against the published artifact, read-only."""
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src"))
    return subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--db",
            str(DB_PATH),
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )


@requires_db
def test_build_emits_one_json_per_channel(tmp_path):
    """Twelve channel JSON files under _data/channels/, slug-named.

    Slugs pinned to the artifact census (12 distinct gene_symbols;
    ``TREK-1`` lowercases to ``trek-1`` keeping its hyphen — spec Q7).
    """
    out = tmp_path / "out"
    run_build(out)
    files = sorted((out / "_data" / "channels").glob("*.json"))
    assert [f.stem for f in files] == EXPECTED_SLUGS


@requires_db
def test_channel_json_shape_piezo1(tmp_path):
    """The piezo1 card JSON carries identity, the frozen-layer disclosure,
    and all 16 registered parameter blocks (zero-row blocks included).

    Pinned: PIEZO1 identity (family PIEZO, UniProt Q92508 — census SQL in
    spec §4); FROZEN_GENE_SYMBOLS = {PIEZO1, PIEZO2} (query.py);
    16-block cards asserted zero-row-visible in test_query.py.
    """
    out = tmp_path / "out"
    run_build(out)
    card = json.loads((out / "_data" / "channels" / "piezo1.json").read_text())
    assert card["gene"]["gene_symbol"] == "PIEZO1"
    assert card["gene"]["family"] == "PIEZO"
    assert card["gene"]["uniprot_accession"] == "Q92508"
    assert "frozen_layer_disclosure" in card
    assert len(card["parameters"]) == 16
    # The 160 PIEZO1 biophysics rows all live in some block (census §4).
    total_rows = sum(b["n_rows"] for b in card["parameters"].values())
    assert total_rows == 160


@requires_db
def test_build_emits_family_index(tmp_path):
    """index.json: family(7) → channel(12) hierarchy with per-channel
    parameter counts.

    Pinned to the artifact census (spec §4), ``n_parameterized_rows``
    caliber — rows carrying at least one normalized parameter value:
    7 families; PIEZO splits PIEZO1 160 / PIEZO2 27; 936 across all
    channels. The 948-row table census minus 936 = 12 qualitative rows
    whose as-reported value is non-numeric (LINEAR, OUTWARD_RECTIFYING,
    ranges like "185-224") and which belong to no parameter block
    (census: all-16-parameter-columns NULL per gene — 1×PIEZO2,
    1×ASIC, 1×TREK-1, 3×TREK-2, 6×TRPV4).
    """
    out = tmp_path / "out"
    run_build(out)
    index = json.loads((out / "_data" / "index.json").read_text())
    families = index["families"]
    assert len(families) == 7

    all_channels = {c["slug"]: c for f in families for c in f["channels"]}
    assert len(all_channels) == 12

    piezo = next(f for f in families if f["family"] == "PIEZO")
    counts = {c["slug"]: c["n_parameterized_rows"] for c in piezo["channels"]}
    assert counts == {"piezo1": 160, "piezo2": 27}

    total = sum(c["n_parameterized_rows"] for c in all_channels.values())
    assert total == 936

    # Per-parameter counts ride along for the browse page (T4): PIEZO1's
    # 56 P50 rows are the README transcript's own pinned number.
    assert all_channels["piezo1"]["parameters"]["p50"] == 56


@requires_db
def test_build_emits_search_index(tmp_path):
    """search-index.json: one flat entry list for client-side substring
    search (spec Q9) — channels (name/aliases/UniProt), families,
    parameters.

    Pinned to the artifact (census SQL / channel table):
    * PIEZO1 aliases ``["FAM38A", "Mib"]``, UniProt Q92508;
    * TMC carries 2 accessions (Q8TDI8/Q8TDI7 — slash-stored set);
    * OSCA has NULL uniprot_accession → empty list, never a null;
    * 7 families; parameter names are the 16 registry keys.
    """
    out = tmp_path / "out"
    run_build(out)
    index = json.loads((out / "_data" / "search-index.json").read_text())
    entries = index["entries"]

    channels = [e for e in entries if e["type"] == "channel"]
    assert len(channels) == 12
    piezo1 = next(e for e in channels if e["slug"] == "piezo1")
    assert piezo1["label"] == "PIEZO1"
    assert piezo1["aliases"] == ["FAM38A", "Mib"]
    assert piezo1["uniprots"] == ["Q92508"]
    tmc = next(e for e in channels if e["slug"] == "tmc")
    assert tmc["uniprots"] == ["Q8TDI8", "Q8TDI7"]
    osca = next(e for e in channels if e["slug"] == "osca")
    assert osca["uniprots"] == []

    families = [e for e in entries if e["type"] == "family"]
    assert len(families) == 7

    params = [e for e in entries if e["type"] == "parameter"]
    from maicdb.query import PARAMETERS

    assert {e["name"] for e in params} == set(PARAMETERS)


@requires_db
def test_build_index_carries_bioactivity_and_qualitative_counts(tmp_path):
    """index.json per-channel counts for the browse page (T4):

    * ``n_bioactivity_rows`` — pinned to the artifact census (spec §4):

          SELECT c.gene_symbol, COUNT(*) FROM bioactivity b
            JOIN channel c ON b.channel_id = c.id GROUP BY 1;

      → TRPV4 37, TRESK 34, ASIC 24, TMC 19, PIEZO1 14, TREK-1 4,
        OSCA 2, MscS 1, TRAAK 1; PIEZO2/MscL/TREK-2 carry 0.

    * ``n_qualitative_rows`` — biophysics rows with ALL 16 registered
      parameter columns NULL (the as-reported-only caliber, spec §4;
      census SQL in this file's module docstring → 12 rows repo-wide):
      PIEZO2 1, ASIC 1, TREK-1 1, TREK-2 3, TRPV4 6, others 0.
    """
    out = tmp_path / "out"
    run_build(out)
    index = json.loads((out / "_data" / "index.json").read_text())
    all_channels = {c["slug"]: c for f in index["families"] for c in f["channels"]}

    assert {s: c["n_bioactivity_rows"] for s, c in all_channels.items()} == {
        "asic": 24, "mscl": 0, "mscs": 1, "osca": 2, "piezo1": 14,
        "piezo2": 0, "tmc": 19, "traak": 1, "trek-1": 4, "trek-2": 0,
        "tresk": 34, "trpv4": 37,
    }
    qualitative = {s: c["n_qualitative_rows"] for s, c in all_channels.items()}
    assert qualitative == {
        "asic": 1, "mscl": 0, "mscs": 0, "osca": 0, "piezo1": 0,
        "piezo2": 1, "tmc": 0, "traak": 0, "trek-1": 1, "trek-2": 3,
        "tresk": 0, "trpv4": 6,
    }
    assert sum(qualitative.values()) == 12


@requires_db
def test_channel_json_carries_bioactivity_block(tmp_path):
    """Channel card JSONs compose the bioactivity block where data exists
    (spec §3 Q11 — 9 channels): PIEZO1 carries 14 rows, and the block
    keeps the §6.7 disclosure a PIEZO row owes (the wording follows the
    evidence itself); TREK-2 (0 rows) carries no block at all.

    Pinned to the census SQL in
    test_build_index_carries_bioactivity_and_qualitative_counts.
    """
    out = tmp_path / "out"
    run_build(out)
    piezo1 = json.loads((out / "_data" / "channels" / "piezo1.json").read_text())
    assert piezo1["bioactivity"]["n_rows"] == 14
    assert piezo1["bioactivity"]["gene"] == "PIEZO1"
    assert piezo1["bioactivity"]["frozen_layer_disclosure"] == (
        piezo1["frozen_layer_disclosure"]
    )
    # rows carry the compound join + evidence chain (query library contract)
    row = piezo1["bioactivity"]["rows"][0]
    assert {"compound_name", "activity_type", "activity_value", "evidence_quote"} <= set(
        row
    )

    trek2 = json.loads((out / "_data" / "channels" / "trek-2.json").read_text())
    assert "bioactivity" not in trek2


@requires_db
def test_build_is_byte_stable(tmp_path):
    """Same artifact + same code → byte-identical outputs across runs
    (spec §6 determinism contract, mirroring loader/export)."""
    out_a, out_b = tmp_path / "a", tmp_path / "b"
    run_build(out_a)
    run_build(out_b)
    files_a = sorted(p.relative_to(out_a) for p in out_a.rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(out_b) for p in out_b.rglob("*") if p.is_file())
    assert files_a == files_b
    assert files_a, "build produced no files"
    for rel in files_a:
        assert (out_a / rel).read_bytes() == (out_b / rel).read_bytes(), rel


def test_locale_string_skeletons_parity():
    """UI-copy dictionaries exist with identical key sets (spec Q3: i18n
    ready from day one; rendering itself is T3)."""
    en = json.loads((REPO_ROOT / "site" / "strings.en.json").read_text())
    zh = json.loads((REPO_ROOT / "site" / "strings.zh.json").read_text())
    assert set(en) == set(zh)
    assert en, "skeleton is not empty — T3 consumes these keys"


@requires_db
def test_build_emits_home_totals(tmp_path):
    """index.json carries the home-scale ``totals`` block, computed from
    SQL — never a transcribed number (ticket #38: the 1100/12/7/211
    overview comes from the data layer, not the template).

    Pinned to the artifact census (spec §4). Census SQL, re-runnable
    read-only against db/maicdb.sqlite:

        SELECT (SELECT COUNT(*) FROM biophysics_experiment)   -- 948
             + (SELECT COUNT(*) FROM bioactivity)             -- 136
             + (SELECT COUNT(*) FROM unmapped_measurement);   --  16  → 1100
        SELECT COUNT(*) FROM publication;                     -- 211
        SELECT COUNT(*) FROM channel;                         --  12
        SELECT COUNT(DISTINCT family) FROM channel;           --   7
    """
    out = tmp_path / "out"
    run_build(out)
    totals = json.loads((out / "_data" / "index.json").read_text())["totals"]
    assert totals == {
        "n_measurements": 1100,
        "n_unmapped": 16,
        "n_channels": 12,
        "n_families": 7,
        "n_publications": 211,
    }


@requires_db
def test_build_renders_home_in_both_locale_trees(tmp_path):
    """The full CLI build renders home in both locale trees with the
    computed scale numbers (data-driven, never hardcoded)."""
    out = tmp_path / "out"
    run_build(out)
    en = (out / "_site" / "index.html").read_text(encoding="utf-8")
    zh = (out / "_site" / "zh" / "index.html").read_text(encoding="utf-8")
    assert "<html lang=\"en\">" in en
    assert "<html lang=\"zh\">" in zh
    for html in (en, zh):
        assert ">1100<" in html and ">12<" in html
        assert ">7<" in html and ">211<" in html
    # all 7 real family names surface as entry links (census §4)
    for family in (
        "DEG_ENaC_ASIC", "K2P", "MSCL_MSCS", "OSCA_TMEM63", "PIEZO", "TMC", "TRP",
    ):
        assert family in en


@requires_db
def test_every_en_page_has_zh_counterpart_and_switcher(tmp_path):
    """Locale invariant over the WHOLE rendered tree, not just home:
    every EN page has a ``zh/`` counterpart file, and each page's
    language switcher — the ``lang-switch`` anchor itself, not any
    relative link — resolves exactly to the counterpart page (ticket
    acceptance; T4–T7 pages inherit this contract by construction)."""
    out = tmp_path / "out"
    run_build(out)
    site = out / "_site"
    en_pages = sorted(
        p.relative_to(site)
        for p in site.rglob("*.html")
        if p.relative_to(site).parts[0] != "zh"
    )
    assert en_pages, "no EN pages rendered"
    for rel in en_pages:
        en_html = (site / rel).read_text(encoding="utf-8")
        zh_rel = Path("zh") / rel
        zh_page = site / zh_rel
        assert zh_page.is_file(), f"missing ZH counterpart for {rel}"
        zh_html = zh_page.read_text(encoding="utf-8")
        page_dir = rel.parent.as_posix()

        def switcher_target(html: str, tree_root: str) -> str:
            match = re.search(r'class="lang-switch"[^>]*href="([^"]*)"', html)
            assert match, f"no language switcher in {rel}"
            return posixpath.normpath(
                posixpath.join(tree_root, page_dir, match.group(1))
            )

        # EN switcher lands on the ZH counterpart; ZH switcher back on EN
        zh_target = posixpath.normpath(posixpath.join("zh", page_dir))
        assert switcher_target(en_html, ".") == zh_target
        assert switcher_target(zh_html, "zh") == posixpath.normpath(page_dir)


@requires_db
def test_db_artifact_untouched_by_site_suite():
    """Site-suite DB guard: test_query.py's whole-suite guard runs before
    this file alphabetically, so the build subprocesses executed in this
    file need their own read-only assertion (spec §6: a site build never
    mutates the artifact).
    """
    assert hashlib.sha256(DB_PATH.read_bytes()).hexdigest() == _DB_HASH_BEFORE

"""Site data-layer build tests (M3-T2, issue #37).

Real-data provenance: every pinned value below comes from the published
artifact (data-v1.0, vault head 5a8ff0e) via the census SQL documented in
``docs/m3-website-spec.md`` §4 — independently re-derived read-only by the
spec gate review (vault digest
``report/ReviewDigest_maicdb-code-m3-website-spec_2026-11-02_agent.md``).
"""

import hashlib
import json
import os
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
def test_db_artifact_untouched_by_site_suite():
    """Site-suite DB guard: test_query.py's whole-suite guard runs before
    this file alphabetically, so the build subprocesses executed in this
    file need their own read-only assertion (spec §6: a site build never
    mutates the artifact).
    """
    assert hashlib.sha256(DB_PATH.read_bytes()).hexdigest() == _DB_HASH_BEFORE

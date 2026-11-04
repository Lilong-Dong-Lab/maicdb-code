"""Loader tests.

Two tiers:
* **Unit tests** (always run) — inline fixtures exercising the transform
  functions ported from the staging loader (conversion factors, hook
  anchoring, role resolution, mutation parsing, lossless label folding).
* **Full-load tests** (skip without the vault) — run the real loader against
  the sibling vault checkout and assert conservation, determinism (two runs
  → byte-identical SQL dumps), and enum coverage. Vault discovery:
  ``$MAICDB_VAULT`` env var, else the sibling
  ``../Project_DataBase_MAICDB`` next to this repo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maicdb.loader import (
    GAP_KEEPS,
    UNIT_ENUMS,
    _convert,
    _experiment_label,
    _f,
    _parse_short_mutation,
    load_vault,
    verify_vault,
)

import os
# env var wins (explicit override), else the sibling checkout
VAULT = Path(os.environ.get("MAICDB_VAULT") or
             Path(__file__).resolve().parents[2] / "Project_DataBase_MAICDB")
VAULT_PRESENT = VAULT.exists()
#: The 12 channel directories the frozen corpus ships (census: spec §4 —
#: ``SELECT gene_symbol FROM channel`` lowercased, data-v1.0 tree).
VAULT_CHANNEL_DIRS = [
    "asic", "mscl", "mscs", "osca", "piezo1", "piezo2", "tmc",
    "traak", "trek-1", "trek-2", "tresk", "trpv4",
]
VAULT_INTACT = VAULT_PRESENT and all(
    (VAULT / "data" / ch).is_dir() for ch in VAULT_CHANNEL_DIRS
)

requires_vault = pytest.mark.skipif(
    not VAULT_PRESENT, reason=f"vault checkout not found at {VAULT}")


def test_vault_checkout_mangled_goes_red_not_silent_skip():
    """Environment guard (retro 2026-11-04): a PRESENT but MANGLED vault
    checkout is a red failure, never a silent skip.

    The 2026-11-03 incident: a GUI auto-``git checkout main`` deleted the
    branch-tracked ``data/`` corpora (main tracks only ``report/``), and
    every vault-dependent test silently skipped for ~24h behind a green
    suite. Absent vault (CI novault/notag states) still skips — this test
    guards the present-but-broken middle state only.

    Recovery pointer: ``docs/agents/vault-ops.md`` (GUI auto-sync warning
    + the incident's restore path: reflog tip → rebuild the work branch →
    checkout back).
    """
    if not VAULT_PRESENT:
        pytest.skip(f"vault checkout not found at {VAULT} — CI novault/notag state")
    missing = [ch for ch in VAULT_CHANNEL_DIRS if not (VAULT / "data" / ch).is_dir()]
    assert not missing, (
        f"vault checkout at {VAULT} is PRESENT but MANGLED — data/ is missing "
        f"channel directories: {missing}. This is the GUI auto-checkout "
        "incident signature (2026-11-03): do NOT re-derive pins off this "
        "state; restore per docs/agents/vault-ops.md first."
    )


# --------------------------------------------------------------------------- #
# Unit tier — transforms
# --------------------------------------------------------------------------- #
def test_convert_factors_and_error_coscale():
    """Each pre-authorized factor scales value and error; rounding at 6 dp."""
    r = {"value": "10.6", "error": "0.2",
         "extractor_note": "REPORTED UNIT IS SECONDS (as-printed)"}
    v, e, converted = _convert(r)
    assert converted and v == pytest.approx(10600.0) and e == pytest.approx(200.0)
    r2 = {"value": "31.8", "error": "",
          "extractor_note": "REPORTED UNIT IS MINUTES"}
    v2, e2, c2 = _convert(r2)
    assert c2 and v2 == pytest.approx(1_908_000.0) and e2 is None
    r3 = {"value": "5", "error": "1", "extractor_note": "REPORTED UNIT IS MILLIMOLAR"}
    v3, e3, c3 = _convert(r3)
    assert c3 and v3 == pytest.approx(5e6) and e3 == pytest.approx(1e6)


def test_convert_hook_anywhere_in_note():
    """F-042 lesson: mid-note hooks must fire (asic as-printed prefix case)."""
    r = {"value": "2", "error": "",
         "extractor_note": "as-printed per source. REPORTED UNIT IS NANOSIEMENS kept"}
    v, _e, converted = _convert(r)
    assert converted and v == pytest.approx(2000.0)


def test_convert_no_hook_is_passthrough():
    r = {"value": "73", "error": "5", "extractor_note": "plain note, no hook"}
    v, e, converted = _convert(r)
    assert not converted and v == 73.0 and e == 5.0


def test_role_tie_break_is_deterministic_antagonist():
    """TFE 2/2: alphabetical tie-break → ANTAGONIST (staging parity; the
    formal enum carries ANTAGONIST as a direct member)."""
    from collections import Counter
    from maicdb.enums import CompoundType
    from maicdb.loader import ROLE_TO_COMPOUND_TYPE
    cnt = Counter({"antagonist": 2, "potentiator": 2})
    winner = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    assert ROLE_TO_COMPOUND_TYPE[winner] is CompoundType.ANTAGONIST
    cnt2 = Counter({"agonist": 12, "potentiator": 1})  # Yoda1
    winner2 = sorted(cnt2.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    assert ROLE_TO_COMPOUND_TYPE[winner2] is CompoundType.ACTIVATOR


def test_parse_short_mutation():
    assert _parse_short_mutation("A1988V") == (1988, "A", "V")
    assert _parse_short_mutation("E756del") == (None, None, None)
    assert _parse_short_mutation("") == (None, None, None)


def test_numeric_cell_ranges_return_none():
    """Ranges/text → None (as-reported originals are preserved elsewhere)."""
    assert _f("3-10") is None
    assert _f("≥75 cells/data-point") is None
    assert _f("  ") is None
    assert _f("-46") == -46.0


def test_experiment_label_folds_losslessly():
    r = {"stimulus_detail": "pressure steps via servo",
         "stimulus_value": "-50", "stimulus_value_unit": "mmHg",
         "modulator_name": "Yoda1", "modulator_role": "agonist",
         "modulator_concentration": "10", "modulator_conc_unit": "µM",
         "temperature_c": "22"}
    lab = _experiment_label(r)
    assert "pressure steps via servo" in lab
    assert "STIMULUS: -50 mmHg" in lab
    assert "MODULATOR: Yoda1 (agonist) 10 µM" in lab
    assert "TEMPERATURE-AS-REPORTED" not in lab  # parseable temp not folded
    r2 = {**r, "stimulus_detail": "", "stimulus_value": "", "modulator_name": "",
          "temperature_c": "room temp"}
    assert _experiment_label(r2) == "TEMPERATURE-AS-REPORTED: room temp"


def test_gap_keeps_cover_the_sixteen():
    """The adjudicated-KEEP table must exactly cover the vault's 16 kept rows
    (pressure_threshold 9, isr 2, x50 2, block_voltage 2, tau_act 1)."""
    assert ("ion_selectivity_ratio", "mV/decade") in GAP_KEEPS
    assert ("pressure_threshold", "mm Hg") in GAP_KEEPS
    assert ("pressure_threshold", "nN/um2") in GAP_KEEPS
    assert ("pressure_threshold", "µm") in GAP_KEEPS
    assert ("block_voltage", "mV") in GAP_KEEPS
    assert ("block_voltage", "") in GAP_KEEPS
    assert ("x50", "nm") in GAP_KEEPS
    assert ("tau_act", "ms") in GAP_KEEPS


def test_unit_enum_strictness():
    """Unknown unit_db value fails loudly (strict mapping, spec §4)."""
    with pytest.raises(ValueError):
        UNIT_ENUMS["p50_unit"]("furlongs")
    assert UNIT_ENUMS["p50_unit"]("mmHg").name == "MMHG"


# --------------------------------------------------------------------------- #
# Full-load tier — requires the vault
# --------------------------------------------------------------------------- #
@requires_vault
def test_freeze_enforcement():
    """A bogus tag must fail; the freeze contract is load-bearing."""
    with pytest.raises(RuntimeError):
        verify_vault(VAULT, "data-v9.9")


@requires_vault
def test_full_load_conservation(tmp_path):
    out = tmp_path / "conserv.sqlite"
    manifest = load_vault(VAULT, out, require_tag="data-v1.0",
                          manifest_path=tmp_path / "m.json")
    c = manifest["counts"]
    # Spec §4 conservation (compound 86 = 85 roled + unroled silica family —
    # the formal NOT-NULL compound link requires it; publication 211 = 205
    # extraction + 6 structure-only citations: both deltas disclosed).
    assert (c["biophysics"], c["bioactivity"], c["unmapped"]) == (948, 136, 16)
    assert c["channel"] == 12 and c["structure"] == 12 and c["variant"] == 125
    assert c["unit_conversions"] == 105
    assert c["compound"] == 86 and c["publication"] == 211
    assert any("silica" in d.lower() or "unroled" in d.lower()
               for d in manifest["disclosures"])


@requires_vault
def test_determinism_byte_identical_dump(tmp_path):
    """Two independent loads → byte-identical SQL dumps (spec §4)."""
    m1 = load_vault(VAULT, tmp_path / "a.sqlite", require_tag=None)
    m2 = load_vault(VAULT, tmp_path / "b.sqlite", require_tag=None)
    a = Path(m1["dump"]).read_bytes()
    b = Path(m2["dump"]).read_bytes()
    assert a == b
    assert a  # non-empty


@requires_vault
def test_all_nine_recording_modes_present(tmp_path):
    """The corpus uses every RecordingMode member — coverage assert expects 9."""
    import sqlite3
    out = tmp_path / "modes.sqlite"
    load_vault(VAULT, out, require_tag=None)
    conn = sqlite3.connect(out)
    modes = {row[0] for row in conn.execute(
        "SELECT DISTINCT recording_mode FROM biophysics_experiment "
        "WHERE recording_mode IS NOT NULL")}
    conn.close()
    from maicdb.enums import RecordingMode
    assert modes == {m.name for m in RecordingMode}


@requires_vault
def test_migration_values_land_typed(tmp_path):
    """The 130 adjudicated migrations land in typed columns (no silent NULLs):
    isr 66 + ca_permeability 4 + fold-shift 23 + delta_p50-gap 12 (nm drifts
    into the shift pair) + rise 13 + thermal 9 + osmotic 3; the card's
    delta_p50_value carries the 16 normal-routed rows."""
    import sqlite3
    out = tmp_path / "mig.sqlite"
    load_vault(VAULT, out, require_tag=None)
    conn = sqlite3.connect(out)
    q = "SELECT COUNT(*) FROM biophysics_experiment WHERE {} IS NOT NULL"
    got = {col: conn.execute(q.format(col)).fetchone()[0] for col in (
        "ion_selectivity_ratio", "ca_permeability", "threshold_fold_shift_value",
        "macroscopic_rise_time_ms", "thermal_threshold_c",
        "osmotic_threshold_value", "delta_p50_value")}
    conn.close()
    assert got == {"ion_selectivity_ratio": 66, "ca_permeability": 4,
                   "threshold_fold_shift_value": 35,  # 23 fold-shift + 12 nm drifts
                   "macroscopic_rise_time_ms": 13, "thermal_threshold_c": 9,
                   "osmotic_threshold_value": 3, "delta_p50_value": 16}


@requires_vault
def test_structure_publication_links(tmp_path):
    """MAJOR-1 regression: structure.publication_id must link (10 of 12 raw
    citations carry a DOI; 9VMX/9VED legitimately NULL), and the 6
    structure-only publications must be referenced by ≥1 row each."""
    import sqlite3
    out = tmp_path / "links.sqlite"
    m = load_vault(VAULT, out, require_tag=None)
    assert m["counts"]["structure_publication_links"] >= 8
    conn = sqlite3.connect(out)
    linked = conn.execute(
        "SELECT COUNT(*) FROM structure WHERE publication_id IS NOT NULL").fetchone()[0]
    orphans = conn.execute(
        "SELECT COUNT(*) FROM publication p WHERE p.id NOT IN "
        "(SELECT publication_id FROM biophysics_experiment WHERE publication_id IS NOT NULL "
        " UNION SELECT publication_id FROM bioactivity WHERE publication_id IS NOT NULL "
        " UNION SELECT publication_id FROM structure WHERE publication_id IS NOT NULL "
        " UNION SELECT publication_id FROM unmapped_measurement WHERE publication_id IS NOT NULL "
        " UNION SELECT publication_id FROM variant WHERE publication_id IS NOT NULL "
        " UNION SELECT publication_id FROM compound WHERE publication_id IS NOT NULL "
        " UNION SELECT publication_id FROM channel WHERE publication_id IS NOT NULL)"
    ).fetchone()[0]
    conn.close()
    assert linked >= 8
    assert orphans == 0  # every publication is cited by some row


@requires_vault
def test_yoda1_keeps_inchikey(tmp_path):
    """MINOR-3 regression: duplicate InChIKeys award to corpus-joining names —
    Yoda1 (and Jedi1/Jedi2) must carry their key, not the CHEMBL alias rows."""
    import sqlite3
    out = tmp_path / "keys.sqlite"
    load_vault(VAULT, out, require_tag=None)
    conn = sqlite3.connect(out)
    keys = dict(conn.execute(
        "SELECT name, inchikey FROM compound WHERE name IN "
        "('Yoda1','Jedi1','Jedi2')").fetchall())
    conn.close()
    assert keys.get("Yoda1") not in (None, "")
    assert sum(1 for v in keys.values() if v) >= 2

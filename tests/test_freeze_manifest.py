"""Freeze-manifest contract tests (ADR-0007, PR B 2026-11-16).

All fixtures are SYNTHETIC (no real-data provenance): a throwaway 12-layer
git repo built in ``tmp_path`` — one stub ``extracted_measurements.csv`` per
canonical layer plus stub literature-mining configs. The contract exercised
is build → validate → hash-verify; the sibling vault is never touched, so
these tests run in every suite state (incl. CI novault/notag).
"""
from __future__ import annotations

import json
import subprocess

import pytest

from maicdb.vault import (LAYERS, FrozenVault, build_freeze_manifest,
                          load_freeze_manifest)

TAG = "data-vT"


def _git(repo, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _commit(repo) -> None:
    _git(repo, "-c", "user.email=test@example.com",
         "-c", "user.name=test", "commit", "-q", "-m", "synthetic surface")


@pytest.fixture()
def synth_vault(tmp_path):
    """A clean synthetic vault at annotated tag ``data-vT``.

    ``data/notes.md`` (root doc) and a stray ``configs/*.json`` are
    deliberately tracked: the frozen-surface inventory must exclude them —
    the ANCHORED ``(glob)`` semantics (``*`` does not cross ``/``). The
    per-layer ``data/asic/README.md`` is equally deliberately tracked and
    must stay PINNED: only root docs are legal post-freeze churn (the
    47-file-incident pair: PR #66 + 8cdb764 erratum).
    """
    vault = tmp_path / "vault"
    for layer in LAYERS:
        d = vault / "data" / layer / "extraction"
        d.mkdir(parents=True)
        slug = layer.upper().replace("-", "")
        (d / "extracted_measurements.csv").write_text(
            "measurement_id,verdict\n"
            f"SYN-{slug}-00001,VERBATIM\n"
            f"SYN-{slug}-00002,NEAR_VERBATIM\n",
            encoding="utf-8")
    (vault / "data" / "notes.md").write_text("prose, not frozen\n",
                                             encoding="utf-8")
    (vault / "data" / "asic" / "README.md").write_text(
        "per-layer prose — frozen\n", encoding="utf-8")
    (vault / "data" / "notes.md").write_text("prose, not frozen\n",
                                             encoding="utf-8")
    cfg = vault / "tools" / "literature-mining" / "configs"
    cfg.mkdir(parents=True)
    (cfg / "piezo1.yaml").write_text("benchmark: synthetic\n", encoding="utf-8")
    (cfg / "piezo1_notes.json").write_text("{}\n", encoding="utf-8")
    _git(vault, "init", "-q")
    _git(vault, "add", "-A")
    _commit(vault)
    _git(vault, "tag", "-a", TAG, "-m", "synthetic freeze")
    return vault


def _write_manifest(path, fm: dict) -> None:
    path.write_text(json.dumps(fm, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def _build(synth_vault):
    return build_freeze_manifest(synth_vault, TAG, freeze_date="2026-01-01",
                                 schema_version="0.0.0")


# --------------------------------------------------------------------------- #
# build_freeze_manifest
# --------------------------------------------------------------------------- #
def test_build_pins_identity_inventory_rows(synth_vault):
    fm = _build(synth_vault)
    assert fm["freeze_tag"] == TAG
    assert fm["schema_version"] == "0.0.0"
    assert fm["rows_total"] == 2 * len(LAYERS)
    assert sorted(fm["rows_per_layer"]) == sorted(LAYERS)
    pinned = "data/piezo1/extraction/extracted_measurements.csv"
    assert pinned in fm["files"] and len(fm["files"][pinned]) == 64
    assert fm["vault_head"]


def test_build_inventory_excludes_prose_and_config_json(synth_vault):
    """Anchored ``(glob)`` semantics: root docs (``data/*.md``) and
    configs-root registries (``configs/*.json``) stay OUT of the frozen
    surface; per-layer ``.md`` (``data/asic/README.md``) stays IN. The
    47-file incident was the UN-anchored pathspec form (it un-froze all 47
    ``data/**.md``); the anchored form fixed it (PR #66, 8cdb764 erratum
    48→47) — these filters re-derive the anchored set."""
    fm = _build(synth_vault)
    assert "data/notes.md" not in fm["files"]
    assert "tools/literature-mining/configs/piezo1_notes.json" not in fm["files"]
    assert fm["files"]["data/asic/README.md"]  # per-layer prose stays frozen
    expected = [
        f"data/{layer}/extraction/extracted_measurements.csv" for layer in LAYERS
    ]
    expected += ["data/asic/README.md", "tools/literature-mining/configs/piezo1.yaml"]
    assert sorted(fm["files"]) == sorted(expected)


# --------------------------------------------------------------------------- #
# load_freeze_manifest — fail-closed validation
# --------------------------------------------------------------------------- #
def test_roundtrip_ok_and_counts_optional(synth_vault, tmp_path):
    p = tmp_path / "fm.json"
    fm = _build(synth_vault)
    _write_manifest(p, fm)  # no counts block — must load fine
    check, sha = load_freeze_manifest(p)
    assert check == fm
    assert len(sha) == 64


def test_tamper_missing_key(synth_vault, tmp_path):
    p = tmp_path / "fm.json"
    fm = _build(synth_vault)
    del fm["vault_head"]
    _write_manifest(p, fm)
    with pytest.raises(RuntimeError, match="missing key 'vault_head'"):
        load_freeze_manifest(p)


def test_tamper_malformed_date(synth_vault, tmp_path):
    p = tmp_path / "fm.json"
    fm = _build(synth_vault)
    fm["freeze_date"] = "2026-13-99"
    _write_manifest(p, fm)
    with pytest.raises(RuntimeError, match="malformed freeze_date"):
        load_freeze_manifest(p)


def test_tamper_rows_total_mismatch(synth_vault, tmp_path):
    p = tmp_path / "fm.json"
    fm = _build(synth_vault)
    fm["rows_total"] = 999
    _write_manifest(p, fm)
    with pytest.raises(RuntimeError, match="rows_total 999"):
        load_freeze_manifest(p)


def test_tamper_rows_per_layer_keys(synth_vault, tmp_path):
    p = tmp_path / "fm.json"
    fm = _build(synth_vault)
    del fm["rows_per_layer"]["traak"]
    _write_manifest(p, fm)
    with pytest.raises(RuntimeError, match="!= the 12 corpus layers"):
        load_freeze_manifest(p)


def test_tamper_digest_not_hex64(synth_vault, tmp_path):
    """Both escape forms raise: wrong-length ('deadbeef') and the
    length-64-but-non-hex vector (a bare ``len`` check would pass it)."""
    p = tmp_path / "fm.json"
    fm = _build(synth_vault)
    f = next(iter(fm["files"]))
    fm["files"][f] = "deadbeef"
    _write_manifest(p, fm)
    with pytest.raises(RuntimeError, match="not a sha256 hex digest"):
        load_freeze_manifest(p)
    fm["files"][f] = "z" * 64
    _write_manifest(p, fm)
    with pytest.raises(RuntimeError, match="not a sha256 hex digest"):
        load_freeze_manifest(p)


def test_tamper_counts_missing_fact_table(synth_vault, tmp_path):
    p = tmp_path / "fm.json"
    fm = _build(synth_vault)
    fm["counts"] = {"publication": 3, "channel": 12}
    _write_manifest(p, fm)
    with pytest.raises(RuntimeError, match="missing fact tables"):
        load_freeze_manifest(p)


def test_tamper_counts_sum_mismatch(synth_vault, tmp_path):
    p = tmp_path / "fm.json"
    fm = _build(synth_vault)
    fm["counts"] = {"biophysics": 2 * len(LAYERS), "bioactivity": 1,
                    "unmapped": 0}
    _write_manifest(p, fm)
    with pytest.raises(RuntimeError, match="conservation counts sum"):
        load_freeze_manifest(p)


def test_missing_manifest_names_the_generator(tmp_path):
    with pytest.raises(RuntimeError, match="write-freeze-manifest.py"):
        load_freeze_manifest(tmp_path / "nowhere.json")


# --------------------------------------------------------------------------- #
# FrozenVault hash verification (manifest given)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def fm_file(synth_vault, tmp_path):
    p = tmp_path / "fm.json"
    _write_manifest(p, _build(synth_vault))
    fm, _ = load_freeze_manifest(p)
    return fm


def test_verify_hashchecked_happy(synth_vault, fm_file):
    assert FrozenVault(synth_vault, TAG,
                       freeze_manifest=fm_file).verify() == fm_file["vault_head"]


def test_verify_manifest_file_deleted_from_vault(synth_vault, fm_file):
    """A manifest pinning a file the vault lacks (hand-edit or partial
    revert) fails closed."""
    fm_file["files"]["data/ghost.csv"] = "0" * 64
    with pytest.raises(RuntimeError, match="in the freeze manifest but not"):
        FrozenVault(synth_vault, TAG, freeze_manifest=fm_file).verify()


def test_verify_untracked_scratch_still_tolerated(synth_vault, fm_file):
    """Untracked local scratch inside the frozen surface stays invisible:
    the old pathspec diff never failed on it (compare-commits semantics)
    and the closed set keeps that (inventory = ``git ls-files``)."""
    scratch = synth_vault / "data" / "scratch.json"
    scratch.write_text("{}\n", encoding="utf-8")
    assert FrozenVault(synth_vault, TAG,
                       freeze_manifest=fm_file).verify() == fm_file["vault_head"]


def test_verify_tracked_extra_in_frozen_surface(synth_vault, fm_file):
    """A file COMMITTED into the frozen surface after the manifest was cut
    (additive post-freeze content) trips the closed set: new frozen content
    requires a new tagged release and a regenerated manifest."""
    new_csv = synth_vault / "data" / "scratch" / "extracted_measurements.csv"
    new_csv.parent.mkdir()
    new_csv.write_text("measurement_id,verdict\nSYN-SCRATCH-1,NOT_FOUND\n",
                       encoding="utf-8")
    _git(synth_vault, "add", "-A")
    _commit(synth_vault)
    with pytest.raises(RuntimeError, match="not in the freeze manifest"):
        FrozenVault(synth_vault, TAG, freeze_manifest=fm_file).verify()


def test_verify_post_tag_content_drift(synth_vault, fm_file):
    """The load-bearing new protection: a commit AFTER the tag that edits
    frozen content (clean tree, tag resolves, HEAD descends) now fails the
    hash check with the drifted file named. The retired pathspec diff did
    catch same-shape edits like this one; its real gaps were shallow/no-tag
    clones (the diff cannot run at all), moved tags (the old check anchored
    on the re-tagged target), and the absence of a pinned, chainable
    artifact — all three close here."""
    csv = synth_vault / "data" / "traak" / "extraction" / \
        "extracted_measurements.csv"
    csv.write_text(csv.read_text(encoding="utf-8") + "SYN-TRAAK-00003,NOT_FOUND\n",
                   encoding="utf-8")
    _git(synth_vault, "add", "-A")
    _commit(synth_vault)
    with pytest.raises(RuntimeError, match="changed since data-vT"):
        FrozenVault(synth_vault, TAG, freeze_manifest=fm_file).verify()


def test_verify_retouched_tag_forbidden(synth_vault, fm_file):
    """Same bytes, moved tag target (``vault_head`` no longer matches) —
    re-tagging a freeze tag with consumers is forbidden (vault progress
    record)."""
    _git(synth_vault, "-c", "user.email=test@example.com",
         "-c", "user.name=test", "commit", "-q", "--allow-empty",
         "-m", "retouch")
    _git(synth_vault, "tag", "-f", "-a", TAG, "-m", "moved")
    with pytest.raises(RuntimeError, match="re-tagging a freeze tag"):
        FrozenVault(synth_vault, TAG, freeze_manifest=fm_file).verify()


def test_verify_tag_mismatch(synth_vault, fm_file):
    fm_file["freeze_tag"] = "data-vOTHER"
    with pytest.raises(RuntimeError, match="pins 'data-vOTHER'"):
        FrozenVault(synth_vault, TAG, freeze_manifest=fm_file).verify()


def test_verify_dirty_tree_still_gates_first(synth_vault, fm_file):
    """Deleted/modified tracked content is caught by the clean-tree gate
    that still runs before the hash check — either way, fail-closed."""
    csv = synth_vault / "data" / "mscl" / "extraction" / \
        "extracted_measurements.csv"
    csv.unlink()
    with pytest.raises(RuntimeError):
        FrozenVault(synth_vault, TAG, freeze_manifest=fm_file).verify()
    csv.write_text("measurement_id,verdict\nSYN-MSCL-99999,NOT_FOUND\n",
                   encoding="utf-8")
    with pytest.raises(RuntimeError):
        FrozenVault(synth_vault, TAG, freeze_manifest=fm_file).verify()

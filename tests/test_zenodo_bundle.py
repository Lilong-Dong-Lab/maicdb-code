"""Tests for the Zenodo upload staging (issue #17, ADR-0002/-0003).

Public seam: ``scripts/stage-zenodo-bundle.sh`` (subprocess) and the
staged/docs artifacts it governs. Provenance for every pinned value here is
repo-side, not vault data: the ``v1.0.0-data`` git tag (the published
artifact authority — GLOSSARY "data release") and ``CITATION.cff`` (the
canonical, editable home of the citation strings — ADR-0003). Tests skip
when the tag is absent (shallow clone), mirroring ``requires_vault`` /
``requires_db`` in the loader and query suites.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE_SCRIPT = REPO_ROOT / "scripts" / "stage-zenodo-bundle.sh"
DOC_DIR = REPO_ROOT / "docs" / "zenodo" / "v1.0.0"
FORM_VALUES = DOC_DIR / "form-values.md"
CITATION_CFF = REPO_ROOT / "CITATION.cff"

#: The published data release under rehearsal (GLOSSARY "data release").
TAG = "v1.0.0-data"

#: Bundle file set per ADR-0002: the byte-exact artifact trio plus the
#: short record README (staged under its upload name, ``README.md``).
BUNDLE_FILES = {"README.md", "load-manifest.json", "maicdb.sql", "maicdb.sqlite"}


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True
    )


def _git_bytes(*args: str) -> bytes:
    """``git`` output as raw bytes (binary blobs; no text decoding)."""
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, check=True
    ).stdout


def _have_tag() -> bool:
    return _git("rev-parse", "-q", "--verify", f"{TAG}^{{tag}}").returncode == 0


requires_tag = pytest.mark.skipif(not _have_tag(), reason=f"git tag {TAG} not found")


def run_stage(out_dir: Path) -> subprocess.CompletedProcess:
    """Run the staging script at its public CLI, into ``out_dir``."""
    return subprocess.run(
        ["bash", str(STAGE_SCRIPT), TAG, str(out_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def staged(tmp_path_factory) -> Path:
    """The staged bundle, shared by the tests below (one staging run)."""
    out = tmp_path_factory.mktemp("zenodo") / "bundle"
    result = run_stage(out)
    assert result.returncode == 0, result.stderr
    return out


@requires_tag
def test_stage_script_creates_the_four_file_bundle(staged: Path):
    """Staging yields exactly the ADR-0002 upload set — nothing improvised."""
    assert {p.name for p in staged.iterdir()} == BUNDLE_FILES


@requires_tag
def test_staged_artifacts_are_byte_identical_to_tag(staged: Path):
    """Each staged artifact equals its ``v1.0.0-data`` tag blob.

    The tag is the independent authority (re-read via ``git cat-file``),
    not the script's own verification pass — so a script that staged from
    the working tree, or a drifted working tree, both fail here.
    """
    for f in ("maicdb.sqlite", "maicdb.sql", "load-manifest.json"):
        blob = _git_bytes("cat-file", "blob", f"{TAG}:db/{f}")
        assert (staged / f).read_bytes() == blob, f


@requires_tag
def test_staged_readme_is_the_committed_source(staged: Path):
    """The bundle's ``README.md`` is the committed record README, verbatim."""
    source = REPO_ROOT / "docs" / "zenodo" / "v1.0.0" / "record-README.md"
    assert (staged / "README.md").read_bytes() == source.read_bytes()


def test_form_values_pin_core_metadata():
    """The form-values doc mirrors the canonical citation strings verbatim.

    CITATION.cff is the editable canonical home of the citation strings
    (ADR-0003); the operator-facing doc must repeat them exactly so nothing
    is improvised on the Zenodo form (issue #17). Runs without the tag —
    the strings live in committed files.
    """
    doc = FORM_VALUES.read_text()
    pref = yaml.safe_load(CITATION_CFF.read_text())["preferred-citation"]
    assert pref["title"] in doc, "title must mirror CITATION.cff verbatim"
    assert pref["version"] in doc
    assert pref["license"] in doc
    for author in pref["authors"]:
        assert author["orcid"].rsplit("/", 1)[-1] in doc, "bare ORCID missing"
        name = f"{author['family-names']}, {author['given-names']}"
        assert name in doc, f"creator display name missing: {name}"


@requires_tag
def test_form_values_checksums_match_staged_bundle(staged: Path):
    """Every staged file's SHA256 appears in the doc's checksum table.

    Recomputed here from the staged bytes — independent of the script's
    printed table — so a doc that lags a README edit fails visibly.
    """
    doc = FORM_VALUES.read_text()
    for f in sorted(BUNDLE_FILES):
        digest = hashlib.sha256((staged / f).read_bytes()).hexdigest()
        assert digest in doc, f"{f}: sha256 {digest} missing from form-values.md"

"""Tests for the Zenodo upload staging (issue #17, ADR-0002/-0003).

Public seam: ``scripts/stage-zenodo-bundle.sh`` (subprocess) and the
staged/docs artifacts it governs. Provenance for every pinned value here is
repo-side, not vault data: the ``v1.0.0-data`` git tag (the published
artifact authority — GLOSSARY "data release"), ``HEAD`` (the committed
record README the bundle ships), and ``CITATION.cff`` (the canonical,
editable home of the citation strings — ADR-0003). Tests skip when the tag
is absent (shallow clone), mirroring ``requires_vault`` / ``requires_db``
in the loader and query suites.

Doc pins are anchored to table cells, not substrings: the operator copies
these exact cells into the effectively-immutable Zenodo record, so a
corrupted cell must fail the suite even when the string still occurs
elsewhere in the doc.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE_SCRIPT = REPO_ROOT / "scripts" / "stage-zenodo-bundle.sh"
DOC_DIR = REPO_ROOT / "docs" / "zenodo" / "v1.0.0"
README_SRC = DOC_DIR / "record-README.md"
#: git path of the record README — one source of truth for every reference.
README_REL = README_SRC.relative_to(REPO_ROOT).as_posix()
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
    try:
        # show-ref, not ^{tag}: lightweight tags count as present too.
        return (
            _git("show-ref", "--verify", "--quiet", f"refs/tags/{TAG}").returncode
            == 0
        )
    except OSError:  # git itself unavailable (exported tarball, stripped PATH)
        return False


requires_tag = pytest.mark.skipif(not _have_tag(), reason=f"git tag {TAG} not found")


def run_stage(out_dir: Path) -> subprocess.CompletedProcess:
    """Run the staging script at its public CLI, into ``out_dir``."""
    return subprocess.run(
        ["bash", str(STAGE_SCRIPT), TAG, str(out_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _row(doc: str, first_cell: str) -> list[str]:
    """Cells of the first markdown table row starting with ``first_cell``."""
    prefix = f"| {first_cell} "
    for line in doc.splitlines():
        if line.startswith(prefix):
            return [c.strip() for c in line.strip().strip("|").split("|")]
    raise AssertionError(f"form-values.md: no table row '{first_cell}'")


def _bt(cell: str) -> str:
    """Strip the backticks a cell wraps its value in."""
    return cell.replace("`", "")


@pytest.fixture(scope="module")
def staged() -> Iterator[Path]:
    """The staged bundle, shared by the tests below (one staging run).

    Skips (rather than errors) without the tag, even if a future test
    forgets the decorator. The script's OUT guard requires dist/, so the
    bundle is staged under gitignored ``dist/pytest-bundle`` and removed
    afterwards.
    """
    if not _have_tag():
        pytest.skip(f"git tag {TAG} not found")
    out = REPO_ROOT / "dist" / "pytest-bundle"
    result = run_stage(out)
    assert result.returncode == 0, result.stderr
    yield out
    shutil.rmtree(out, ignore_errors=True)


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
    """The bundle's ``README.md`` is the HEAD blob of the record README.

    Committed bytes only: the file ships inside an effectively immutable
    Zenodo record, so it must be reproducible from a git object — a dirty
    working-tree README must never be what the script stages.
    """
    blob = _git_bytes("cat-file", "blob", f"HEAD:{README_REL}")
    assert (staged / "README.md").read_bytes() == blob


@requires_tag
def test_default_invocation_stages_into_dist():
    """The exact no-arg command form-values.md documents works as written.

    Re-stages ``dist/zenodo-1.0.0`` (gitignored build output — the
    operator's upload source); intentionally not cleaned up afterwards.
    """
    result = subprocess.run(
        ["bash", str(STAGE_SCRIPT)], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    out = REPO_ROOT / "dist" / "zenodo-1.0.0"
    assert {p.name for p in out.iterdir()} == BUNDLE_FILES


@requires_tag
def test_out_guard_refuses_dist_root_and_preserves_siblings():
    """``OUT="dist/"`` is refused — it must not rm -rf the dist/ tree.

    Regression test for the gate-review MINOR (dead guard patterns): a
    trailing-slash or absolute dist path normalizes to dist itself, which
    the guard rejects; a sibling bundle staged next to it must survive.
    """
    sibling = REPO_ROOT / "dist" / "sibling-bundle"
    sibling.mkdir(parents=True, exist_ok=True)
    (sibling / "keep.txt").write_text("keep")
    try:
        for bad in ("dist/", str(REPO_ROOT / "dist") + "/"):
            result = subprocess.run(
                ["bash", str(STAGE_SCRIPT), TAG, bad],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 1, f"OUT={bad!r} must be refused"
            assert "dist" in result.stderr
            assert (sibling / "keep.txt").read_text() == "keep"
    finally:
        shutil.rmtree(sibling, ignore_errors=True)


def test_form_values_pin_core_metadata():
    """The form-values doc mirrors the canonical citation strings verbatim.

    CITATION.cff is the editable canonical home of the citation strings
    (ADR-0003); the operator-facing doc must repeat them exactly so nothing
    is improvised on the Zenodo form (issue #17). Anchored to the §2 table
    cells — the exact strings the operator copies. Runs without the tag.
    """
    doc = FORM_VALUES.read_text()
    cff = yaml.safe_load(CITATION_CFF.read_text())
    pref = cff["preferred-citation"]

    assert _bt(_row(doc, "Title")[1]) == pref["title"]
    assert _bt(_row(doc, "Version")[1]) == pref["version"]
    assert _bt(_row(doc, "Licenses and rights")[1]).startswith(pref["license"])

    # Creators table: family/given cells and the ORCID cell, exactly.
    for n, author in enumerate(pref["authors"], start=1):
        cells = _row(doc, str(n))
        assert _bt(cells[1]) == author["family-names"], f"creator {n} family"
        assert _bt(cells[2]) == author["given-names"], f"creator {n} given"
        bare = author["orcid"].rsplit("/", 1)[-1]
        assert _bt(cells[-1]) == f"ORCID {bare}", f"creator {n} ORCID"
        # Display name (comma form) must exist in the same row's display cell.
        display = f"{author['family-names']}, {author['given-names']}"
        assert any(_bt(c) == display for c in cells), f"creator {n} display"

    keywords = [k.strip() for k in _bt(_row(doc, "Keywords / subjects")[1]).split(",")]
    assert keywords == cff["keywords"]

    # The repo URL the doc and record README point at is the CFF one.
    assert cff["repository-code"] in doc
    assert cff["repository-code"] in README_SRC.read_text()


@requires_tag
def test_form_values_checksums_match_their_sources(staged: Path):
    """Every §3 checksum row matches the bytes it documents.

    Artifacts: recomputed from the staged bundle. README: the working-tree
    record README — the file the row says it hashes. All of Bytes, SHA256
    and MD5 are pinned (the rehearsal cross-checks all three against the
    rendered Zenodo file list).
    """
    doc = FORM_VALUES.read_text()
    for name in sorted(BUNDLE_FILES):
        data = (README_SRC if name == "README.md" else staged / name).read_bytes()
        cells = _row(doc, f"`{name}`")
        assert cells[1] == str(len(data)), f"{name}: bytes"
        assert _bt(cells[2]) == hashlib.sha256(data).hexdigest(), f"{name}: sha256"
        assert _bt(cells[3]) == hashlib.md5(data).hexdigest(), f"{name}: md5"

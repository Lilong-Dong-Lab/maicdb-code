"""Downloads-page tests (M3-T6, issue #41).

Two seams, both consuming ``render_site()``:

* **fixture-driven (no DB)** — the synthetic data layer from
  test_site_pages.py plus the repo's real ``db/`` artifacts (they ship
  in-repo, so the file-copy behavior is testable without the DB): the
  downloads page renders in both locales, every linked file exists in
  the tree it is served from, sizes shown match the source files, DOI /
  license identifiers come from CITATION.cff, and the unmapped
  disclosure carries the data layer's count.
* **DB-backed** — the full CLI build against the published artifact:
  ``totals.n_unmapped`` is pinned to the census (28) and the disclosure
  renders in both locales.

Real-data provenance: the unmapped count is the published artifact's
census (data-v1.1, read-only SQL, recorded in load-manifest
``counts.unmapped``):

    SELECT COUNT(*) FROM unmapped_measurement;   -- 28
"""

import json
from pathlib import Path

from tests.test_site_build import REPO_ROOT, requires_db, run_build
from tests.test_site_pages import _strings, render_fixture

SITE_DIR = REPO_ROOT / "site"

#: The artifact files the downloads page links (ticket #41 scope), as
#: (repo-relative source, tree-relative link target) — both site-tree
#: copies and page links are derived from this one list in the tests.
DOWNLOAD_FILES = [
    "db/maicdb.sqlite",
    "db/maicdb.sql",
    "db/load-manifest.json",
    "CITATION.cff",
]


def _page(out: Path, locale: str) -> str:
    prefix = "" if locale == "en" else "zh/"
    return (out / prefix / "downloads" / "index.html").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Page presence + copy (fixture)
# --------------------------------------------------------------------------- #
def test_downloads_page_renders_both_locales(tmp_path):
    """The downloads page exists in both locale trees with the localized
    heading and page title (every UI string from the dictionaries)."""
    out = render_fixture(tmp_path)
    for locale in ("en", "zh"):
        html = _page(out, locale)
        assert f"<title>{_strings(locale)['nav_downloads']} · MAIC-DB</title>" in html
        assert _strings(locale)["downloads_heading"] in html


def test_downloads_files_copied_into_both_trees_and_linked(tmp_path):
    """Ticket acceptance "downloads links resolve": each artifact file is
    copied byte-identically into BOTH locale trees (relative-path assets
    only, spec Q6 — the link never crosses a tree), and the downloads
    page links every one of them with the page-depth relative prefix
    (the downloads page sits one level down → ``../``).

    Source bytes: the in-repo published artifacts (data-v1.1), sizes
    ``stat``-ed 2026-11-08 — sqlite 3223552, sql 2249927, manifest 1171,
    CITATION.cff 1338.
    """
    out = render_fixture(tmp_path)
    for tree in (out, out / "zh"):
        for rel in DOWNLOAD_FILES:
            assert (tree / rel).is_file(), (tree.name, rel)
            assert (tree / rel).read_bytes() == (REPO_ROOT / rel).read_bytes(), rel
    for locale in ("en", "zh"):
        html = _page(out, locale)
        for rel in DOWNLOAD_FILES:
            assert f'href="../{rel}"' in html, rel


def test_downloads_sizes_displayed_in_si_units(tmp_path):
    """Each file row shows its size, SI-formatted (one decimal, 1000-based
    kB/MB — the ``ls --si`` convention, NOT the 1024-based ``ls -h``);
    pinned to the published artifacts' byte sizes (see the stat
    provenance above), so a formatting change or a stale manifest fails
    the row, not just the string."""
    out = render_fixture(tmp_path)
    for locale in ("en", "zh"):
        html = _page(out, locale)
        for size in ("3.2 MB", "2.2 MB", "1.2 kB", "1.3 kB"):
            assert size in html, size


def test_downloads_doi_license_identifiers_from_citation_sources(tmp_path):
    """DOI links and license names flow from the canonical sources
    (CITATION.cff via ``_site_facts`` — ADR-0003: the site never
    hardcodes them), version number included; pinned to the published
    values (version DOI 10.5281/zenodo.23620159, concept DOI
    10.5281/zenodo.23620158 — README Releases, dataset v1.0.0,
    CC-BY-4.0 data / MIT code)."""
    out = render_fixture(tmp_path)
    for locale in ("en", "zh"):
        html = _page(out, locale)
        assert "v1.0.0" in html
        assert 'href="https://doi.org/10.5281/zenodo.23620159"' in html
        assert "10.5281/zenodo.23620159" in html
        assert 'href="https://doi.org/10.5281/zenodo.23620158"' in html
        assert "10.5281/zenodo.23620158" in html
        # license rows: data + code, each linking its landing page
        assert 'href="https://creativecommons.org/licenses/by/4.0/"' in html
        assert ">CC-BY-4.0<" in html
        assert 'href="https://opensource.org/licenses/MIT"' in html
        assert ">MIT<" in html


def test_downloads_unmapped_disclosure_both_locales(tmp_path):
    """The unmapped disclosure renders in BOTH locales with the data
    layer's count (the fixture's synthetic 4 — the real pin is the
    DB-backed 16 below), never a hardcoded number in the template."""
    out = render_fixture(tmp_path)
    for locale in ("en", "zh"):
        html = _page(out, locale)
        assert _strings(locale)["downloads_unmapped_heading"] in html
        assert _strings(locale)["downloads_unmapped_note"] in html
        assert ">4<" in html


# --------------------------------------------------------------------------- #
# Full build against the published artifact (DB-backed)
# --------------------------------------------------------------------------- #
@requires_db
def test_db_downloads_unmapped_disclosure_pins_census(tmp_path):
    """The real build's disclosure count is the artifact census —
    ``SELECT COUNT(*) FROM unmapped_measurement`` → 28 (load-manifest
    ``counts.unmapped``; 16 + 7 Duru 2026 + 5 PNAS Po at data-v1.1) —
    surfaced via ``totals`` and rendered in both locales (ticket
    acceptance)."""
    out = tmp_path / "out"
    run_build(out)
    totals = json.loads((out / "_data" / "index.json").read_text(encoding="utf-8"))[
        "totals"
    ]
    assert totals["n_unmapped"] == 28
    site = out / "_site"
    for prefix in ("", "zh/"):
        html = (site / prefix / "downloads" / "index.html").read_text(encoding="utf-8")
        assert ">28<" in html
        locale = "zh" if prefix else "en"
        assert _strings(locale)["downloads_unmapped_note"] in html

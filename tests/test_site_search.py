"""Global-search tests (M3-T6, issue #41).

The search is CLIENT-SIDE (spec Q9: build-time flat index, case-
insensitive substring match, no third-party JS), so the suite pins the
contract at the two seams Python can see:

* **build outputs (fixture)** — the search box renders on every page in
  both locales via the T3 layout, and ``search-index.json`` is copied
  into every locale tree (the deployed root is the rendered tree
  ``site/_site`` — an index left in ``_data/`` only would be unfetchable
  in production);
* **index completeness (DB-backed)** — a Python re-implementation of
  the JS matcher (same fields, same lowercase substring rule; the JS
  lives in ``site/assets/site.js`` and is reviewed against it) must
  return all 12 channels by name AND by every alias, all 7 families,
  all 16 parameters by name and label, and every hit's URL must resolve
  to a page that exists in the rendered tree.

Browser-side behavior (fetch wiring, dropdown DOM) is not executable
here — no Node toolchain by spec Q1 — and is covered by the layout/
asset assertions plus the independent review gate.
"""

import json

from tests.test_site_build import (
    REPO_ROOT,
    requires_db,
    run_build,
)
from tests.test_site_pages import render_fixture

SITE_DIR = REPO_ROOT / "site"


def _strings(locale: str) -> dict:
    return json.loads(
        (SITE_DIR / f"strings.{locale}.json").read_text(encoding="utf-8")
    )


#: Python twin of the JS matcher in site/assets/site.js (searchEntries):
#: case-insensitive substring over the Q9 field set. Kept in lockstep by
#: review — the two must not drift.
def searchEntries(entries: list[dict], query: str) -> list[dict]:
    q = query.strip().lower()
    if not q:
        return []
    hits = []
    for entry in entries:
        kind = entry["type"]
        if kind == "channel":
            fields = [entry["label"], *entry["aliases"], *entry["uniprots"], entry["family"]]
        elif kind == "family":
            fields = [entry["label"]]
        else:
            fields = [entry["name"], entry["label"]]
        if any(q in field.lower() for field in fields):
            hits.append(entry)
    return hits


# --------------------------------------------------------------------------- #
# Search box on every page + index copy (fixture)
# --------------------------------------------------------------------------- #
def test_search_box_renders_on_every_page_both_locales(tmp_path):
    """The site-wide search box lives in the T3 layout (base.html), so
    EVERY rendered page carries it — input id, localized placeholder,
    and the ``data-root`` prefix the JS resolves ``search-index.json``
    and result URLs against (the page's own tree, relative paths only)."""
    out = render_fixture(tmp_path)
    pages = sorted(p for p in out.rglob("*.html"))
    assert pages, "no pages rendered"
    for page in pages:
        html = page.read_text(encoding="utf-8")
        locale = "zh" if page.relative_to(out).parts[0] == "zh" else "en"
        assert 'id="site-search"' in html, page
        assert f'placeholder="{_strings(locale)["search_placeholder"]}"' in html, page
        # data-root: the page's depth inside its own tree
        depth = len(page.parent.relative_to(out if locale == "en" else out / "zh").parts)
        expected = "." if depth == 0 else "/".join([".."] * depth)
        assert f'data-root="{expected}"' in html, page


def test_search_index_copied_into_both_locale_trees(tmp_path):
    """``search-index.json`` is copied byte-identically into each locale
    tree's root (the deployed root is the rendered tree — the data
    layer's ``_data/`` copy never ships), so the JS fetch at
    ``<data-root>/search-index.json`` resolves in both locales."""
    out = render_fixture(tmp_path)
    source = (out.parent / "_data" / "search-index.json")
    assert source.is_file(), "fixture data layer must write the search index"
    for tree in (out, out / "zh"):
        copy = tree / "search-index.json"
        assert copy.is_file(), tree
        assert copy.read_bytes() == source.read_bytes(), tree


@requires_db
def test_db_search_completeness_and_link_resolution(tmp_path):
    """Ticket acceptance, executed: the matcher (Python twin) returns

    * all 12 channels by name AND by every alias (PIEZO1's FAM38A/Mib
      are the census aliases — test_site_build pins them to the index),
    * all 7 families (the census family names, spec §4),
    * all 16 parameters by name and by label (the registry keys/labels),

    and every hit's URL resolves to a page that exists in BOTH rendered
    locale trees (relative resolution: URL stripped of its leading
    ``/`` joined at each tree root).
    """
    out = tmp_path / "out"
    run_build(out)
    entries = json.loads(
        (out / "_site" / "search-index.json").read_text(encoding="utf-8")
    )["entries"]
    site = out / "_site"

    channels = [e for e in entries if e["type"] == "channel"]
    assert len(channels) == 12
    for entry in channels:
        for query in [entry["label"], *entry["aliases"]]:
            assert entry in searchEntries(entries, query), query

    families = [e for e in entries if e["type"] == "family"]
    assert len(families) == 7
    for entry in families:
        assert entry in searchEntries(entries, entry["label"])

    parameters = [e for e in entries if e["type"] == "parameter"]
    assert len(parameters) == 16
    for entry in parameters:
        assert entry in searchEntries(entries, entry["name"])
        assert entry in searchEntries(entries, entry["label"])

    # every hit URL resolves to an existing page in both locale trees
    for entry in entries:
        target = entry["url"].lstrip("/").split("#")[0]
        for tree in (site, site / "zh"):
            assert (tree / target / "index.html").is_file(), (entry["url"], tree)

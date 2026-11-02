"""Site skeleton render tests (M3-T3, issue #38).

Two seams:

* ``render_site()`` in ``site/build.py`` — fixture-driven (no DB): the
  locale loop, switcher links, relative assets, dictionary-driven copy.
* the template files themselves — a static literal scan: every human-read
  string in ``site/templates/`` must come from ``strings.{en,zh}.json``
  (spec Q3: UI strings only ever in locale dictionaries).

Real-data provenance for DB-backed pins: the four home-scale numbers are
the artifact census (data-v1.0, read-only SQL, values recorded in spec
§4 and re-derived for this ticket 2026-11-02):

    SELECT (SELECT COUNT(*) FROM biophysics_experiment)   -- 948
         + (SELECT COUNT(*) FROM bioactivity)             -- 136
         + (SELECT COUNT(*) FROM unmapped_measurement);   --  16  → 1100
    SELECT COUNT(*) FROM publication;                     -- 211
    SELECT COUNT(*) FROM channel;                         --  12
    SELECT COUNT(DISTINCT family) FROM channel;           --   7

Footer identifiers (license names, dataset DOI) are data, not UI copy:
``render_site()`` reads them from ``CITATION.cff`` — the canonical home
of the citation strings per ADR-0003.
"""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from tests.test_site_build import REPO_ROOT, requires_db, run_build

SITE_DIR = REPO_ROOT / "site"
TEMPLATES_DIR = SITE_DIR / "templates"
STRINGS = {
    code: json.loads((REPO_ROOT / "site" / f"strings.{code}.json").read_text())
    for code in ("en", "zh")
}

#: HTML technical attribute values / doctype tokens that are not UI copy
#: (machine-facing vocabulary, never shown as prose).
_TECHNICAL_LITERALS = frozenset(
    {
        "utf-8",
        "width=device-width, initial-scale=1",
        "search",
        "stylesheet",
    }
)

#: Single-token machine strings (CSS hooks, relative asset paths, anchor
#: ids): no spaces, no case — cannot be a human-read sentence. This is
#: the scan's declared boundary: it targets natural-language copy that
#: must be translated, not CSS class names.
_MACHINE_TOKEN = re.compile(r"^[a-z0-9#./_-]+$")

#: Pure punctuation separators ("·", "(", "——") carry no translatable
#: words — allowed wherever they appear.
_PUNCT_ONLY = re.compile(r"^[\W_]+$")


class _LiteralCollector(HTMLParser):
    """Collect text nodes and attribute values from (Jinja-stripped) HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.literals: set[str] = set()

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.literals.add(data.strip())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for _name, value in attrs:
            if value is not None and value.strip():
                self.literals.add(value.strip())


def _template_literals(template: str) -> set[str]:
    """Human-read literals in one template: strip Jinja tags, parse HTML."""
    stripped = re.sub(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", "", template)
    collector = _LiteralCollector()
    collector.feed(stripped)
    return collector.literals


def test_templates_carry_no_hardcoded_ui_strings():
    """Every human-read literal in every template is a dictionary value.

    Spec Q3 / ticket acceptance: UI strings only ever live in
    ``strings.{en,zh}.json`` — a literal inside a template is an
    untranslated string waiting to ship. Allowed alongside dictionary
    values: HTML technical attribute values and single-token machine
    strings (CSS hooks, asset paths) that cannot be prose.
    """
    templates = sorted(TEMPLATES_DIR.glob("*.html"))
    assert templates, f"no templates found under {TEMPLATES_DIR}"

    dictionary_values = {v for s in STRINGS.values() for v in s.values()}
    violations: dict[str, set[str]] = {}
    for path in templates:
        bad = {
            lit
            for lit in _template_literals(path.read_text(encoding="utf-8"))
            if lit not in dictionary_values
            and lit not in _TECHNICAL_LITERALS
            and not _MACHINE_TOKEN.fullmatch(lit)
            and not _PUNCT_ONLY.fullmatch(lit)
        }
        if bad:
            violations[path.name] = bad
    assert not violations, f"hardcoded UI strings in templates: {violations}"


# --------------------------------------------------------------------------- #
# render_site() — fixture-driven (no DB); the seam T4–T7 keep consuming
# --------------------------------------------------------------------------- #
FIXTURE_INDEX = {
    "totals": {
        "n_measurements": 1100,
        "n_channels": 12,
        "n_families": 7,
        "n_publications": 211,
    },
    "families": [
        {
            "family": "PIEZO",
            "channels": [
                {"slug": "piezo1", "n_parameterized_rows": 160},
                {"slug": "piezo2", "n_parameterized_rows": 27},
            ],
        }
    ],
}


def load_build_module():
    """Load ``site/build.py`` as a module (the ``site`` directory is a
    script dir, not a package — and the name collides with stdlib ``site``)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "maicdb_site_build", REPO_ROOT / "site" / "build.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_fixture(tmp_path: Path) -> Path:
    """Materialize the fixture data layer and render both locale trees."""
    data_dir = tmp_path / "_data"
    data_dir.mkdir(parents=True)
    (data_dir / "index.json").write_text(
        json.dumps(FIXTURE_INDEX), encoding="utf-8"
    )
    out_dir = tmp_path / "_site"
    load_build_module().render_site(
        data_dir=data_dir,
        out_dir=out_dir,
        site_dir=SITE_DIR,
        cff_path=REPO_ROOT / "CITATION.cff",
    )
    return out_dir


def test_render_home_both_locales_from_fixture(tmp_path):
    """Home renders in EN (unprefixed) and ZH (/zh/), copy fully
    dictionary-driven, footer identifiers from CITATION.cff."""
    out = render_fixture(tmp_path)
    en = (out / "index.html").read_text(encoding="utf-8")
    zh = (out / "zh" / "index.html").read_text(encoding="utf-8")

    assert "<html lang=\"en\">" in en
    assert "<html lang=\"zh\">" in zh
    # per-page <title>: the home title is the site title, localized
    assert "<title>MAIC-DB — Mechanically Activated Ion Channel Database</title>" in en
    assert "<title>MAIC-DB — 机械激活离子通道数据库</title>" in zh
    # one-liner + scale numbers flow from the data layer fixture
    assert "curated measurements" in en
    assert ">1100<" in en and ">12<" in en and ">7<" in en and ">211<" in en
    assert "条策划测量" in zh
    # family entry links point at the browse-page anchors (data, not copy)
    assert "href=\"./channels/#PIEZO\"" in en
    assert "(2)" in en  # the fixture's PIEZO family holds two channels
    # search box present with the localized placeholder (T6 wires it)
    assert "placeholder=\"Search channels, families, parameters…\"" in en
    # footer identifiers come from CITATION.cff, never the templates
    assert "10.5281/zenodo.23620159" in en
    assert ">MIT<" in en and ">CC-BY-4.0<" in en
    assert "https://creativecommons.org/licenses/by/4.0/" in en


def test_render_language_switcher_links_counterparts(tmp_path):
    """Every rendered page carries a switcher link to its counterpart:
    EN home → ``zh/``, ZH home → back up to the EN tree root."""
    out = render_fixture(tmp_path)
    en = (out / "index.html").read_text(encoding="utf-8")
    zh = (out / "zh" / "index.html").read_text(encoding="utf-8")
    assert "lang=\"zh\" href=\"zh/\"" in en
    assert "lang=\"en\" href=\"../\"" in zh


def test_render_assets_copied_relative_per_tree(tmp_path):
    """Each locale tree carries its own copy of the static assets, and
    pages reference them with relative paths only (Pages-subpath-ready,
    spec Q6) — no absolute URLs, no per-locale asset forks."""
    out = render_fixture(tmp_path)
    for tree in (out, out / "zh"):
        assert (tree / "assets" / "style.css").is_file()
        assert (tree / "assets" / "site.js").is_file()
    en = (out / "index.html").read_text(encoding="utf-8")
    zh = (out / "zh" / "index.html").read_text(encoding="utf-8")
    assert "href=\"./assets/style.css\"" in en
    assert "src=\"./assets/site.js\"" in en
    assert "href=\"./assets/style.css\"" in zh
    assert 'href="/' not in en and "src='/" not in en
    assert 'href="/' not in zh and "src='/" not in zh


def test_render_is_byte_stable_from_fixture(tmp_path):
    """Same fixture data + same code → byte-identical trees (spec §6)."""
    first = render_fixture(tmp_path / "run-a")
    second = render_fixture(tmp_path / "run-b")
    files_a = sorted(p.relative_to(first) for p in first.rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(second) for p in second.rglob("*") if p.is_file())
    assert files_a == files_b and files_a
    for rel in files_a:
        assert (first / rel).read_bytes() == (second / rel).read_bytes(), rel

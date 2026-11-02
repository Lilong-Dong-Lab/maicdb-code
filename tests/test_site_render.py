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

#: Attributes whose values are CSS/DOM hooks, not copy: a single-token
#: lowercase value here is a machine string, not a sentence.
_STRUCTURAL_ATTRS = frozenset({"class", "id", "name"})

#: Single-token machine strings (CSS hooks, relative asset paths, anchor
#: ids): no spaces, no case — cannot be a human-read sentence. Allowed
#: ONLY in structural attributes and path-shaped attribute remainders
#: (see test_templates_carry_no_hardcoded_ui_strings); a bare lowercase
#: word as a TEXT node is a violation even if token-shaped.
_MACHINE_TOKEN = re.compile(r"^[a-z0-9#./_-]+$")

#: Pure punctuation separators ("·", "(", "——") carry no translatable
#: words — allowed wherever they appear.
_PUNCT_ONLY = re.compile(r"^[\W_]+$")


class _LiteralCollector(HTMLParser):
    """Collect (kind, value) pairs from (Jinja-stripped) HTML: text nodes
    as ``("text", s)`` and attribute values as ``("attr:<name>", s)``."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.literals: list[tuple[str, str]] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.literals.append(("text", data.strip()))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value is not None and value.strip():
                self.literals.append((f"attr:{name}", value.strip()))


def _template_literals(template: str) -> list[tuple[str, str]]:
    """Literals in one template.

    Two sources, both counted as template-source copy:
    * Jinja expression/statement string literals (``{{ "Welcome" }}``,
      ``{% if x == "piezo1" %}``) — a natural-language string inside an
      expression ships untranslated exactly like a text node, so the
      scan must not silently strip it;
    * the HTML that remains after stripping Jinja tags: text nodes and
      attribute values via :class:`_LiteralCollector`.
    """
    literals: list[tuple[str, str]] = []
    # {{ ... }} output expressions: any quoted literal renders verbatim —
    # natural language there ships untranslated, so it is scanned as copy.
    for body in re.findall(r"\{\{(.*?)\}\}", template, re.DOTALL):
        literals.extend(
            ("expr", quoted)
            for pair in re.findall(r'"([^"]*)"|\'([^\']*)\'', body)
            for quoted in pair
            if quoted.strip()
        )
    # {% ... %} statements (incl. whitespace-control forms {%- / -%}):
    # same rule, EXCEPT template-reference statements (extends/include/
    # import/from) whose quoted literals are template filenames — machine
    # strings, like a class attribute.
    for keyword, rest in re.findall(r"\{%[-+]?\s*(\w+)(.*?)%\}", template, re.DOTALL):
        kind = "tmpl" if keyword in {"extends", "include", "import", "from"} else "expr"
        literals.extend(
            (kind, quoted)
            for pair in re.findall(r'"([^"]*)"|\'([^\']*)\'', rest)
            for quoted in pair
            if quoted.strip()
        )
    stripped = re.sub(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", "", template)
    collector = _LiteralCollector()
    collector.feed(stripped)
    literals.extend(collector.literals)
    return literals


def test_templates_carry_no_hardcoded_ui_strings():
    """Every human-read literal in every template is a dictionary value.

    Spec Q3 / ticket acceptance: UI strings only ever live in
    ``strings.{en,zh}.json`` — a literal inside a template is an
    untranslated string waiting to ship. The scan strips every Jinja
    expression and parses what remains; anything natural-language is a
    violation (see ``_is_copy_violation`` for the exact allow rules —
    dictionary values are NOT an allow rule, because the dictionaries
    reach a page only through expressions; template-source text is
    hardcoded by definition).
    """
    templates = sorted(TEMPLATES_DIR.glob("*.html"))
    assert templates, f"no templates found under {TEMPLATES_DIR}"

    violations: dict[str, set[str]] = {}
    for path in templates:
        bad = {
            f"{kind}: {lit!r}"
            for kind, lit in _template_literals(path.read_text(encoding="utf-8"))
            if _is_copy_violation(kind, lit)
        }
        if bad:
            violations[path.name] = bad
    assert not violations, f"hardcoded UI strings in templates: {violations}"


def _is_copy_violation(kind: str, lit: str) -> bool:
    """The scan's allow/deny rule (shared with the self-test below).

    The dictionaries enter a page ONLY through ``{{ strings.* }}``
    expressions, which the scan strips — so any natural-language residue
    left in the TEMPLATE SOURCE is a hardcoded string, even when its
    value happens to equal a dictionary entry (a ZH render of the same
    template would ship it untranslated). What may legitimately remain:
    pure punctuation, technical attribute values, CSS/DOM hooks, and
    path-shaped attribute skeletons like ``/channels/#``.
    """
    if _PUNCT_ONLY.fullmatch(lit):
        return False
    if lit in _TECHNICAL_LITERALS:
        return False
    if kind.removeprefix("attr:") in _STRUCTURAL_ATTRS and _MACHINE_TOKEN.fullmatch(lit):
        return False
    if kind == "tmpl" and _MACHINE_TOKEN.fullmatch(lit):
        return False
    if (
        kind.startswith("attr:")
        and ("/" in lit or lit.startswith("#"))
        and _MACHINE_TOKEN.fullmatch(lit)
    ):
        return False
    return True


def test_template_scan_rejects_a_bare_lowercase_text_node():
    """Scanner self-test: a token-shaped TEXT node ("channels" — a real
    dictionary value!) and a literal URL attribute both fail the scan —
    the real-template pass above is therefore not vacuous. The spec's
    boundary: template-source text is hardcoded by definition, because
    the dictionaries reach the page only through expressions."""
    assert _is_copy_violation("text", "channels")
    assert _is_copy_violation("text", "Channels")  # equals nav_home — still hardcoded
    assert _is_copy_violation("attr:href", "https://example.com/page")
    # gate MINOR-3 vector: a string literal INSIDE a Jinja expression
    # would previously be stripped unexamined — it must fail too
    assert ("expr", "Welcome to the database") in _template_literals(
        '<p>{{ "Welcome to the database" }}</p>'
    )
    assert _is_copy_violation("expr", "Welcome to the database")
    assert _is_copy_violation("expr", "piezo1")  # {% if slug == "piezo1" %} — data, not copy
    # whitespace-control statement tags ({%- / -%}) must not escape the
    # scan (gate re-review: the bare {% form was covered, this was not)
    assert ("expr", "piezo1") in _template_literals(
        '{%- if slug == "piezo1" -%}x{% endif %}'
    )
    assert _template_literals("<p>{{ strings.home_tagline }}</p>") == []
    # template-reference statements name files, not copy
    assert ("tmpl", "base.html") in _template_literals('{% extends "base.html" %}')
    assert not _is_copy_violation("tmpl", "base.html")
    # the legitimate residues stay allowed
    assert not _is_copy_violation("text", "·")
    assert not _is_copy_violation("attr:class", "site-header")
    assert not _is_copy_violation("attr:href", "/channels/#")


# --------------------------------------------------------------------------- #
# render_site() — fixture-driven (no DB); the seam T4–T7 keep consuming.
# Since T4 the fixture data layer is the synthetic index + card payloads
# defined in test_site_pages.py (render_site reads channel JSONs).
# --------------------------------------------------------------------------- #
from tests.test_site_pages import SYNTH_CARDS, SYNTH_INDEX  # noqa: E402

FIXTURE_INDEX = SYNTH_INDEX


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
    (data_dir / "channels").mkdir(parents=True)
    (data_dir / "index.json").write_text(
        json.dumps(FIXTURE_INDEX), encoding="utf-8"
    )
    for slug, card in SYNTH_CARDS.items():
        (data_dir / "channels" / f"{slug}.json").write_text(
            json.dumps(card), encoding="utf-8"
        )
    out_dir = tmp_path / "_site"
    load_build_module().render_site(
        data_dir=data_dir,
        out_dir=out_dir,
        site_dir=SITE_DIR,
        repo_root=REPO_ROOT,
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
    assert "href=\"./channels/#TESTFAM\"" in en
    assert "(2)" in en  # the fixture's TESTFAM family holds two channels
    # search box present with the localized placeholder (T6 wires it)
    assert "placeholder=\"Search channels, families, parameters…\"" in en
    # footer identifiers come from CITATION.cff and README Releases
    # (dataset version DOI + concept DOI), never the templates
    assert "10.5281/zenodo.23620159" in en
    assert "10.5281/zenodo.23620158" in en
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

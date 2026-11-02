"""Browse + channel-card page tests (M3-T4, issue #39).

Two seams, both consuming ``render_site()``:

* **fixture-driven (no DB)** — synthetic card payloads whose SHAPE mirrors
  the ``channel_card()`` / ``bioactivity_card()`` payload contracts. Every
  value below is synthetic (NOT real-data provenance — the DB-backed pins
  live in the ``requires_db`` tests and in test_site_build.py).
* **DB-backed** — the full CLI build against the published artifact:
  12 card pages × 2 locales, the anchor-id set == the measurement_id set,
  the PIEZO frozen-banner semantics, zero-row blocks visible, bioactivity
  block presence.

The frozen-banner semantics walker is the HTML translation of the M1
pattern (``test_query.test_frozen_layer_wording``): assert the boilerplate
ATTACHES, and that no affirmative verification status renders — matched by
semantics (attribute names / whole status-valued text nodes), never by
substring, because evidence prose legitimately contains "verified".
"""

import json
import re
from html.parser import HTMLParser
from pathlib import Path


from tests.test_site_build import REPO_ROOT, requires_db, run_build

SITE_DIR = REPO_ROOT / "site"

#: Synthetic §6.7 stand-in — the page must render whatever disclosure the
#: payload carries verbatim (the real wording is pinned DB-side, against
#: ``FROZEN_LAYER_DISCLOSURE`` from the library).
_SYNTH_DISCLOSURE = "synthetic frozen-layer disclosure for fixture pages"

FROZEN1_CARD = {
    "gene": {
        "maicdb_id": "MAIC:CH:TEST01",
        "gene_symbol": "FROZEN1",
        "gene_aliases": ["ALIASA", "ALIASB"],
        "organism": "Test organism",
        "organism_taxid": 9999,
        "uniprot_accession": "P00000",
        "protein_name": None,
        "family": "TESTFAM",
        "activation_mechanism": "Test mechanism",
        "ortholog_group": "FROZEN1",
        "summary": None,
    },
    "frozen_layer_disclosure": _SYNTH_DISCLOSURE,
    "parameters": {
        "p50": {
            "label": "synthetic P50 threshold",
            "n_rows": 1,
            "rows": [
                {
                    "maicdb_id": "MAIC:BX:T0001",
                    "measurement_id": "FROZEN1-EX-00001",
                    "value": -30.0,
                    "unit": "mmHg",
                    "value_as_reported": "-30",
                    "unit_as_reported": "mm Hg",
                    "evidence_quote": "synthetic quote with verified prose",
                    "evidence_location": "Results (Fig. 1A)",
                    "confidence": "high",
                    "extractor_note": "合成提取注记：原样中文显示",
                    "condition_key": "synthetic_condition",
                    "n": "4",
                }
            ],
        },
        "conductance": {"label": "synthetic conductance", "n_rows": 0, "rows": []},
        "osmotic_threshold": {
            "label": "synthetic osmotic threshold",
            "n_rows": 1,
            "rows": [
                {
                    "maicdb_id": "MAIC:BX:T0002",
                    "measurement_id": "FROZEN1-EX-00002",
                    "value": 300.0,
                    "unit": None,
                    "value_as_reported": "300",
                    "unit_as_reported": None,
                    "evidence_quote": "synthetic unit-less quote",
                    "evidence_location": "Results (Fig. 2B)",
                    "confidence": "low",
                    "extractor_note": None,
                    "condition_key": "synthetic_condition_2",
                    "n": None,
                }
            ],
        },
    },
    "bioactivity": {
        "gene": "FROZEN1",
        "n_rows": 1,
        "frozen_layer_disclosure": _SYNTH_DISCLOSURE,
        "rows": [
            {
                "maicdb_id": "MAIC:BA:T0001",
                "measurement_id": "FROZEN1-EX-00003",
                "compound_name": "Synthetic compound",
                "activity_type": "IC50",
                "activity_value": 0.4,
                "activity_units": "nM",
                "relation": "=",
                "source_db": "LITERATURE",
                "assay_description": "synthetic assay description",
                "evidence_quote": "synthetic bioactivity quote",
                "evidence_location": "Results (Fig. 3C)",
                "confidence": "medium",
                "extractor_note": "合成生物活性注记",
                "condition_key": "synthetic_bio_condition",
                "n": "8",
            }
        ],
    },
}

PLAIN2_CARD = {
    "gene": {
        "maicdb_id": "MAIC:CH:TEST02",
        "gene_symbol": "PLAIN2",
        "gene_aliases": [],
        "organism": "Test organism 2",
        "organism_taxid": 8888,
        "uniprot_accession": None,
        "protein_name": "Test protein",
        "family": "TESTFAM",
        "activation_mechanism": None,
        "ortholog_group": None,
        "summary": "A synthetic summary.",
    },
    "parameters": {
        "p50": {"label": "synthetic P50 threshold", "n_rows": 0, "rows": []},
        "slope": {"label": "synthetic slope", "n_rows": 0, "rows": []},
    },
}

SYNTH_INDEX = {
    # totals mirror the artifact census only so assertions read like the
    # real page (census SQL in test_site_render.py's docstring); the
    # per-channel values are deliberately arbitrary.
    "totals": {
        "n_measurements": 1100,
        "n_channels": 12,
        "n_families": 7,
        "n_publications": 211,
        # synthetic stand-in (real census: 16 — the DB-backed pin lives
        # in test_site_downloads.py); asserts the count is data-driven
        "n_unmapped": 4,
    },
    "families": [
        {
            "family": "TESTFAM",
            "channels": [
                {
                    "slug": "frozen1",
                    "gene_symbol": "FROZEN1",
                    "n_parameterized_rows": 2,
                    "n_bioactivity_rows": 1,
                    "n_qualitative_rows": 0,
                    "n_parameters_covered": 2,
                    "parameters": {"p50": 1, "conductance": 0, "osmotic_threshold": 1},
                },
                {
                    "slug": "plain2",
                    "gene_symbol": "PLAIN2",
                    "n_parameterized_rows": 0,
                    "n_bioactivity_rows": 0,
                    "n_qualitative_rows": 2,
                    "n_parameters_covered": 0,
                    "parameters": {"p50": 0, "slope": 0},
                },
            ],
        }
    ],
    # parameter index (M3-T5): n_rows = sum of the comparison's per-bucket
    # counts (the data layer derives it the same way, never hand-copied)
    "parameters": [
        {
            "name": "p50",
            "label": "synthetic P50 threshold",
            "n_rows": 3,
        },
        {
            "name": "ion_selectivity_ratio",
            "label": "synthetic ion selectivity ratio",
            "n_rows": 3,
        },
    ],
}

#: The synthetic cards, keyed by slug; test_site_render's home-page
#: fixture renders the same data layer (render_site reads channel
#: JSONs since T4 — the helpers are shared, not forked).
SYNTH_CARDS = {"frozen1": FROZEN1_CARD, "plain2": PLAIN2_CARD}

#: Synthetic parameter-comparison docs (M3-T5), mirroring the library's
#: ``export(format="json")`` payload shape — the data layer writes that
#: output verbatim, so the fixture must match it field for field:
#: doc-level ``sign_convention`` (threshold params) / ``frozen_layer_
#: disclosure`` (a comparison always lists PIEZO rows, zero-count ones
#: included), per-row ``note`` + ``median=None`` on direction-blind
#: ratio rows, ``unit=None`` buckets for unit-less/NULL-unit params.
#: All values synthetic; real-data pins live in test_site_parameters.py.
SYNTH_P50_COMPARISON = {
    "parameter": "p50",
    "rows": [
        {
            "gene": "FROZEN1",
            "family": "TESTFAM",
            "parameter": "p50",
            "unit": "mmHg",
            "count": 2,
            "min": -30.0,
            "median": -25.0,
            "max": -20.0,
            "measurement_ids": ["FROZEN1-EX-00001", "FROZEN1-EX-00004"],
            "frozen_layer_disclosure": _SYNTH_DISCLOSURE,
        },
        {
            "gene": "FROZEN1",
            "family": "TESTFAM",
            "parameter": "p50",
            "unit": "psi",
            "count": 1,
            "min": -1.5,
            "median": -1.5,
            "max": -1.5,
            "measurement_ids": ["FROZEN1-EX-00005"],
            "frozen_layer_disclosure": _SYNTH_DISCLOSURE,
        },
        {
            "gene": "PLAIN2",
            "family": "TESTFAM",
            "parameter": "p50",
            "unit": None,
            "count": 0,
            "min": None,
            "median": None,
            "max": None,
            "measurement_ids": [],
        },
    ],
    "sign_convention": "synthetic sign-convention wording",
    "frozen_layer_disclosure": _SYNTH_DISCLOSURE,
}

SYNTH_RATIO_COMPARISON = {
    "parameter": "ion_selectivity_ratio",
    "rows": [
        {
            "gene": "PLAIN2",
            "family": "TESTFAM",
            "parameter": "ion_selectivity_ratio",
            "unit": None,
            "count": 3,
            "min": 1.2,
            "median": None,
            "max": 40.0,
            "measurement_ids": ["PLAIN2-EX-00001", "PLAIN2-EX-00002", "PLAIN2-EX-00003"],
            "note": "synthetic ratio-median note",
        },
        {
            "gene": "FROZEN1",
            "family": "TESTFAM",
            "parameter": "ion_selectivity_ratio",
            "unit": None,
            "count": 0,
            "min": None,
            "median": None,
            "max": None,
            "measurement_ids": [],
            "frozen_layer_disclosure": _SYNTH_DISCLOSURE,
        },
    ],
    "frozen_layer_disclosure": _SYNTH_DISCLOSURE,
}

SYNTH_PARAMETERS: dict[str, dict] = {
    "p50": SYNTH_P50_COMPARISON,
    "ion_selectivity_ratio": SYNTH_RATIO_COMPARISON,
}

#: Synthetic search index (M3-T6): mirrors the data layer's flat entry
#: list (spec Q9 field set); test_site_search.py's Python matcher twin
#: consumes the same shape. All values synthetic.
SYNTH_SEARCH_INDEX = {
    "entries": [
        {
            "type": "channel",
            "slug": "frozen1",
            "label": "FROZEN1",
            "family": "TESTFAM",
            "aliases": ["ALIASA", "ALIASB"],
            "uniprots": ["P00000"],
            "url": "/channels/frozen1/",
        },
        {
            "type": "channel",
            "slug": "plain2",
            "label": "PLAIN2",
            "family": "TESTFAM",
            "aliases": [],
            "uniprots": [],
            "url": "/channels/plain2/",
        },
        {"type": "family", "label": "TESTFAM", "url": "/channels/#TESTFAM"},
        {
            "type": "parameter",
            "name": "p50",
            "label": "synthetic P50 threshold",
            "url": "/parameters/p50/",
        },
        {
            "type": "parameter",
            "name": "ion_selectivity_ratio",
            "label": "synthetic ion selectivity ratio",
            "url": "/parameters/ion_selectivity_ratio/",
        },
    ]
}


def load_build_module():
    """Load ``site/build.py`` as a module (mirrors test_site_render)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "maicdb_site_build_pages", REPO_ROOT / "site" / "build.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_fixture(tmp_path: Path) -> Path:
    """Materialize the synthetic data layer (index + channel JSONs +
    parameter-comparison JSONs) and render both locale trees."""
    data_dir = tmp_path / "_data"
    (data_dir / "channels").mkdir(parents=True)
    (data_dir / "parameters").mkdir(parents=True)
    (data_dir / "index.json").write_text(
        json.dumps(SYNTH_INDEX), encoding="utf-8"
    )
    for slug, card in SYNTH_CARDS.items():
        (data_dir / "channels" / f"{slug}.json").write_text(
            json.dumps(card), encoding="utf-8"
        )
    for name, comparison in SYNTH_PARAMETERS.items():
        (data_dir / "parameters" / f"{name}.json").write_text(
            json.dumps(comparison), encoding="utf-8"
        )
    (data_dir / "search-index.json").write_text(
        json.dumps(SYNTH_SEARCH_INDEX), encoding="utf-8"
    )
    out_dir = tmp_path / "_site"
    load_build_module().render_site(
        data_dir=data_dir,
        out_dir=out_dir,
        site_dir=SITE_DIR,
        repo_root=REPO_ROOT,
    )
    return out_dir


def _strings(locale: str) -> dict:
    return json.loads(
        (SITE_DIR / f"strings.{locale}.json").read_text(encoding="utf-8")
    )


def _details_blocks(html: str) -> list[tuple[str | None, str]]:
    """``(id, inner_html)`` per top-level ``<details>`` block."""
    return re.findall(r"<details\b([^>]*)>(.*?)</details>", html, re.DOTALL)


def _details_ids(html: str) -> set[str]:
    ids = set()
    for attrs, _ in _details_blocks(html):
        match = re.search(r'\bid="([^"]+)"', attrs)
        if match:
            ids.add(match.group(1))
    return ids


# --------------------------------------------------------------------------- #
# Browse page (fixture)
# --------------------------------------------------------------------------- #
def test_browse_renders_family_grouped_grid(tmp_path):
    """Family sections anchor the home/search entry links; each channel
    card shows gene symbol, the parameterized-row count, parameter
    coverage, and the qualitative / bioactivity riders ONLY where the
    counts are non-zero (data-driven, never hardcoded)."""
    out = render_fixture(tmp_path)
    for locale, prefix in (("en", ""), ("zh", "zh/")):
        html = (out / prefix / "channels" / "index.html").read_text(encoding="utf-8")
        # family section carries the anchor id the home page links to
        assert 'id="TESTFAM"' in html
        assert "TESTFAM" in html  # heading text (data)
        # channel entries link to the card pages
        assert 'href="../channels/frozen1/"' in html
        assert 'href="../channels/plain2/"' in html
        # parameterized-row count + coverage render as numbers
        assert ">2<" in html and ">0<" in html
        assert "2 / 3" in html and "0 / 2" in html
        # riders: non-zero only. The index order is frozen1 then plain2, so
        # frozen1's card segment is bounded by plain2's link and plain2's
        # runs to the end of the family section.
        rider = _strings(locale)["browse_qualitative_rider"]
        after_frozen1 = html.split('href="../channels/frozen1/"', 1)[1]
        frozen1_card = after_frozen1.split('href="../channels/plain2/"', 1)[0]
        plain2_card = html.split('href="../channels/plain2/"', 1)[1]
        assert rider not in frozen1_card  # frozen1: 0 qualitative rows
        assert rider in plain2_card  # plain2: 2 qualitative rows
        assert "+2" in plain2_card
        assert ">1<" in frozen1_card  # bioactivity rider (1 row)


# --------------------------------------------------------------------------- #
# Channel card page (fixture)
# --------------------------------------------------------------------------- #
def test_card_identity_header_renders_all_eleven_fields(tmp_path):
    """All 11 identity fields render; NULL fields show the localized
    not-recorded marker, never an empty cell or a Python None."""
    out = render_fixture(tmp_path)
    html = (out / "channels" / "frozen1" / "index.html").read_text(encoding="utf-8")
    assert "MAIC:CH:TEST01" in html
    assert "FROZEN1" in html
    assert "ALIASA, ALIASB" in html
    assert "Test organism" in html and "9999" in html
    assert "P00000" in html and "TESTFAM" in html
    assert "Test mechanism" in html
    # NULL fields: identity protein_name + summary, the osmotic row's
    # extractor_note and n → four not-recorded markers (localized)
    assert html.count("(not recorded)") == 4
    assert "None" not in html  # no Python None leaks into the page

    zh = (out / "zh" / "channels" / "frozen1" / "index.html").read_text(encoding="utf-8")
    marker_zh = _strings("zh")["card_not_recorded"]
    assert zh.count(marker_zh) == 4
    assert "<title>FROZEN1 · MAIC-DB</title>" in html
    assert "<html lang=\"zh\">" in zh


def test_card_parameter_blocks_zero_rows_and_sign_note(tmp_path):
    """Every registered block renders with its count; zero-row blocks stay
    visible with the localized note; the sign-convention note appears on
    threshold parameters ONLY (p50 yes, conductance no) and its EN text is
    the library's wording (CLI parity, locked by the parity test below)."""
    from maicdb.query import SIGN_CONVENTION_NOTE

    out = render_fixture(tmp_path)
    html = (out / "channels" / "frozen1" / "index.html").read_text(encoding="utf-8")
    # counts in the block headings: (1), (0), (1)
    assert "(1)" in html and "(0)" in html
    # zero-row note present exactly once (the conductance block)
    assert html.count(_strings("en")["card_zero_rows_note"]) == 1
    # sign note: on the p50 block only — once in the whole page
    assert html.count(SIGN_CONVENTION_NOTE) == 1
    # as-reported pair rides next to the value (as-recorded unit spelling)
    assert "(as reported: -30 mm Hg)" in html
    # unit-less row: value without a unit word, no "None"
    assert "300.0" in html


def test_card_evidence_expansion_hidden_until_expanded(tmp_path):
    """Evidence (quote, location, confidence, extractor note, condition
    key, n) lives INSIDE the ``<details>`` block — collapsed by default in
    a browser, so numbers are visible while evidence is one click away.
    The Chinese extractor note renders verbatim in BOTH locales."""
    out = render_fixture(tmp_path)
    for prefix in ("", "zh/"):
        html = (
            out / prefix / "channels" / "frozen1" / "index.html"
        ).read_text(encoding="utf-8")
        blocks = _details_blocks(html)
        assert len(blocks) == 3  # 2 parameter rows + 1 bioactivity row
        all_inner = "\n".join(inner for _, inner in blocks)
        for evidence in (
            "synthetic quote with verified prose",
            "Results (Fig. 1A)",
            "high",
            "合成提取注记：原样中文显示",
            "synthetic_condition",
            "4",
            "synthetic bioactivity quote",
            "Synthetic compound",
            "synthetic assay description",
        ):
            assert evidence in all_inner, evidence
        # summaries carry the numbers, not the evidence prose
        for summary in re.findall(r"<summary>(.*?)</summary>", html, re.DOTALL):
            assert "synthetic quote" not in summary
            assert "Results (Fig." not in summary


def test_card_anchor_ids_equal_measurement_ids(tmp_path):
    """Anchor id = measurement_id (spec Q10): the set of ``id`` attributes
    on row ``<details>`` equals the set of non-null measurement_ids across
    parameter + bioactivity rows."""
    out = render_fixture(tmp_path)
    html = (out / "channels" / "frozen1" / "index.html").read_text(encoding="utf-8")
    expected = {
        r["measurement_id"]
        for block in FROZEN1_CARD["parameters"].values()
        for r in block["rows"]
    } | {r["measurement_id"] for r in FROZEN1_CARD["bioactivity"]["rows"]}
    assert _details_ids(html) == expected


def test_card_bioactivity_block_where_data_exists(tmp_path):
    """frozen1 (data) renders the bioactivity block with its compound and
    activity; plain2 (no data) renders no block — no heading either."""
    out = render_fixture(tmp_path)
    frozen1 = (out / "channels" / "frozen1" / "index.html").read_text(encoding="utf-8")
    plain2 = (out / "channels" / "plain2" / "index.html").read_text(encoding="utf-8")
    heading = _strings("en")["card_bioactivity_heading"]
    assert heading in frozen1
    assert "IC50 = 0.4 nM" in frozen1
    assert heading not in plain2
    # qualitative disclosure: plain2 carries 2, frozen1 none
    assert "2" in plain2 and _strings("en")["card_qualitative_note"] in plain2
    assert _strings("en")["card_qualitative_note"] not in frozen1


def test_card_frozen_banner_semantics_fixture(tmp_path):
    """The banner renders the payload's disclosure in EN and the curated
    zh wording in ZH (the T-LOC overlay replaces the payload disclosure
    globally — spec Q3); the semantics walker (below) finds no
    affirmative verification status on any of the four pages even though
    the fixture quote deliberately contains "verified" as prose."""
    zh_disclosure = json.loads(
        (SITE_DIR / "zh-content.json").read_text(encoding="utf-8")
    )["frozen_layer_disclosure"]
    out = render_fixture(tmp_path)
    for prefix, expected in (("", _SYNTH_DISCLOSURE), ("zh/", zh_disclosure)):
        html = (
            out / prefix / "channels" / "frozen1" / "index.html"
        ).read_text(encoding="utf-8")
        assert expected in html
        assert not list(affirmative_status_hits(html))
        plain = (
            out / prefix / "channels" / "plain2" / "index.html"
        ).read_text(encoding="utf-8")
        assert _SYNTH_DISCLOSURE not in plain and zh_disclosure not in plain
        assert not list(affirmative_status_hits(plain))


# --------------------------------------------------------------------------- #
# The frozen-banner semantics walker (M1 pattern, HTML translation)
# --------------------------------------------------------------------------- #
#: A text node that *is* an affirmative verification status (whole-node
#: match, lowercased — the same set as test_query's walker, plus the
#: Chinese whole-value forms: the ZH tree renders Chinese since T-LOC,
#: so the walker must bite on both languages).
_AFFIRMATIVE_STATUSES = {
    "verified",
    "re-verified",
    "verification: verified",
    "status: verified",
    "verified: true",
    "已核验",
    "已验证",
    "核验：已核验",
}


class _StatusScanner(HTMLParser):
    """Collect affirmative-status hits from rendered HTML: attribute NAMES
    carrying a verification marker (``data-verified``, ``verification``),
    ANY attribute whose whole value IS a status (``aria-label="verified"``
    — the M1 walker's any-key exact-value rule), badge-shaped class/id
    word sets containing ``verified``, and whole text nodes that ARE a
    status."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hits: list[str] = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if value is None:
                continue
            if "verif" in name.lower():
                self.hits.append(f"attr-name:{name}={value}")
            if value.strip().lower() in _AFFIRMATIVE_STATUSES:
                self.hits.append(f"attr-value:{name}={value}")
            elif name.lower() in {"class", "id"} and "verified" in value.lower().split():
                self.hits.append(f"badge:{name}={value}")

    def handle_data(self, data):
        if data.strip().lower() in _AFFIRMATIVE_STATUSES:
            self.hits.append(f"text:{data.strip()}")


def affirmative_status_hits(html: str):
    """Yield affirmative-verification hits; empty means the page renders no
    affirmative status. Substring-free by construction: prose containing
    "verified" (evidence quotes, the §6.7 boilerplate itself) passes."""
    scanner = _StatusScanner()
    scanner.feed(html)
    return scanner.hits


def test_status_scanner_rejects_affirmative_forms():
    """Scanner self-test (guard-test escape vectors): each bad form is
    caught; prose forms pass. The real-page passes above are therefore
    not vacuous."""
    assert list(affirmative_status_hits('<em data-verified="yes">ok</em>'))
    assert list(affirmative_status_hits('<span class="verified">ok</span>'))
    assert list(affirmative_status_hits('<span class="badge verified">ok</span>'))
    assert list(affirmative_status_hits('<span aria-label="verified">ok</span>'))
    assert list(affirmative_status_hits('<span data-status="verified">ok</span>'))
    assert list(affirmative_status_hits('<p>Verified</p>'))
    assert list(affirmative_status_hits("<p>status: verified</p>"))
    # prose legitimately containing the word — passes
    assert not list(affirmative_status_hits("<p>not been re-verified</p>"))
    assert not list(affirmative_status_hits("<p>we verified the recording</p>"))
    assert not list(affirmative_status_hits('<a class="verified-link">x</a>'))
    assert not list(affirmative_status_hits('<a title="not been re-verified">x</a>'))
    # a punctuated status node is prose-shaped (trailing period), not a
    # bare status — the same exact-match boundary as the M1 walker
    assert not list(affirmative_status_hits("<p>Verified.</p>"))
    # Chinese status forms (T-LOC): whole-value hits in text and in any
    # attribute; negation/punctuated prose stays outside the set
    assert list(affirmative_status_hits("<p>已核验</p>"))
    assert list(affirmative_status_hits('<span aria-label="已验证">x</span>'))
    assert list(affirmative_status_hits("<p>核验：已核验</p>"))
    assert not list(affirmative_status_hits("<p>已核验。</p>"))
    assert not list(affirmative_status_hits("<p>尚未经过核验</p>"))


def test_sign_convention_en_dictionary_matches_library():
    """The EN dictionary's sign-convention note is the library's wording
    verbatim — the site page and the CLI card disclose the same sentence
    (parity lock; the ZH translation is the T4 in-ticket translation)."""
    from maicdb.query import SIGN_CONVENTION_NOTE

    assert _strings("en")["sign_convention_note"] == SIGN_CONVENTION_NOTE


# --------------------------------------------------------------------------- #
# Full build against the published artifact (DB-backed)
# --------------------------------------------------------------------------- #
@requires_db
def test_db_card_pages_exist_in_both_locales(tmp_path):
    """12 card pages × 2 locales + the browse page × 2 (ticket
    acceptance). Slugs pinned to the census (spec §4)."""
    from tests.test_site_build import EXPECTED_SLUGS

    out = tmp_path / "out"
    run_build(out)
    site = out / "_site"
    for slug in EXPECTED_SLUGS:
        assert (site / "channels" / slug / "index.html").is_file(), slug
        assert (site / "zh" / "channels" / slug / "index.html").is_file(), slug
    assert (site / "channels" / "index.html").is_file()
    assert (site / "zh" / "channels" / "index.html").is_file()


@requires_db
def test_db_anchor_ids_equal_measurement_ids_piezo1(tmp_path):
    """The rendered PIEZO1 card's row anchors are exactly its non-null
    measurement_ids — 160 biophysics rows + 14 bioactivity rows (census
    in test_site_build.py's docstring), all attributed in data-v1.0."""
    out = tmp_path / "out"
    run_build(out)
    card = json.loads(
        (out / "_data" / "channels" / "piezo1.json").read_text(encoding="utf-8")
    )
    expected = {
        r["measurement_id"]
        for block in card["parameters"].values()
        for r in block["rows"]
        if r["measurement_id"]
    } | {
        r["measurement_id"]
        for r in card["bioactivity"]["rows"]
        if r["measurement_id"]
    }
    assert len(expected) == 160 + 14
    html = (out / "_site" / "channels" / "piezo1" / "index.html").read_text(
        encoding="utf-8"
    )
    assert _details_ids(html) == expected


@requires_db
def test_db_piezo_banner_semantics_real_pages(tmp_path):
    """PIEZO1/PIEZO2 pages carry the §6.7 disclosure in BOTH locales —
    the library's EN boilerplate in the EN tree, the curated zh wording
    (zh-content.json, T-LOC) in the ZH tree — and render no affirmative
    verification status; a non-frozen page (TRPV4) carries no banner in
    either tree."""
    from maicdb.query import FROZEN_LAYER_DISCLOSURE

    zh_disclosure = json.loads(
        (SITE_DIR / "zh-content.json").read_text(encoding="utf-8")
    )["frozen_layer_disclosure"]
    out = tmp_path / "out"
    run_build(out)
    site = out / "_site"
    for slug in ("piezo1", "piezo2"):
        for prefix, expected in (("", FROZEN_LAYER_DISCLOSURE), ("zh/", zh_disclosure)):
            html = (site / prefix / "channels" / slug / "index.html").read_text(
                encoding="utf-8"
            )
            assert expected in html, (slug, prefix)
            assert not list(affirmative_status_hits(html)), (slug, prefix)
    trpv4 = (site / "channels" / "trpv4" / "index.html").read_text(encoding="utf-8")
    trpv4_zh = (site / "zh" / "channels" / "trpv4" / "index.html").read_text(
        encoding="utf-8"
    )
    assert FROZEN_LAYER_DISCLOSURE not in trpv4
    assert zh_disclosure not in trpv4_zh


@requires_db
def test_db_zero_row_blocks_visible_piezo2(tmp_path):
    """PIEZO2's zero-row threshold blocks stay on the page with their
    count (census: p50/t50/x50 = 0 rows; tau_inact = 15 — spec §4 and
    test_query pins)."""
    out = tmp_path / "out"
    run_build(out)
    html = (out / "_site" / "channels" / "piezo2" / "index.html").read_text(
        encoding="utf-8"
    )
    zero_note = _strings("en")["card_zero_rows_note"]
    # 12 of 16 blocks are zero-row on PIEZO2 (covered = 4 — see below)
    assert html.count(zero_note) == 12
    assert "(0)" in html and "(15)" in html


@requires_db
def test_db_bioactivity_block_presence(tmp_path):
    """ASIC's page carries the bioactivity block (24 rows — census) with a
    real compound; TREK-2 (0 rows) carries no block."""
    out = tmp_path / "out"
    run_build(out)
    site = out / "_site"
    asic = (site / "channels" / "asic" / "index.html").read_text(encoding="utf-8")
    assert _strings("en")["card_bioactivity_heading"] in asic
    assert "Hi1a" in asic
    trek2 = (site / "channels" / "trek-2" / "index.html").read_text(encoding="utf-8")
    assert _strings("en")["card_bioactivity_heading"] not in trek2


@requires_db
def test_db_browse_parameter_coverage_counts(tmp_path):
    """Browse coverage numbers are computed, not transcribed: PIEZO1
    11/16, PIEZO2 4/16, TRPV4 10/16 parameters with ≥1 row (re-derived
    from the built channel JSONs, census-backed)."""
    out = tmp_path / "out"
    run_build(out)
    index = json.loads((out / "_data" / "index.json").read_text(encoding="utf-8"))
    channels = {c["slug"]: c for f in index["families"] for c in f["channels"]}
    assert channels["piezo1"]["n_parameters_covered"] == 11
    assert channels["piezo2"]["n_parameters_covered"] == 4
    assert channels["trpv4"]["n_parameters_covered"] == 10
    # every channel: covered == parameters with a non-zero count
    for slug, entry in channels.items():
        derived = sum(1 for n in entry["parameters"].values() if n > 0)
        assert entry["n_parameters_covered"] == derived, slug

"""Curated Chinese content tests (M3-T-LOC, issue #43).

Three seams:

* **static** — ``site/zh-content.json`` completeness and quality gates:
  key sets aligned to the registry/census, every curated value
  genuinely Chinese-side (label ≠ EN label, §6.7 ≠ the EN boilerplate),
  and the newly written §6.7 wording carries every semantic component
  of the English original (the M1 pattern: semantics, not substrings —
  the zh wording is a fresh translation, never a copy).
* **fixture render** — the overlay is presentation-only: ZH pages show
  the curated zh values, EN pages show the payload's EN values
  untouched, and a payload key missing from zh-content falls through
  unchanged (no crash, no partial overwrite).
* **DB-backed** — the full build's ZH tree is fully populated (no EN
  fallback leaks on curated content: zh summaries on all 12 cards, zh
  labels on all 16 parameter pages + the index, 7 family descriptions
  on browse) and the zh §6.7 attaches to the PIEZO cards in the ZH
  tree only, the EN boilerplate in the EN tree only.

Real-data provenance: the 12 gene symbols, 7 family names and 16
parameter names are the artifact census (spec §4; the 7 families are
DEG_ENaC_ASIC, K2P, MSCL_MSCS, OSCA_TMEM63, PIEZO, TMC, TRP —
``SELECT DISTINCT family FROM channel``). The EN §6.7 boilerplate and
parameter labels come from the library (``FROZEN_LAYER_DISCLOSURE``,
``PARAMETERS`` — pinned in tests/test_query.py).
"""

import json
import re

from tests.test_site_build import (
    EXPECTED_SLUGS,
    REPO_ROOT,
    requires_db,
    run_build,
)

SITE_DIR = REPO_ROOT / "site"
ZH_CONTENT_PATH = SITE_DIR / "zh-content.json"

#: The census gene symbols in EXPECTED_SLUGS order (real casing —
#: ``MscL``/``MscS``, not slug-upper; cross-checked against the slugs
#: below). Census: spec §4, ``SELECT gene_symbol FROM channel``.
EXPECTED_GENES = [
    "ASIC",
    "MscL",
    "MscS",
    "OSCA",
    "PIEZO1",
    "PIEZO2",
    "TMC",
    "TRAAK",
    "TREK-1",
    "TREK-2",
    "TRESK",
    "TRPV4",
]

#: The census family names (spec §4; SQL in the module docstring).
FAMILIES = [
    "DEG_ENaC_ASIC",
    "K2P",
    "MSCL_MSCS",
    "OSCA_TMEM63",
    "PIEZO",
    "TMC",
    "TRP",
]

#: Semantic components the zh §6.7 wording must carry — one per clause
#: of the EN original (both gene symbols named; the frozen-layer
#: concept; the NOT-re-verified negation over evidence quotes; the
#: verification-percentages scope limited to the 10 non-frozen layers).
#: Component presence, never a substring of the EN text: the zh wording
#: is newly written (ticket F-3 — no Chinese source exists).
_ZH_DISCLOSURE_COMPONENTS = {
    "gene1": "PIEZO1",
    "gene2": "PIEZO2",
    "frozen-layer concept": "冻结层",
    "not-re-verified negation": "未",
    "evidence quotes": "证据引文",
    "10 non-frozen layers scope": "10",
    "only-scope qualifier": "仅",
}


def load_zh_content() -> dict:
    return json.loads(ZH_CONTENT_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Static: file completeness + quality gates
# --------------------------------------------------------------------------- #
def test_zh_content_covers_every_channel_family_parameter():
    """Key sets align to the census/registry: 12 channels (real-cased gene
    symbols), 7 families, 16 parameters (registry keys) — a missing key
    would silently fall through to EN in the ZH tree."""
    assert [g.lower() for g in EXPECTED_GENES] == EXPECTED_SLUGS  # self-check
    zh = load_zh_content()
    assert set(zh["channels"]) == set(EXPECTED_GENES)
    assert set(zh["families"]) == set(FAMILIES)
    from maicdb.query import PARAMETERS

    assert set(zh["parameters"]) == set(PARAMETERS)


def _has_cjk(value: str) -> bool:
    """值至少含一个 CJK 表意字符——"Chinese-side" 的机器可判定义
    （成分检测而非字符串比较：大小写变体、尾随空白的 EN 拷贝、
    非 CJK 第三语言值都判否）。"""
    return bool(re.search(r"[一-鿿]", value))


def test_cjk_detector_rejects_escape_forms():
    """Guard 自测向量（CODING_STANDARDS rule 4）：已知 escape 形式必须
    让检测器判否，真实 zh 值判是——上面的 Chinese-side 通过因此
    非空转。"""
    assert _has_cjk("P50 压力阈值")
    assert not _has_cjk("P50 pressure threshold")
    assert not _has_cjk("P50 pressure threshold ")  # 尾随空白的 EN 拷贝
    assert not _has_cjk("P50 PRESSURE THRESHOLD")  # 大小写变体
    assert not _has_cjk("") and not _has_cjk("  ")
    assert not _has_cjk("порог давления")  # 非 CJK 第三语言


def test_zh_content_values_are_chinese_side():
    """Every curated value of all four kinds carries CJK characters —
    an EN copy, an empty string, or a third-language value fails the
    component detector (which is not string-equality, so cosmetic
    escapes don't pass)."""
    zh = load_zh_content()
    for gene, entry in zh["channels"].items():
        assert _has_cjk(entry["summary"]), gene
    for name, entry in zh["parameters"].items():
        assert _has_cjk(entry["label"]), name
    for fam, entry in zh["families"].items():
        assert _has_cjk(entry["description"]), fam
    assert _has_cjk(zh["frozen_layer_disclosure"])


def test_zh_frozen_disclosure_carries_every_semantic_component():
    """The newly written zh §6.7 carries each semantic component of the
    EN boilerplate (see _ZH_DISCLOSURE_COMPONENTS) — semantics, not
    substrings: nothing here matches the EN text's wording."""
    zh = load_zh_content()
    wording = zh["frozen_layer_disclosure"]
    for label, component in _ZH_DISCLOSURE_COMPONENTS.items():
        assert component in wording, label


def test_zh_frozen_disclosure_is_not_an_affirmative_status():
    """M1 pattern: the zh wording as a whole is not an affirmative
    verification status — against the render-layer walker's status set
    (single source, Chinese forms included since T-LOC), never a
    hand-copied twin that can drift. Negation prose ("未经过再核验")
    passes by the whole-value boundary rule."""
    from tests.test_site_pages import _AFFIRMATIVE_STATUSES

    wording = load_zh_content()["frozen_layer_disclosure"].strip()
    assert wording not in _AFFIRMATIVE_STATUSES
    # the status set itself carries the zh forms (walker upgrade, below)
    assert {"已核验", "已验证"} <= _AFFIRMATIVE_STATUSES


# --------------------------------------------------------------------------- #
# Fixture render: the overlay is presentation-only
# --------------------------------------------------------------------------- #
def test_overlay_is_presentation_only_zh_gets_zh_en_keeps_payload(tmp_path):
    """The FROZEN1 fixture's ``p50``/``slope`` blocks are registry
    parameters, so the ZH tree renders their zh labels while the EN tree
    keeps the payload's synthetic EN labels; the FROZEN1 gene is NOT in
    zh-content's channel roster, so its NULL summary stays NULL (same
    not-recorded count both locales — no phantom content invented); the
    §6.7 wording is replaced globally (one zh disclosure, never the
    fixture's synthetic EN one, in the ZH tree)."""
    from tests.test_site_pages import (
        _SYNTH_DISCLOSURE,
        _strings,
        render_fixture,
    )

    zh = load_zh_content()
    out = render_fixture(tmp_path)
    zh_html = (out / "zh" / "channels" / "frozen1" / "index.html").read_text(
        encoding="utf-8"
    )
    en_html = (out / "channels" / "frozen1" / "index.html").read_text(
        encoding="utf-8"
    )

    # parameter labels: ZH overlay applied, EN payload untouched
    assert zh["parameters"]["p50"]["label"] in zh_html
    assert "synthetic P50 threshold" not in zh_html
    assert "synthetic P50 threshold" in en_html
    assert zh["parameters"]["p50"]["label"] not in en_html
    # PLAIN2's card carries the slope block (FROZEN1's does not)
    zh_plain2 = (out / "zh" / "channels" / "plain2" / "index.html").read_text(
        encoding="utf-8"
    )
    assert zh["parameters"]["slope"]["label"] in zh_plain2
    assert "synthetic slope" not in zh_plain2

    # summary: FROZEN1 not in the channel roster → NULL stays NULL
    # (identity not-recorded count identical in both locales)
    assert en_html.count("(not recorded)") == zh_html.count(
        _strings("zh")["card_not_recorded"]
    ) == 4

    # §6.7: the zh wording replaces the payload disclosure in the ZH
    # tree; the EN tree keeps whatever the payload carried
    assert zh["frozen_layer_disclosure"] in zh_html
    assert _SYNTH_DISCLOSURE not in zh_html
    assert _SYNTH_DISCLOSURE in en_html
    assert zh["frozen_layer_disclosure"] not in en_html

    # the parameter index + comparison page render zh labels in the ZH
    # tree too (same overlay, same source)
    for page in ("parameters/index.html", "parameters/p50/index.html"):
        zh_page = (out / "zh" / page).read_text(encoding="utf-8")
        assert zh["parameters"]["p50"]["label"] in zh_page, page
        en_page = (out / page).read_text(encoding="utf-8")
        assert "synthetic P50 threshold" in en_page, page


# --------------------------------------------------------------------------- #
# Full build against the published artifact (DB-backed)
# --------------------------------------------------------------------------- #
@requires_db
def test_db_zh_tree_fully_populated_no_en_fallback_leaks(tmp_path):
    """Ticket acceptance: the ZH tree carries the curated zh content for
    EVERY entity — all 12 channel summaries on their card pages, all 16
    parameter labels on the comparison pages and the index, all 7 family
    descriptions on browse — and the corresponding EN strings do not
    leak into the ZH pages (each curated value's EN counterpart is absent
    from that ZH page)."""
    from maicdb.query import PARAMETERS

    zh = load_zh_content()
    out = tmp_path / "out"
    run_build(out)
    site = out / "_site"

    # channel summaries: zh on the ZH card, EN tree keeps not-recorded
    for gene in EXPECTED_GENES:
        slug = gene.lower()
        zh_page = (site / "zh" / "channels" / slug / "index.html").read_text(
            encoding="utf-8"
        )
        assert zh["channels"][gene]["summary"] in zh_page, gene
        en_page = (site / "channels" / slug / "index.html").read_text(
            encoding="utf-8"
        )
        assert zh["channels"][gene]["summary"] not in en_page, gene
        # the EN tree's summary cell shows the not-recorded marker (the
        # artifact's summary column is NULL this load — loader-mapping)
        from tests.test_site_pages import _strings

        assert _strings("en")["card_not_recorded"] in en_page, gene

    # parameter labels: zh on every comparison page + the index
    zh_index = (site / "zh" / "parameters" / "index.html").read_text(
        encoding="utf-8"
    )
    for name in PARAMETERS:
        label = zh["parameters"][name]["label"]
        page = (site / "zh" / "parameters" / name / "index.html").read_text(
            encoding="utf-8"
        )
        assert label in page, name
        assert label in zh_index, name
        assert PARAMETERS[name].label not in page, name

    # family descriptions: zh-only content, 7/7 on the ZH browse page
    zh_browse = (site / "zh" / "channels" / "index.html").read_text(
        encoding="utf-8"
    )
    en_browse = (site / "channels" / "index.html").read_text(encoding="utf-8")
    for fam in FAMILIES:
        desc = zh["families"][fam]["description"]
        assert desc in zh_browse, fam
        assert desc not in en_browse, fam

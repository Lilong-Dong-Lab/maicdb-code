"""Parameter comparison pages (M3-T5, issue #40).

Two seams, mirroring test_site_pages.py:

* **fixture-driven (no DB)** — synthetic comparison payloads whose shape
  mirrors the library's ``export(format="json")`` output (the data layer
  writes that output verbatim, so the fixtures in test_site_pages.py
  match it field for field). Every value is synthetic; real-data pins
  live in the ``requires_db`` tests.
* **DB-backed** — the full CLI build against the published artifact:
  16 comparison pages + the index page × 2 locales, unit buckets
  disclosed and never merged, ratio medians omitted with the note,
  zero-count genes reported, counts pinned to the census SQL in this
  file's ``requires_db`` docstrings.
"""

from pathlib import Path

from tests.test_site_build import requires_db, run_build
from tests.test_site_pages import render_fixture


# --------------------------------------------------------------------------- #
# Fixture seam: pages render in both locale trees
# --------------------------------------------------------------------------- #
def test_parameter_pages_render_in_both_locales(tmp_path):
    """The parameter index page + one comparison page per registered
    parameter (here: the fixture's two) exist in BOTH locale trees —
    16 + 1 pages × 2 locales is the ticket acceptance, this is its
    fixture-scale shape."""
    out = render_fixture(tmp_path)
    for prefix in ("", "zh/"):
        index = out / prefix / "parameters" / "index.html"
        p50 = out / prefix / "parameters" / "p50" / "index.html"
        ratio = out / prefix / "parameters" / "ion_selectivity_ratio" / "index.html"
        assert index.is_file() and p50.is_file() and ratio.is_file()
        html = index.read_text(encoding="utf-8")
        assert html.startswith("<!doctype html>")


# --------------------------------------------------------------------------- #
# Fixture seam: the comparison page's disclosure semantics
# --------------------------------------------------------------------------- #
def test_comparison_page_disclosures_and_buckets(tmp_path):
    """Ticket acceptance semantics on the fixture payload: unit buckets
    disclosed and never merged (FROZEN1 renders TWO rows — mmHg and psi),
    zero-count genes listed (PLAIN2 count=0, marked), the threshold sign
    convention on p50 only, the ratio-median note + "—" median on the
    ratio parameter only, and the §6.7 banner from the payload's doc
    field. No Python ``None`` leaks into any cell."""
    import json

    out = render_fixture(tmp_path)
    p50 = (out / "parameters" / "p50" / "index.html").read_text(encoding="utf-8")
    strings = json.loads(
        (Path(__file__).parent.parent / "site" / "strings.en.json").read_text(
            encoding="utf-8"
        )
    )

    # unit-bucket disclosure + the two unmerged buckets as separate rows
    assert strings["param_unit_disclosure"] in p50
    assert p50.count("<tr") == 4  # header + 3 data rows
    assert ">mmHg<" in p50 and ">psi<" in p50
    # zero-count gene: row present, marked, all stats "—"
    assert 'class="zero-rows"' in p50
    zero_row = p50.split('class="zero-rows"', 1)[1].split("</tr>", 1)[0]
    assert ">PLAIN2<" in zero_row and zero_row.count("—") == 4
    # threshold sign convention rides the p50 page (localized dictionary)
    assert strings["card_sign_convention_label"] in p50
    # ratio note does NOT ride the p50 page
    assert strings["ratio_median_note"] not in p50
    # §6.7 banner from the doc-level payload field
    assert "synthetic frozen-layer disclosure for fixture pages" in p50
    # measurement-id deep links into the channel card (Q10, relative)
    assert 'href="../../channels/frozen1/#FROZEN1-EX-00001"' in p50
    assert "None" not in p50


def test_comparison_page_ratio_median_omitted_with_note(tmp_path):
    """Direction-blind ratio parameter (ticket): median renders "—" and
    the ratio-median note rides the page (once, localized); the note is
    absent from a non-ratio page (p50); the ZH edition carries the ZH
    dictionary's note."""
    import json

    out = render_fixture(tmp_path)
    site_dir = Path(__file__).parent.parent / "site"
    en = json.loads((site_dir / "strings.en.json").read_text(encoding="utf-8"))
    zh = json.loads((site_dir / "strings.zh.json").read_text(encoding="utf-8"))

    ratio = (out / "parameters" / "ion_selectivity_ratio" / "index.html").read_text(
        encoding="utf-8"
    )
    ratio_zh = (
        out / "zh" / "parameters" / "ion_selectivity_ratio" / "index.html"
    ).read_text(encoding="utf-8")
    # the counted row: min/max render, the cell BETWEEN them (the
    # median) is "—"; the unit cell is "—" too (unit-less parameter,
    # same marker as a NULL stored-unit bucket)
    import re

    counted = ratio.split(">PLAIN2<", 1)[1].split("</tr>", 1)[0]
    assert re.search(r">1\.2</td>\s*<td>—</td>\s*<td>40\.0<", counted)
    # note present exactly once per page, localized per tree
    assert ratio.count(en["ratio_median_note"]) == 1
    assert ratio_zh.count(zh["ratio_median_note"]) == 1
    assert en["ratio_median_note"] not in ratio_zh


def test_ratio_median_note_en_dictionary_matches_library():
    """The EN dictionary's ratio-median note is the library's wording
    verbatim — the comparison page and the CLI export disclose the same
    sentence (parity lock, the sign-convention pattern; the ZH wording
    is this ticket's in-ticket translation)."""
    import json

    from maicdb.query import RATIO_MEDIAN_NOTE

    en = json.loads(
        (Path(__file__).parent.parent / "site" / "strings.en.json").read_text(
            encoding="utf-8"
        )
    )
    assert en["ratio_median_note"] == RATIO_MEDIAN_NOTE


def test_parameter_index_page_lists_all_parameters(tmp_path):
    """The index page links one comparison page per parameter with its
    registry label and its derived row count (localized count label)."""
    import json

    out = render_fixture(tmp_path)
    html = (out / "parameters" / "index.html").read_text(encoding="utf-8")
    strings = json.loads(
        (Path(__file__).parent.parent / "site" / "strings.en.json").read_text(
            encoding="utf-8"
        )
    )
    assert f"<h1>{strings['parameters_heading']}</h1>" in html
    for name, label in (
        ("p50", "synthetic P50 threshold"),
        ("ion_selectivity_ratio", "synthetic ion selectivity ratio"),
    ):
        assert f'href="../parameters/{name}/"' in html
        assert label in html
    assert f">3 {strings['param_rows_label']}<" in html
    zh = (out / "zh" / "parameters" / "index.html").read_text(encoding="utf-8")
    assert f"<h1>{strings['parameters_heading']}</h1>" not in zh


# --------------------------------------------------------------------------- #
# DB seam: the rendered pages against the published artifact
# --------------------------------------------------------------------------- #
@requires_db
def test_db_pages_exist_in_both_locales(tmp_path):
    """Ticket acceptance: 16 comparison pages + the index page × 2
    locales (spec §5 site structure)."""
    from maicdb.query import PARAMETERS

    out = tmp_path / "out"
    run_build(out)
    site = out / "_site"
    for prefix in ("", "zh/"):
        assert (site / prefix / "parameters" / "index.html").is_file()
        for name in PARAMETERS:
            assert (site / prefix / "parameters" / name / "index.html").is_file(), (
                prefix,
                name,
            )


@requires_db
def test_db_p50_unit_buckets_never_merged(tmp_path):
    """Unit-bucket semantics on real data: MscL's P50 lives in TWO
    buckets — mmHg (17 rows) and psi (4 rows) — rendered as two table
    rows, never merged (issue #13; census SQL re-runnable read-only):

        SELECT c.gene_symbol, e.p50_unit, COUNT(*)
          FROM biophysics_experiment e JOIN channel c ON e.channel_id=c.id
         WHERE e.p50_value IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2;
        → (…), ('MscL', 'mmHg', 17), ('MscL', 'psi', 4), (…)

    PIEZO1's single mmHg bucket carries its 56 rows (spec §4 pin)."""
    out = tmp_path / "out"
    run_build(out)
    html = (out / "_site" / "parameters" / "p50" / "index.html").read_text(
        encoding="utf-8"
    )
    # MscL renders one row per unit bucket, each with its own count
    import re

    units = {}
    for seg in html.split(">MscL<")[1:]:
        row = seg.split("</tr>")[0]
        unit = "mmHg" if ">mmHg<" in row else ("psi" if ">psi<" in row else None)
        if unit:
            count = re.search(r"<summary>(\d+)</summary>", row)
            units[unit] = int(count.group(1)) if count else None
    assert units == {"mmHg": 17, "psi": 4}
    # the disclosure rides every comparison page (ticket acceptance)
    assert "Buckets are split by stored unit" in html
    # PIEZO1's 56-row mmHg bucket (spec §4)
    piezo1_row = html.split(">PIEZO1<")[1].split("</tr>")[0]
    assert ">mmHg<" in piezo1_row and "<summary>56</summary>" in piezo1_row


@requires_db
def test_db_zero_count_genes_reported_not_hidden(tmp_path):
    """Zero-count genes stay listed (rows are (gene, unit) BUCKETS, so a
    gene can legitimately hold several): osmotic_threshold has data on
    TRPV4 only — its 3 rows split across THREE stored-unit buckets
    ("%", "% HTS", "mOsm" — as-recorded spellings, never merged; census):

        SELECT c.gene_symbol, e.osmotic_threshold_unit, COUNT(*)
          FROM biophysics_experiment e JOIN channel c ON e.channel_id=c.id
         WHERE e.osmotic_threshold_value IS NOT NULL GROUP BY 1, 2;
        → ('TRPV4', '%', 1), ('TRPV4', '% HTS', 1), ('TRPV4', 'mOsm', 1)

    so the page carries 14 data rows (11 zero-gene rows + 3 TRPV4
    buckets), 11 of them marked zero; the 4-row unit-less
    ca_permeability (ASIC only, one bucket) lists 12 rows, 11 marked —
    AND is a direction-blind ratio, so its counted ASIC row shows the
    omitted-median marker (min/max pinned: ASIC's 4 ca_permeability
    values are 1.8…25.5 — ``SELECT MIN(ca_permeability), MAX(
    ca_permeability) FROM biophysics_experiment e JOIN channel c ON
    e.channel_id=c.id WHERE c.gene_symbol='ASIC' AND e.ca_permeability
    IS NOT NULL``)."""
    import json
    import re

    out = tmp_path / "out"
    run_build(out)
    site = out / "_site"
    for name, counted_gene, n_data_rows in (
        ("osmotic_threshold", "TRPV4", 14),
        ("ca_permeability", "ASIC", 12),
    ):
        for prefix in ("", "zh/"):
            html = (
                site / prefix / "parameters" / name / "index.html"
            ).read_text(encoding="utf-8")
            data_rows = re.findall(r"<tr([^>]*)>", html)[1:]  # skip thead row
            zero_marked = [r for r in data_rows if 'class="zero-rows"' in r]
            assert len(data_rows) == n_data_rows, (name, prefix)
            assert len(zero_marked) == 11, (name, prefix)

    osm = (site / "parameters" / "osmotic_threshold" / "index.html").read_text(
        encoding="utf-8"
    )
    for unit in ("%", "% HTS", "mOsm"):
        assert f"<td>{unit}</td>" in osm, unit

    # ratio page: the note rides the page; the counted ASIC row's cell
    # between min and max (the median) is "—" — 1.8 / — / 25.5
    en = json.loads(
        (Path(__file__).parent.parent / "site" / "strings.en.json").read_text(
            encoding="utf-8"
        )
    )
    ca_en = (site / "parameters" / "ca_permeability" / "index.html").read_text(
        encoding="utf-8"
    )
    asic_row = ca_en.split(">ASIC<")[1].split("</tr>")[0]
    assert re.search(r">1\.8</td>\s*<td>—</td>\s*<td>25\.5<", asic_row)
    assert 'class="zero-rows"' not in asic_row
    assert en["ratio_median_note"] in ca_en


# --------------------------------------------------------------------------- #
# DB seam: the data layer emits the comparison payloads
# --------------------------------------------------------------------------- #
@requires_db
def test_db_parameter_jsons_are_the_library_export_verbatim(tmp_path):
    """One JSON per registered parameter (16, registry names — the URL
    slug vocabulary: ``conductance`` NOT ``conductance_ps``), and each
    file is the library's ``export(format="json")`` output VERBATIM —
    byte-identical, so the site page and the CLI export can never drift
    (spec §1: the site is a thin consumer of the library)."""
    import json

    from maicdb.query import PARAMETERS, export, open_readonly

    out = tmp_path / "out"
    run_build(out)
    files = sorted((out / "_data" / "parameters").glob("*.json"))
    assert [f.stem for f in files] == sorted(PARAMETERS)

    engine = open_readonly("db/maicdb.sqlite")
    try:
        for name in PARAMETERS:
            exported = export(engine, name, format="json")
            built = (out / "_data" / "parameters" / f"{name}.json").read_text(
                encoding="utf-8"
            )
            assert built == exported, name
        # spot-check the payload shape the templates consume
        p50 = json.loads((out / "_data" / "parameters" / "p50.json").read_text())
        assert p50["parameter"] == "p50"
        assert "sign_convention" in p50  # threshold parameter
        assert "frozen_layer_disclosure" in p50  # lists PIEZO zero rows
    finally:
        engine.dispose()


@requires_db
def test_db_parameter_index_counts_pinned_to_census(tmp_path):
    """``index.json`` gains a ``parameters`` list (name, label, n_rows);
    ``n_rows`` = the comparison's per-bucket counts summed — the spec §4
    parameter census, re-derived read-only against db/maicdb.sqlite
    2026-11-02 (this ticket):

        SELECT COUNT(*) FROM biophysics_experiment
         WHERE conductance_ps IS NOT NULL;            -- 263
         WHERE p50_value IS NOT NULL;                 -- 152
         WHERE ion_selectivity_ratio IS NOT NULL;     --  66
         WHERE osmotic_threshold_value IS NOT NULL;   --   3

    Labels are the registry's (spec §4 vocabulary; ``label`` values
    asserted against PARAMETERS — no transcription).
    """
    import json

    from maicdb.query import PARAMETERS

    out = tmp_path / "out"
    run_build(out)
    index = json.loads((out / "_data" / "index.json").read_text(encoding="utf-8"))
    params = index["parameters"]
    assert [p["name"] for p in params] == list(PARAMETERS)
    by_name = {p["name"]: p for p in params}
    assert by_name["conductance"]["n_rows"] == 263
    assert by_name["p50"]["n_rows"] == 152
    assert by_name["ion_selectivity_ratio"]["n_rows"] == 66
    assert by_name["osmotic_threshold"]["n_rows"] == 3
    for name, spec in PARAMETERS.items():
        assert by_name[name]["label"] == spec.label, name

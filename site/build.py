"""Build the MAIC-DB site: data layer (M3-T2, issue #37) + HTML render
loop (M3-T3, issue #38).

Deterministic contract: same artifact + same code → byte-identical
outputs (``sort_keys`` + ``indent=2`` JSON, no timestamps, no clock in
the templates), mirroring the loader/export byte-stability rules. The
artifact is opened read-only and never touched (a DB-hash guard covers
the whole suite).

Build outputs (spec §6; default ``--out site``):
- ``site/_data/index.json``            family(7) → channel(12) → counts
                                        + home-scale ``totals`` + the
                                        parameter index (16, M3-T5)
- ``site/_data/channels/<slug>.json``  one card payload per channel (×12,
                                        bioactivity block where rows exist,
                                        MIMIC badge block where records
                                        exist — P7)
- ``site/_data/parameters/<name>.json`` one comparison payload per
                                        registered parameter (×16, M3-T5)
                                        — the library's ``export`` JSON
                                        written verbatim
- ``site/_data/analysis/<track>.json`` the four analysis payloads
                                        (audit / biophysics / atlas /
                                        trends, P7) — the P3/P4/P5/P6
                                        modules' outputs serialized
                                        verbatim by
                                        ``maicdb.analysis.site_payloads``
- ``site/_data/search-index.json``     flat search index (spec Q9)
- ``site/_site/``                      rendered pages, EN (unprefixed):
                                        home, browse, 12 channel cards,
                                        parameter index + 16 comparison
                                        pages (M3-T5)
- ``site/_site/zh/``                   the ZH edition of every page

The render loop consumes the data layer's JSON (a page never queries the
DB — spec §1 "thin consumer"), drives every UI string from
``strings.{en,zh}.json`` (spec Q3: UI copy only ever in the locale
dictionaries), and takes footer identifiers (license names, dataset DOI)
from ``CITATION.cff`` — the canonical citation home per ADR-0003.

NOT build outputs: ``site/strings.{en,zh}.json`` are repo source files
(UI copy dictionaries, parity-tested); ``site/zh-content.json`` is the
curated Chinese content layer (M3-T-LOC — channel summaries, parameter
labels, family descriptions, the zh §6.7 wording; a presentation-layer
overlay consumed by the ZH render loop only); ``site/templates/`` and
``site/assets/`` are repo sources the renderer reads.
"""

import argparse
import copy
import hashlib
import json
import posixpath
import re
import shutil
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from sqlalchemy import func, select

from maicdb.analysis import figures as analysis_figures
from maicdb.analysis.site_payloads import (
    analysis_payloads,
    channel_mimic_blocks,
)
from maicdb.models import Bioactivity, BiophysicsExperiment, Channel, Publication, UnmappedMeasurement
from maicdb.query import (
    PARAMETERS,
    bioactivity_card,
    channel_card,
    export,
    open_readonly,
)


def slugify(gene_symbol: str) -> str:
    """URL slug: lowercase gene symbol, hyphens kept (TREK-1 → trek-1)."""
    return gene_symbol.lower()


# --------------------------------------------------------------------------- #
# HTML render loop (M3-T3/T4): locale trees over the data layer's JSON
# --------------------------------------------------------------------------- #
#: Locale layout: locale → (tree directory under the site root, its
#: counterpart locale). EN is the unprefixed tree, ZH lives under ``zh/``;
#: iteration order is the render order.
_LOCALES: dict[str, tuple[str, str]] = {"en": ("", "zh"), "zh": ("zh", "en")}

#: License landing pages for the footer links (stable public URLs; the
#: license *names* themselves come from CITATION.cff with the data).
_LICENSE_URLS = {
    "MIT": "https://opensource.org/licenses/MIT",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
}

#: Downloads-page artifact manifest (M3-T6, issue #41): repo-relative
#: source paths, copied byte-identically into every locale tree so the
#: page's links resolve inside the tree each page is served from
#: (relative paths only, spec Q6). Sizes shown next to the links are
#: derived from these same files — never transcribed.
_DOWNLOAD_FILES = (
    "db/maicdb.sqlite",
    "db/maicdb.sql",
    "db/load-manifest.json",
    "CITATION.cff",
)


def _human_size(n_bytes: int) -> str:
    """Human-readable size in SI units (1000-based kB/MB — the ``ls --si``
    convention, NOT the 1024-based ``ls -h``); one decimal, whole bytes.
    E.g. 1171 → ``1.2 kB``, 3112960 → ``3.1 MB``."""
    size = float(n_bytes)
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1000:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    return f"{size:.1f} TB"


# --------------------------------------------------------------------------- #
# Curated Chinese content overlay (M3-T-LOC, issue #43)
# --------------------------------------------------------------------------- #
def _zh_label(zh: dict, name: str) -> str | None:
    """The zh label for a parameter from zh-content; None when the key is
    absent (the render then keeps the payload value) — the single source
    for the three overlay consumers."""
    return zh["parameters"].get(name, {}).get("label")


def _zh_card(card: dict, zh: dict) -> dict:
    """Card payload for the ZH render: deep-copied, then summary /
    parameter labels / the §6.7 disclosure substituted (spec §6 — curated
    Chinese is a presentation layer; the data artifact and the EN tree
    stay untouched; a key absent from zh-content keeps the payload value
    — no content is invented)."""
    card = copy.deepcopy(card)
    entry = zh["channels"].get(card["gene"]["gene_symbol"])
    if entry and entry.get("summary"):
        card["gene"]["summary"] = entry["summary"]
    for name, block in card["parameters"].items():
        label = _zh_label(zh, name)
        if label:
            block["label"] = label
    if "frozen_layer_disclosure" in card:
        card["frozen_layer_disclosure"] = zh["frozen_layer_disclosure"]
    bio = card.get("bioactivity")
    if bio and "frozen_layer_disclosure" in bio:
        bio["frozen_layer_disclosure"] = zh["frozen_layer_disclosure"]
    return card


def _zh_comparison(comparison: dict, entry: dict, zh: dict) -> tuple[dict, dict]:
    """Comparison payload + index entry for the ZH render: doc-level §6.7
    disclosure and parameter label substituted (rows carry no curated
    fields — evidence quotes are never translated, spec Q3)."""
    comparison = copy.deepcopy(comparison)
    entry = copy.deepcopy(entry)
    if "frozen_layer_disclosure" in comparison:
        comparison["frozen_layer_disclosure"] = zh["frozen_layer_disclosure"]
    label = _zh_label(zh, entry["name"])
    if label:
        entry["label"] = label
    return comparison, entry


def _zh_index_lists(
    families: list[dict], parameters: list[dict], zh: dict
) -> tuple[list[dict], list[dict]]:
    """ZH overlay for the browse / parameter-index lists: family groups
    gain their Chinese description (only when zh-content has the key —
    the EN tree's bytes are unchanged: the comment and the conditional
    block are laid out inline so the EN output is byte-identical to the
    pre-block template), parameter entries get label substitution."""
    families = copy.deepcopy(families)
    for fam in families:
        desc = zh["families"].get(fam["family"], {}).get("description")
        if desc:
            fam["description"] = desc
    parameters = copy.deepcopy(parameters)
    for param in parameters:
        label = _zh_label(zh, param["name"])
        if label:
            param["label"] = label
    return families, parameters


def _site_facts(repo_root: Path) -> dict:
    """Footer identifier block, read from the repo's canonical sources
    (ADR-0003; the site never hardcodes license names or DOIs):
    CITATION.cff for the license names and the dataset version DOI,
    the README's Releases section for the concept DOI (the CFF header
    delegates it there)."""
    cff = yaml.safe_load((repo_root / "CITATION.cff").read_text(encoding="utf-8"))
    preferred = cff["preferred-citation"]
    doi = str(preferred["doi"])
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    # README Releases carries it as a markdown link on the line under the
    # "**Concept DOI**" label; DOTALL + lazy match grabs the link text DOI.
    concept = re.search(r"Concept DOI.*?(10\.\d{4,}/zenodo\.\d+)", readme, re.DOTALL)
    if concept is None:
        raise ValueError("concept DOI not found in README Releases")
    concept_doi = concept.group(1)
    return {
        "license_code": cff["license"],
        "license_data": preferred["license"],
        "license_code_url": _LICENSE_URLS[cff["license"]],
        "license_data_url": _LICENSE_URLS[preferred["license"]],
        "dataset_version": f"v{preferred['version']}",
        "dataset_doi": doi,
        "dataset_doi_url": f"https://doi.org/{doi}",
        "concept_doi": concept_doi,
        "concept_doi_url": f"https://doi.org/{concept_doi}",
        "repo_url": cff["repository-code"],
    }


def _tree_prefix(page_dir: str, locale: str) -> str:
    """POSIX path of *page_dir* inside its locale tree (``zh`` prefix for
    the ZH edition, none for EN)."""
    return posixpath.normpath(posixpath.join(_LOCALES[locale][0] or ".", page_dir))


def _root_prefix(page_dir: str) -> str:
    """Relative prefix from a page up to its own tree root — ``.`` at the
    root, ``../..`` two levels down (relative assets only, spec Q6)."""
    depth = 0 if page_dir in ("", ".") else page_dir.strip("/").count("/") + 1
    return "." if depth == 0 else "/".join([".."] * depth)


def _alt_href(page_dir: str, locale: str) -> str:
    """Language-switcher target: the same page in the other locale tree
    (relative; the template appends the trailing slash)."""
    other = _LOCALES[locale][1]
    return posixpath.relpath(_tree_prefix(page_dir, other), _tree_prefix(page_dir, locale))


def _site_pages(
    index: dict, data_dir: Path, download_files: list[dict]
) -> list[tuple[str, str, dict]]:
    """The page list: (template, tree-relative directory, extra context).

    Singleton pages first (home, browse, parameter index, downloads),
    then one card page per channel in index order (family → gene_symbol
    — the data layer's deterministic order), then one comparison page
    per parameter in registry order. The card context carries the
    channel's index entry (browse counts for the qualitative rider) and
    the threshold-parameter names, so the template never re-derives that
    set from the CLI's rule; the comparison context carries the
    parameter's index entry, a gene→slug map (Q10 deep links into the
    channel cards, derived from the index — the page never queries the
    DB), and whether any row carries the ratio-median note (disclosed
    once per page, not per row); the downloads context carries the
    artifact manifest (path + SI size) built by ``render_site`` from the
    repo's real files.
    """
    pages: list[tuple[str, str, dict]] = [
        ("home.html", "", {}),
        ("browse.html", "channels", {}),
        ("parameters.html", "parameters", {}),
        ("downloads.html", "downloads", {"download_files": download_files}),
    ]
    # Analysis section (P7, spec §8): landing + one page per track +
    # methods. Track pages read their JSON payload here (thin consumer
    # — the page never queries the DB); the landing carries only the
    # headline numbers lifted from the payloads.
    audit = json.loads(
        (data_dir / "analysis" / "audit.json").read_text(encoding="utf-8")
    )
    atlas = json.loads(
        (data_dir / "analysis" / "atlas.json").read_text(encoding="utf-8")
    )
    biophysics = json.loads(
        (data_dir / "analysis" / "biophysics.json").read_text(encoding="utf-8")
    )
    trends = json.loads(
        (data_dir / "analysis" / "trends.json").read_text(encoding="utf-8")
    )
    headlines = _analysis_headlines(audit, atlas, biophysics, trends)
    # Breakdown label keys are built here (build-side machine strings)
    # so the audit template can look them up in ``strings`` without a
    # string literal (the Q3 scanner: template literals are violations).
    breakdowns_list = [
        (axis, f"breakdown_{axis}", rows)
        for axis, rows in sorted(audit["breakdowns"].items())
    ]
    pages.extend(
        [
            ("analysis.html", "analysis", {"headlines": headlines}),
            (
                "audit.html",
                "analysis/audit",
                {"audit": audit, "breakdowns_list": breakdowns_list},
            ),
            ("atlas.html", "analysis/atlas", {"atlas": atlas}),
            (
                "trends.html",
                "analysis/trends",
                {
                    "trends": trends,
                    **_trends_pivots(trends),
                },
            ),
            ("methods.html", "analysis/methods", {"headlines": headlines}),
        ]
    )
    gene_slugs = {
        entry["gene_symbol"]: entry["slug"]
        for fam in index["families"]
        for entry in fam["channels"]
    }
    for fam in index["families"]:
        for entry in fam["channels"]:
            slug = entry["slug"]
            card = json.loads(
                (data_dir / "channels" / f"{slug}.json").read_text(encoding="utf-8")
            )
            pages.append(
                (
                    "card.html",
                    f"channels/{slug}",
                    {"card": card, "entry": entry},
                )
            )
    for param in index["parameters"]:
        name = param["name"]
        comparison = json.loads(
            (data_dir / "parameters" / f"{name}.json").read_text(encoding="utf-8")
        )
        pages.append(
            (
                "parameter.html",
                f"parameters/{name}",
                {
                    "comparison": comparison,
                    "entry": param,
                    "gene_slugs": gene_slugs,
                },
            )
        )
    return pages


def _trends_pivots(trends: dict) -> dict:
    """The trends page's year-axis pivots, derived from the payload (the
    page reshapes; the module owns order and counting).

    * ``trends_family_grid``: (year, {family: k}) rows; a family absent
      from a year maps to None → the template renders a dash (absence,
      not zero).
    * ``trends_adoption_grid``: (parameter label, [k per year]) with
      None where that parameter had no row that year — the module's
      full cross-tab has every (year, parameter) combination, so None
      never occurs at data-v1.0, but the dash path exists for honesty.
    """
    families: list[str] = []
    for row in trends["pubs_per_year_by_family"]:
        if row["family"] not in families:
            families.append(row["family"])
    by_year: dict[int, dict[str, int]] = {}
    for row in trends["pubs_per_year_by_family"]:
        by_year.setdefault(row["year"], {})[row["family"]] = row["k"]
    family_grid = [
        (year, {fam: cells.get(fam) for fam in families})
        for year, cells in sorted(by_year.items())
    ]

    years = sorted({row["year"] for row in trends["parameter_adoption"]})
    per_param: dict[str, dict[int, int]] = {}
    for row in trends["parameter_adoption"]:
        per_param.setdefault(row["parameter"], {})[row["year"]] = row["k"]
    adoption_grid = [
        (label, [per_param.get(label, {}).get(y) for y in years])
        for label in per_param
    ]
    return {
        "trends_families": families,
        "trends_family_grid": family_grid,
        "trends_adoption_years": years,
        "trends_adoption_grid": adoption_grid,
    }


def _analysis_headlines(
    audit: dict, atlas: dict, biophysics: dict, trends: dict
) -> dict:
    """Landing-page headline numbers, lifted (not recomputed) from the
    payloads — the page renders payload facts only."""
    identifiable = [
        c for c in biophysics["threshold_meta"] if c.get("identifiable")
    ]
    return {
        "audit_data_tag": audit["data_freeze_tag"],
        "audit_n_records": audit["n_records"],
        "audit_mean_score": audit["mean_score"],
        "audit_fields": len(audit["field_totals"]),
        "atlas_cells": atlas["n_cells"],
        "atlas_compounds": atlas["n_compounds"],
        "atlas_channels": atlas["n_channels"],
        "atlas_delta_rows": len(atlas["delta_p50"]),
        "bio_cells": len(biophysics["threshold_meta"]),
        "bio_identifiable": len(identifiable),
        "trends_years": len(trends["pubs_per_year_total"]),
        "trends_first_year": trends["pubs_per_year_total"][0]["year"],
        "trends_last_year": trends["pubs_per_year_total"][-1]["year"],
    }


#: Which top-nav item each page template belongs to (M3 a11y pass): the
#: header link for that section carries ``aria-current="page"``. Card and
#: comparison pages belong to the Channels / Parameters sections
#: respectively — the same nav entry the reader came through. The five
#: analysis pages (P7) belong to Analysis.
_NAV_FLAGS_by_template = {
    "home.html": "home",
    "browse.html": "channels",
    "card.html": "channels",
    "parameters.html": "parameters",
    "parameter.html": "parameters",
    "downloads.html": "downloads",
    "analysis.html": "analysis",
    "audit.html": "analysis",
    "atlas.html": "analysis",
    "trends.html": "analysis",
    "methods.html": "analysis",
}


def _nav_flags(template: str) -> dict[str, bool]:
    """The five ``is_<section>`` flags the header consumes (template-scan
    safe: no string literals inside the template's conditionals)."""
    section = _NAV_FLAGS_by_template[template]
    return {
        "is_home": section == "home",
        "is_channels": section == "channels",
        "is_parameters": section == "parameters",
        "is_downloads": section == "downloads",
        "is_analysis": section == "analysis",
    }


def render_site(data_dir: Path, out_dir: Path, site_dir: Path, repo_root: Path) -> list[Path]:
    """Render every page kind into both locale trees under *out_dir*.

    Reads ``<data_dir>/index.json``, the per-channel card JSONs and the
    per-parameter comparison JSONs (the data layer — a page never
    queries the DB), copies ``site/assets/`` into each tree (relative
    references only), and writes ``<out_dir>/[zh/]<page>/index.html``.
    StrictUndefined makes a missing dictionary key a build error, so an
    untranslated string cannot ship silently.

    M3-T6 additions, both per locale tree so every page stays inside
    its own tree (relative links only, spec Q6): the downloads
    artifacts (``_DOWNLOAD_FILES``, byte-identical copies from the
    repo, linked from the downloads page with their SI sizes) and a
    copy of the data layer's ``search-index.json`` at the tree root
    (the deployed root is the rendered tree, so the client-side search
    could not fetch it from ``_data/``).
    """
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    download_files = [
        {"path": rel, "size": _human_size((repo_root / rel).stat().st_size)}
        for rel in _DOWNLOAD_FILES
    ]
    # The analysis payloads (P7) — loaded for the figure render; the
    # page contexts load their own copies in ``_site_pages`` (both from
    # the same data layer, so they cannot drift).
    payloads = {
        name: json.loads(
            (data_dir / "analysis" / f"{name}.json").read_text(encoding="utf-8")
        )
        for name in ("audit", "biophysics", "atlas", "trends")
    }
    pages = _site_pages(index, data_dir, download_files)
    env = Environment(
        loader=FileSystemLoader(site_dir / "templates"),
        autoescape=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    # Display formatting (P7): number formatting lives here, not in the
    # templates — a format literal inside a template is exactly the
    # machine-string the Q3 scanner exists to catch. None never reaches
    # these (every call site guards with strings.table_empty first).
    env.globals["fmt"] = {
        "pct": lambda x: f"{x * 100:.0f}",
        "f3": lambda x: f"{x:.3f}",
    }
    strings = {
        code: json.loads((site_dir / f"strings.{code}.json").read_text(encoding="utf-8"))
        for code in _LOCALES
    }
    site = _site_facts(repo_root)
    # Curated Chinese content (M3-T-LOC): a presentation-layer overlay —
    # only the ZH tree renders it; the data layer and the EN tree are
    # untouched (spec §6).
    zh_content = json.loads(
        (site_dir / "zh-content.json").read_text(encoding="utf-8")
    )
    # Cache-busting asset URLs (content hash, deterministic — the
    # byte-stable contract holds): a stylesheet or script edit changes
    # the query string, so a browser holding the previous copy must
    # refetch instead of silently rendering the old design.
    asset_version = hashlib.sha256(
        (site_dir / "assets" / "style.css").read_bytes()
        + (site_dir / "assets" / "site.js").read_bytes()
    ).hexdigest()[:8]

    written: list[Path] = []
    for locale, (tree_dir, alt_locale) in _LOCALES.items():
        tree = out_dir / tree_dir
        shutil.copytree(site_dir / "assets", tree / "assets", dirs_exist_ok=True)
        # Figures (P7, spec §8): rendered from the payloads into each
        # tree's analysis/figures/ — same bytes both trees (deterministic
        # render, metadata stripped; test_analysis_figures locks it).
        written.extend(
            analysis_figures.render_all(payloads, tree / "analysis" / "figures")
        )
        for rel in _DOWNLOAD_FILES:
            dest = tree / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo_root / rel, dest)
            written.append(dest)
        search_copy = tree / "search-index.json"
        shutil.copyfile(data_dir / "search-index.json", search_copy)
        written.append(search_copy)
        locale_families = index["families"]
        locale_parameters = index["parameters"]
        if locale == "zh":
            locale_families, locale_parameters = _zh_index_lists(
                index["families"], index["parameters"], zh_content
            )
        for template, page_dir, extra in pages:
            if locale == "zh":
                if "card" in extra:
                    extra = {**extra, "card": _zh_card(extra["card"], zh_content)}
                elif "comparison" in extra:
                    comparison, entry = _zh_comparison(
                        extra["comparison"], extra["entry"], zh_content
                    )
                    extra = {**extra, "comparison": comparison, "entry": entry}
            page = tree / page_dir / "index.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                env.get_template(template).render(
                    strings=strings[locale],
                    show_sizes=(5, 10, 25),
                    **_nav_flags(template),
                    asset_css=f"{_root_prefix(page_dir)}/assets/style.css?v={asset_version}",
                    asset_js=f"{_root_prefix(page_dir)}/assets/site.js?v={asset_version}",
                    lang=locale,
                    alt_lang=alt_locale,
                    root=_root_prefix(page_dir),
                    alt=_alt_href(page_dir, locale),
                    site=site,
                    totals=index["totals"],
                    families=locale_families,
                    parameters=locale_parameters,
                    **extra,
                )
                + "\n",
                encoding="utf-8",
            )
            written.append(page)
    print(f"site render: {len(pages)} page(s) x {len(_LOCALES)} locales -> {out_dir}")
    return written


def _dump(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def build(db_path: Path, out_dir: Path) -> list[Path]:
    """Emit the data layer; returns the written paths in build order."""
    engine = open_readonly(db_path)
    data_dir = out_dir / "_data"
    channels_dir = data_dir / "channels"
    channels_dir.mkdir(parents=True, exist_ok=True)

    with engine.connect() as conn:
        genes = list(
            conn.scalars(select(Channel.gene_symbol).order_by(Channel.gene_symbol))
        )
        # gene_symbol → channel id, the MIMIC badge join key (P7). The
        # analysis module keys blocks by channel id; cards are keyed by
        # gene symbol.
        gene_ids = dict(
            conn.execute(select(Channel.gene_symbol, Channel.id)).all()
        )
        # Home-scale census (SQL, never transcribed — ticket #38): one
        # measurement = one row across the three fact tables; the
        # publications count is the normalized citation table itself.
        # The unmapped share rides along for the downloads disclosure
        # (M3-T6): 16 archived rows mapped to no registered parameter
        # block, disclosed by count with no page of their own (Q11).
        fact_counts = {
            model: conn.scalar(select(func.count()).select_from(model))
            for model in (BiophysicsExperiment, Bioactivity, UnmappedMeasurement)
        }
        totals = {
            "n_measurements": sum(fact_counts.values()),
            "n_unmapped": fact_counts[UnmappedMeasurement],
            "n_channels": len(genes),
            "n_families": conn.scalar(
                select(func.count()).select_from(
                    select(Channel.family).distinct().subquery()
                )
            ),
            "n_publications": conn.scalar(
                select(func.count()).select_from(Publication)
            ),
        }
        # Qualitative as-reported-only rows: every registered parameter
        # column NULL (the caliber spec §4 found — 12 rows repo-wide,
        # belonging to no parameter block). The predicate is derived from
        # the PARAMETERS registry, never hand-copied, so a registry change
        # can't silently strand a column.
        qualitative_value_cols = [
            getattr(BiophysicsExperiment, spec.column) for spec in PARAMETERS.values()
        ]
        qualitative_by_gene = dict(
            conn.execute(
                select(Channel.gene_symbol, func.count())
                .join_from(
                    Channel,
                    BiophysicsExperiment,
                    BiophysicsExperiment.channel_id == Channel.id,
                )
                .where(*(c.is_(None) for c in qualitative_value_cols))
                .group_by(Channel.gene_symbol)
            ).all()
        )

    written: list[Path] = []
    families: dict[str, dict] = {}
    search_entries: list[dict] = []
    # MIMIC badge blocks, computed once (P2's scoring engine behind P7's
    # per-channel field-level aggregation — site_payloads docstring).
    mimic_blocks = channel_mimic_blocks(engine)
    for gene in genes:
        card = channel_card(engine, gene)
        # Bioactivity rides the same payload where data exists (spec Q11 —
        # 9 channels; a zero-row gene carries no block, unlike the 16
        # parameter blocks, which are never hidden). PIEZO1's block keeps
        # the §6.7 disclosure the library attaches — the wording follows
        # the evidence itself.
        bioactivity = bioactivity_card(engine, gene)
        if bioactivity["n_rows"]:
            card["bioactivity"] = bioactivity
        # MIMIC badge (spec §8): every channel with ≥1 experiment gets
        # the block; channels with none render no badge (no lie).
        mimic = mimic_blocks.get(gene_ids.get(gene))
        if mimic is not None:
            card["mimic"] = mimic
        identity = card["gene"]
        path = channels_dir / f"{slugify(gene)}.json"
        _dump(path, card)
        written.append(path)

        slug = slugify(gene)
        # Aggregate the browse index (family → channels → counts) from the
        # same payloads — computed, never hand-copied (HANDOFF §3 rule 4).
        fam = identity["family"]
        families.setdefault(fam, {"family": fam, "channels": []})
        families[fam]["channels"].append(
            {
                "slug": slug,
                "gene_symbol": gene,
                # Rows carrying at least one normalized parameter value —
                # NOT the raw table-row census: 12 rows repo-wide are
                # qualitative as-reported values (LINEAR / OUTWARD_
                # RECTIFYING / ranges) with every parameter column NULL
                # and therefore no parameter block (spec §4 census note).
                "n_parameterized_rows": sum(
                    b["n_rows"] for b in card["parameters"].values()
                ),
                "n_bioactivity_rows": bioactivity["n_rows"],
                "n_qualitative_rows": qualitative_by_gene.get(gene, 0),
                "n_parameters_covered": sum(
                    1 for b in card["parameters"].values() if b["n_rows"] > 0
                ),
                "parameters": {
                    name: block["n_rows"]
                    for name, block in card["parameters"].items()
                },
            }
        )

        # Search entries (spec Q9): the JSON column arrives already
        # deserialized (SQLAlchemy sa.JSON); UniProt is a slash-separated
        # set (NULL → empty list).
        uniprots = (identity["uniprot_accession"] or "").split("/")
        search_entries.append(
            {
                "type": "channel",
                "slug": slug,
                "label": gene,
                "family": fam,
                "aliases": identity["gene_aliases"] or [],
                "uniprots": [u for u in uniprots if u],
                "url": f"/channels/{slug}/",
            }
        )

    for fam in sorted(families):
        search_entries.append(
            {"type": "family", "label": fam, "url": f"/channels/#{fam}"}
        )
    for name, spec in PARAMETERS.items():
        search_entries.append(
            {
                "type": "parameter",
                "name": name,
                "label": spec.label,
                "url": f"/parameters/{name}/",
            }
        )

    # Parameter comparisons (M3-T5): the library's ``export`` JSON output
    # written VERBATIM, one file per registered parameter — the page and
    # the CLI export cannot drift (the same bytes feed both). The index
    # entry's ``n_rows`` sums the comparison's per-bucket counts,
    # computed — never transcribed (HANDOFF §3 rule 4).
    params_dir = data_dir / "parameters"
    params_dir.mkdir(parents=True, exist_ok=True)
    parameter_index = []
    for name, spec in PARAMETERS.items():
        doc = export(engine, name, format="json")
        path = params_dir / f"{name}.json"
        path.write_text(doc, encoding="utf-8")
        written.append(path)
        parameter_index.append(
            {
                "name": name,
                "label": spec.label,
                "n_rows": sum(r["count"] for r in json.loads(doc)["rows"]),
            }
        )

    # Analysis payloads (P7, spec §8): the four track modules' outputs
    # serialized verbatim — pages read these JSON files, never the DB.
    payloads = analysis_payloads(engine)
    analysis_dir = data_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        path = analysis_dir / f"{name}.json"
        _dump(path, payload)
        written.append(path)

    index = {
        "families": [families[fam] for fam in sorted(families)],
        "parameters": parameter_index,
        "totals": totals,
    }
    index_path = data_dir / "index.json"
    _dump(index_path, index)
    written.append(index_path)

    search_path = data_dir / "search-index.json"
    _dump(search_path, {"entries": search_entries})
    written.append(search_path)
    print(f"site data layer: {len(genes)} channel cards -> {channels_dir}")

    written.extend(
        render_site(
            data_dir=data_dir,
            out_dir=out_dir / "_site",
            site_dir=Path(__file__).resolve().parent,
            repo_root=Path(__file__).resolve().parent.parent,
        )
    )
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/maicdb.sqlite")
    parser.add_argument("--out", default="site")
    args = parser.parse_args(argv)
    build(Path(args.db), Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

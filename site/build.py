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
                                        bioactivity block where rows exist)
- ``site/_data/parameters/<name>.json`` one comparison payload per
                                        registered parameter (×16, M3-T5)
                                        — the library's ``export`` JSON
                                        written verbatim
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
import json
import posixpath
import re
import shutil
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from sqlalchemy import func, select

from maicdb.models import Bioactivity, BiophysicsExperiment, Channel, Publication, UnmappedMeasurement
from maicdb.query import (
    PARAMETERS,
    THRESHOLD_PARAMETERS,
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
                    {
                        "card": card,
                        "entry": entry,
                        "threshold_names": THRESHOLD_PARAMETERS,
                    },
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
                    "has_ratio_note": any("note" in r for r in comparison["rows"]),
                },
            )
        )
    return pages


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
    pages = _site_pages(index, data_dir, download_files)
    env = Environment(
        loader=FileSystemLoader(site_dir / "templates"),
        autoescape=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
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

    written: list[Path] = []
    for locale, (tree_dir, alt_locale) in _LOCALES.items():
        tree = out_dir / tree_dir
        shutil.copytree(site_dir / "assets", tree / "assets", dirs_exist_ok=True)
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

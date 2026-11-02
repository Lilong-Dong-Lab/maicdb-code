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
(UI copy dictionaries, parity-tested); ``site/templates/`` and
``site/assets/`` are repo sources the renderer reads.
"""

import argparse
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


def _site_pages(index: dict, data_dir: Path) -> list[tuple[str, str, dict]]:
    """The page list: (template, tree-relative directory, extra context).

    Singleton pages first (home, browse, parameter index), then one card
    page per channel in index order (family → gene_symbol — the data
    layer's deterministic order), then one comparison page per parameter
    in registry order. The card context carries the channel's index entry
    (browse counts for the qualitative rider) and the threshold-parameter
    names, so the template never re-derives that set from the CLI's rule;
    the comparison context carries the parameter's index entry, a
    gene→slug map (Q10 deep links into the channel cards, derived from
    the index — the page never queries the DB), and whether any row
    carries the ratio-median note (disclosed once per page, not per row).
    """
    pages: list[tuple[str, str, dict]] = [
        ("home.html", "", {}),
        ("browse.html", "channels", {}),
        ("parameters.html", "parameters", {}),
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
    """
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    pages = _site_pages(index, data_dir)
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

    written: list[Path] = []
    for locale, (tree_dir, alt_locale) in _LOCALES.items():
        tree = out_dir / tree_dir
        shutil.copytree(site_dir / "assets", tree / "assets", dirs_exist_ok=True)
        for template, page_dir, extra in pages:
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
                    families=index["families"],
                    parameters=index["parameters"],
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
        totals = {
            "n_measurements": sum(
                conn.scalar(select(func.count()).select_from(model))
                for model in (BiophysicsExperiment, Bioactivity, UnmappedMeasurement)
            ),
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

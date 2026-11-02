"""Build the MAIC-DB site: data layer (M3-T2, issue #37) + HTML render
loop (M3-T3, issue #38).

Deterministic contract: same artifact + same code → byte-identical
outputs (``sort_keys`` + ``indent=2`` JSON, no timestamps, no clock in
the templates), mirroring the loader/export byte-stability rules. The
artifact is opened read-only and never touched (a DB-hash guard covers
the whole suite).

Build outputs (spec §6; default ``--out site``):
- ``site/_data/index.json``            family(7) → channel(12) → counts
                                        + home-scale ``totals``
- ``site/_data/channels/<slug>.json``  one card payload per channel (×12)
- ``site/_data/search-index.json``     flat search index (spec Q9)
- ``site/_site/``                      rendered pages, EN (unprefixed)
- ``site/_site/zh/``                   rendered pages, ZH (``/zh/`` prefix)

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
import shutil
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from sqlalchemy import func, select

from maicdb.models import Bioactivity, BiophysicsExperiment, Channel, Publication, UnmappedMeasurement
from maicdb.query import PARAMETERS, channel_card, open_readonly


def slugify(gene_symbol: str) -> str:
    """URL slug: lowercase gene symbol, hyphens kept (TREK-1 → trek-1)."""
    return gene_symbol.lower()


# --------------------------------------------------------------------------- #
# HTML render loop (M3-T3): locale trees over the data layer's JSON
# --------------------------------------------------------------------------- #
#: Rendered page kinds: (template name, tree-relative directory). T4–T7
#: append their page kinds here (browse, cards, parameters, downloads).
_PAGES: tuple[tuple[str, str], ...] = (("home.html", ""),)

#: Locale order; EN is the unprefixed tree, ZH lives under ``zh/``.
_LOCALES = ("en", "zh")

#: License landing pages for the footer links (stable public URLs; the
#: license *names* themselves come from CITATION.cff with the data).
_LICENSE_URLS = {
    "MIT": "https://opensource.org/licenses/MIT",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
}


def _site_facts(cff_path: Path) -> dict:
    """Footer identifier block, read from CITATION.cff (ADR-0003: the
    canonical, editable home of the citation strings — the site never
    hardcodes license names or DOIs)."""
    cff = yaml.safe_load(cff_path.read_text(encoding="utf-8"))
    preferred = cff["preferred-citation"]
    doi = str(preferred["doi"])
    return {
        "license_code": cff["license"],
        "license_data": preferred["license"],
        "license_code_url": _LICENSE_URLS[cff["license"]],
        "license_data_url": _LICENSE_URLS[preferred["license"]],
        "dataset_doi": doi,
        "dataset_doi_url": f"https://doi.org/{doi}",
        "repo_url": cff["repository-code"],
    }


def _tree_prefix(page_dir: str, locale: str) -> str:
    """POSIX path of *page_dir* inside its locale tree (``zh`` prefix for
    the ZH edition, none for EN)."""
    return posixpath.normpath(posixpath.join("zh" if locale == "zh" else ".", page_dir))


def _root_prefix(page_dir: str) -> str:
    """Relative prefix from a page up to its own tree root — ``.`` at the
    root, ``../..`` two levels down (relative assets only, spec Q6)."""
    depth = 0 if page_dir in ("", ".") else page_dir.strip("/").count("/") + 1
    return "." if depth == 0 else "/".join([".."] * depth)


def _alt_href(page_dir: str, locale: str) -> str:
    """Language-switcher target: the same page in the other locale tree
    (relative; the template appends the trailing slash)."""
    other = "zh" if locale == "en" else "en"
    return posixpath.relpath(_tree_prefix(page_dir, other), _tree_prefix(page_dir, locale))


def render_site(data_dir: Path, out_dir: Path, site_dir: Path, cff_path: Path) -> list[Path]:
    """Render every page kind into both locale trees under *out_dir*.

    Reads ``<data_dir>/index.json`` (the T2 data layer — a page never
    queries the DB), copies ``site/assets/`` into each tree (relative
    references only), and writes ``<out_dir>/[zh/]<page>/index.html``.
    StrictUndefined makes a missing dictionary key a build error, so an
    untranslated string cannot ship silently.
    """
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
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
    site = _site_facts(cff_path)

    written: list[Path] = []
    for locale in _LOCALES:
        tree = out_dir / (locale if locale == "zh" else "")
        shutil.copytree(site_dir / "assets", tree / "assets", dirs_exist_ok=True)
        for template, page_dir in _PAGES:
            page = tree / page_dir / "index.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(
                env.get_template(template).render(
                    strings=strings[locale],
                    lang=locale,
                    alt_lang="zh" if locale == "en" else "en",
                    root=_root_prefix(page_dir),
                    alt=_alt_href(page_dir, locale),
                    site=site,
                    totals=index["totals"],
                    families=index["families"],
                )
                + "\n",
                encoding="utf-8",
            )
            written.append(page)
    print(f"site render: {len(_PAGES)} page(s) x {len(_LOCALES)} locales -> {out_dir}")
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

    written: list[Path] = []
    families: dict[str, dict] = {}
    search_entries: list[dict] = []
    for gene in genes:
        card = channel_card(engine, gene)
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

    index = {
        "families": [families[fam] for fam in sorted(families)],
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
            cff_path=Path(__file__).resolve().parent.parent / "CITATION.cff",
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

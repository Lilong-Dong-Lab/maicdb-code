"""Build the MAIC-DB site data layer (M3-T2, issue #37).

Deterministic contract: same artifact + same code → byte-identical
outputs (``sort_keys`` + ``indent=2`` JSON, no timestamps), mirroring
the loader/export byte-stability rules. The artifact is opened read-only
and never touched (a DB-hash guard covers the whole suite).

Build outputs, under ``<out>/_data/`` (spec §6; default ``--out site``
puts data at ``site/_data/`` — rendered HTML later joins at
``site/_site/`` and ``site/_site/zh/``, which is T3):
- ``_data/index.json``            family(7) → channel(12) → parameter counts
- ``_data/channels/<slug>.json``  one card payload per channel (×12)
- ``_data/search-index.json``     flat search index (spec Q9)

NOT build outputs: ``site/strings.{en,zh}.json`` are repo source files
(UI copy dictionaries, parity-tested in tests/test_site_build.py) that
T3's renderer consumes — the data layer here is locale-neutral.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select

from maicdb.models import Channel
from maicdb.query import PARAMETERS, channel_card, open_readonly


def slugify(gene_symbol: str) -> str:
    """URL slug: lowercase gene symbol, hyphens kept (TREK-1 → trek-1)."""
    return gene_symbol.lower()


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
    }
    index_path = data_dir / "index.json"
    _dump(index_path, index)
    written.append(index_path)

    search_path = data_dir / "search-index.json"
    _dump(search_path, {"entries": search_entries})
    written.append(search_path)
    print(f"site data layer: {len(genes)} channel cards -> {channels_dir}")
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

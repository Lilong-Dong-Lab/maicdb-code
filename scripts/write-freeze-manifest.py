#!/usr/bin/env python
"""Write db/freeze-manifest.json (ADR-0007) from a vault freeze tag.

Two phases, because the manifest mixes vault facts with loader facts:

1. ``build_freeze_manifest`` pins the vault-side facts — identity (tag,
   HEAD, freeze date, schema version), the closed-set sha256 inventory of
   the frozen surface, and the per-layer row counts.
2. A loader dry run against that preliminary manifest fills the
   conservation ``counts`` block (routing counts are loader facts, not
   vault facts), and the final manifest is written and validated by a
   round-trip through ``load_freeze_manifest``.

Usage (at every freeze retarget, before the retarget's code commit):

    uv run python scripts/write-freeze-manifest.py \
        --vault /tmp/vault-tag-v12 \
        --tag data-v1.2 --freeze-date 2026-11-08 --schema-version 0.2.0

The vault must be a clean checkout descending from the tag's commit (the
builder verifies; see the freeze recipe in the vault's progress record for
the worktree dance). Commit the written manifest with the retarget PR.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from maicdb.loader import load_vault
from maicdb.vault import (COUNT_KEYS, FREEZE_MANIFEST_PATH,
                          build_freeze_manifest, load_freeze_manifest,
                          resolve_vault)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate the code-side freeze manifest (ADR-0007)")
    ap.add_argument("--vault", type=Path, default=None,
                    help="vault checkout at the freeze tag "
                         "(default: $MAICDB_VAULT, else the sibling checkout)")
    ap.add_argument("--tag", required=True,
                    help="the vault freeze tag to pin (e.g. data-v1.2)")
    ap.add_argument("--freeze-date", required=True,
                    help="declared freeze epoch, ISO date (vault-inexpressible)")
    ap.add_argument("--schema-version", required=True,
                    help="formal-schema version the code implements")
    ap.add_argument("--out", type=Path, default=None,
                    help=f"output path (default: {FREEZE_MANIFEST_PATH})")
    args = ap.parse_args()

    vault = resolve_vault(args.vault)
    out = args.out or FREEZE_MANIFEST_PATH

    fm = build_freeze_manifest(vault, args.tag, freeze_date=args.freeze_date,
                               schema_version=args.schema_version)

    with tempfile.TemporaryDirectory(prefix="freeze-manifest-") as td:
        prelim = Path(td) / "preliminary-freeze-manifest.json"
        prelim.write_text(json.dumps(fm, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
        load_manifest = load_vault(vault, Path(td) / "dry.sqlite",
                                   require_tag=args.tag,
                                   freeze_manifest_path=prelim)
    fm["counts"] = {k: load_manifest["counts"][k] for k in COUNT_KEYS}

    out.write_text(json.dumps(fm, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    check, sha = load_freeze_manifest(out)  # round-trip: fail-closed
    if check != fm:
        raise RuntimeError(f"{out}: round-trip mismatch after write")
    print(f"wrote {out} (sha256 {sha[:12]}…): tag {fm['freeze_tag']} @ "
          f"{fm['vault_head'][:12]}, {fm['rows_total']} rows, "
          f"{len(fm['files'])} pinned files")


if __name__ == "__main__":
    main()

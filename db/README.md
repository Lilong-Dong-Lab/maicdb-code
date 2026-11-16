# MAIC-DB v1.2 published database artifacts

The formal-schema database loaded from the vault's frozen curation corpus.

> [!note] id semantics (ADR-0006)
> `maicdb_id` accessions (`MAIC:BX:*`) are **per-release row keys** — cite
> them with the release tag, and use the vault `measurement_id` for
> cross-release identity. Assignment freezes at the first public release
> (`docs/adr/0006-maicdb-id-stability.md`); each freeze retarget may
> renumber until then.

| File | Content | Regenerate |
|---|---|---|
| `maicdb.sqlite` | The database (schema v0.2, 10 tables) | `maicdb-load --vault <vault> -o db/maicdb.sqlite --manifest db/load-manifest.json` |
| `maicdb.sql` | Byte-stable SQL dump (the determinism contract — two loads of the same vault state are byte-identical) | Same command (written alongside) |
| `load-manifest.json` | Row counts, disclosures, freeze point, `freeze_manifest_sha256` chain link | Written by the loader |
| `freeze-manifest.json` | The pinned input contract (ADR-0007): freeze identity + closed-set sha256 inventory of the vault's frozen surface + conservation counts | `PYTHONPATH=src uv run python scripts/write-freeze-manifest.py --tag data-v1.2 --freeze-date 2026-11-08 --schema-version 0.2.0` (run BEFORE the load — the loader hash-checks it) |

## Provenance

- **Input**: vault repo `Lilong-Dong-Lab/Project_DataBase_MAICDB` @ tag **`data-v1.2`**
  (a zero-row retarget of `data-v1.1`: identical 1125-row corpus — the vault
  delta is additive piezo1/piezo2 corroboration artifacts only)
  (see the manifest's `vault_head` / `data_freeze_tag` — the dump embeds the
  exact vault commit it was loaded from; determinism is per-vault-state).
- **Freeze enforcement**: the loader verifies the tag is an ancestor of the
  vault HEAD, then hash-checks every frozen-surface file against
  `db/freeze-manifest.json` (git blob bytes — stable across LFS smudge
  states; missing/extra/changed files are load-time errors). Docs churn on
  the rolling repo stays legal (the frozen surface is `data/` +
  literature-mining configs only). The census cross-anchors the chain
  (load manifest's `freeze_manifest_sha256` vs the freeze manifest's
  actual bytes).
- **Schema**: v0.2 (evidence chain on both fact tables, six gap-adjudicated
  migration columns, `unmapped_measurement` archive, `db_meta`; see
  `docs/loader-mapping.md` for every mapping decision and its approval trail).

## Retarget recipe (order is load-bearing)

1. Vault PR merges, then the vault freeze tag is cut (`data-vN.N`).
2. Regenerate the freeze manifest against the new tag (command above —
   `--freeze-date` is the declared freeze epoch, `--schema-version` the
   formal-schema version).
3. Commit the manifest, then regenerate the artifact trio with the load
   command above; `tests/census_snapshot.json` regenerates with
   `scripts/derive-census-clean.sh`.
4. Loader constants live in the freeze manifest — a retarget stops
   editing `src/maicdb/loader.py`.

## Contents (from the load manifest)

1125 curated measurement rows = **960 biophysics** (incl. 131 gap-adjudicated
migrations, zero silent NULLs; 105 pre-authorized unit conversions with
as-reported originals preserved) + **137 bioactivity** + **28 unmapped**
(adjudicated-kept archive; v1.0 carried 1100 = 948 + 136 + 16). Dimensions:
**216 publications** (210 from the extraction corpus — 10 shared across layers
— + 6 structure-only citations),
**12 channels** (osca = one family row, four accessions in
`external_reference`), **12 structures** (piezo1; 10/12 linked to their
primary citations), **86 compounds** (85 role-resolved + the unroled
silica-nanoparticle family), **133 variants**, **6 external references**.

Every fact row carries the full evidence chain (`measurement_id`,
`evidence_quote`, `evidence_location`, `confidence`, `extractor_note` — the
F-004 disclosure tokens verbatim, `condition_key`, `n`). License:
**CC-BY-4.0** (recorded in `db_meta`).

> [!note] Date semantics
> `db_meta.release_date` records the **data-freeze epoch** (2026-11-08 for
> data-v1.1 and data-v1.2; 2026-09-01 for data-v1.0), the constant baked into the byte-stable
> dump — the dump is deterministic by construction, so it pins the freeze
> date, not the publication day.

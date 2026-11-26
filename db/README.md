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
| `maicdb.sqlite` | The database (schema v0.8, 26 tables + compatibility view) | `maicdb-load --vault <vault> -o db/maicdb.sqlite --manifest db/load-manifest.json` |
| `maicdb.sql` | Byte-stable SQL dump (the determinism contract — two loads of the same vault state are byte-identical) | Same command (written alongside) |
| `load-manifest.json` | Row counts, disclosures, vault HEAD | Written by the loader |

## Provenance

- **Input**: vault repo `Lilong-Dong-Lab/Project_DataBase_MAICDB` @ tag **`data-v1.2`**
  (a zero-row retarget of `data-v1.1`: identical 1125-row corpus — the vault
  delta is additive piezo1/piezo2 corroboration artifacts only)
  (see the manifest's `vault_head` / `data_freeze_tag` — the dump embeds the
  exact vault commit it was loaded from; determinism is per-vault-state).
- **Freeze enforcement**: the loader verifies the tag is an ancestor of the
  vault HEAD and that `data/` + configs are unchanged since the tag
  (docs churn on the rolling repo is legal).
- **Schema**: v0.8 (v0.3 normalized Evidence authority; v0.4 Construct
  experiment/variant linkage; v0.5 structure-function residue and
  variant-location mapping; v0.6 subject-specific semantic external-reference
  matrix; v0.7 native Data-layer vocabulary and inventory; v0.8
  compound-channel provenance; see `docs/loader-mapping.md` and ADR-0007 for
  mapping decisions).

## Contents (from the load manifest)

1125 curated measurement rows = **960 biophysics** (incl. 131 gap-adjudicated
migrations, zero silent NULLs; 105 pre-authorized unit conversions with
as-reported originals preserved) + **137 bioactivity** + **28 unmapped**
(adjudicated-kept archive; v1.0 carried 1100 = 948 + 136 + 16). Dimensions:
**216 publications** (210 from the extraction corpus — 10 shared across layers
— + 6 structure-only citations),
**12 channels** (osca = one family row, four accessions in
`external_reference`), **12 structures** (piezo1; 10/12 linked to their
external references), **12 structures** (piezo1; 10/12 linked to their
primary citations; each PDB ID also carries a semantic structure reference),
**86 compounds** (85 role-resolved + the unroled
silica-nanoparticle family), **135 variants** (133 extraction-derived plus
2 title-derived), **27 semantic external references**.

Every fact row carries the full evidence chain (`measurement_id`,
`evidence_quote`, `evidence_location`, `confidence`, `extractor_note` — the
F-004 disclosure tokens verbatim, `condition_key`, `n`). License:
**CC-BY-4.0** (recorded in `db_meta`).

## Evidence authority (tickets #97/#98)

The artifact contains **1129 `evidence_item` records** and **1129
`evidence_subject` links**: 1,125 fact-family Evidence objects (one for every
biophysics experiment (960), bioactivity row (137), and unmapped measurement
(28), plus four title-derived structure Evidence objects. Evidence items are
reusable, stable `MAIC:EV:*` objects carrying a
claim, source, publication, quote, location, controlled evidence
type/confidence, curator note, lightweight review state, and review timestamp.
Queries, site payloads, CLI, and exports resolve this normalized model first;
legacy evidence columns remain readable only as a compatibility bridge.

## Structure-function mapping (ticket #100)

The artifact records four explicit construction mutations (`A1988V`,
`E756del`, and `R2456H`) in their deposited PIEZO1 PDB structures. Each is
represented by a UniProt-numbered `structure_residue`, a
`structure_variant_location`, and a normalized `EvidenceItem` whose quote is
the deposited PDB title. PDB residue coordinates are intentionally NULL in
this release: the frozen vault does not carry residue-level SIFTS mappings,
and the loader does not infer coordinates from sequence identity.

## Native Data-layer provenance (ticket #102)

Schema v0.7 adds a controlled `data_layer` vocabulary
(`source_reported`, `curated`, `computed`) and a shared
`data_layer_inventory` table. The inventory is the extensible contract for
value-bearing scientific outputs: each row carries its public surface, field,
layer, and an auditable migration or derivation rule. The marker is additive
provenance; it never overwrites or reinterprets the underlying values.

> [!note] Date semantics
> `db_meta.release_date` records the **data-freeze epoch** (2026-11-08 for
> data-v1.1 and data-v1.2; 2026-09-01 for data-v1.0), the constant baked into the byte-stable
> dump — the dump is deterministic by construction, so it pins the freeze
> date, not the publication day.

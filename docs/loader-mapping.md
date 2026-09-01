# MAIC-DB Loader Mapping Spec v0.1 — data-v1.0 Corpus → Formal Schema

Status: spec (this round); implementation in the next round(s). Decisions marked
**[DECIDED 2026-09-01]** were approved by the lab lead; the rest are spec
recommendations standing for review.

## 1. Purpose, inputs, outputs

**Purpose**: map the vault's frozen curation corpus onto the formal 8-table ORM
schema (this repo, `src/maicdb/`), porting the staging loader's proven
transforms (`tools/db-load/build_staging_db.py` in the vault) and discharging
the §9 loader duties (MIMIC enforcement, `external_reference` integrity,
`ortholog_group` normalization).

**Input contract** — vault repo `Lilong-Dong-Lab/Project_DataBase_MAICDB` @
tag **`data-v1.0`** (merge commit `a12c5c0`, 2026-09-01):

| Source | Content |
|---|---|
| `data/<ch>/extraction/extracted_measurements.csv` ×12 | 1100 rows (piezo1 174, piezo2 29, trpv4 115, asic 137, mscs 104, mscl 89, osca 94, tmc 172, traak 40, trek-1 52, trek-2 42, tresk 52) |
| `tools/literature-mining/configs/<ch>.yaml` ×12 | channel identity (gene_symbol, uniprot, family, aliases) |
| `data/piezo1/structures/piezo1_pdb_structures.csv` (+ raw `data/piezo1/raw/piezo1_pdb_entries_detail/*.json`) | 12 PDB structures + primary citations (structure data exists ONLY for piezo1) |
| `data/piezo1/compounds/`, `data/piezo1/cross_references/` | compound descriptors, channel xrefs (piezo1 only) |
| `data/db/staging.sqlite` / `staging.sql` | staging preview (7 tables) — reference for transform parity, NOT a load source (CSVs are the source of truth; builder = single truth) |
| `data/extraction_schema.md` | column semantics + enums authority (doc side) |

**Output**: `maicdb.sqlite` (formal schema, loaded) + load manifest
(row counts, exclusions, enum coverage, conversion tally).

## 2. Schema v0.2 extensions **[DECIDED 2026-09-01 — user approval]**

The v0.1 schema (designed 2026-07, before the curation phase) has no home for
the evidence chain that F-004/F-005 built on. Two extensions were approved:

1. **Evidence columns (dedicated)** on `biophysics_experiment` AND `bioactivity`:
   `measurement_id TEXT UNIQUE` (vault natural key), `evidence_quote TEXT`,
   `evidence_location TEXT`, `confidence TEXT`, `extractor_note TEXT`
   (F-004 tokens live here verbatim), `condition_key TEXT`, `n INTEGER`
   (replicate count as reported — records/patches/cells; NOT `n_cells`).
2. **`unmapped_measurement` archive table** (the 16 adjudicated schema_gap
   rows): `measurement_id UNIQUE`, `channel_id FK`, `parameter_kind`,
   `value`+`unit`, `adjudication`, the evidence columns, `publication_id FK`.

Also recommended now (§9 future item, cheap, FAIR): **`db_meta`** table —
`schema_version`, `license=CC-BY-4.0`, `release_date`, `mimic_standard_version`,
`data_freeze_tag=data-v1.0`.

## 3. Table-by-table mapping

### 3.1 `publication` — 205 rows (DOI dedup; 8 papers shared across layers)
| Extraction | Column | Transform |
|---|---|---|
| `doi` | `doi` | dedup key; NULL-less (all rows carry DOI) |
| `pmid` | `pmid` | int; string digits cast |
| `first_author` | `authors` | `[first_author]` only (vault holds no full author list per paper — **disclosed partial**) |
| `publication_year` | `year` | int |
| `journal` | `journal` | verbatim |
| — | `title` | NULL this load (no per-paper title column in extraction; piezo1 raw PDB citations hold titles for 12 structure papers only) |
| — | `citation_text` | NULL |

### 3.2 `channel` — 12 rows (one per layer)
| Source | Column | Transform |
|---|---|---|
| configs `protein.gene_symbol` | `gene_symbol` | verbatim (PIEZO1, TRPV4, …) |
| `protein.aliases` | `gene_aliases` | JSON list |
| `protein.uniprot` | `uniprot_accession` | UNIQUE — one per layer; bacterial layers (mscl Q8XCZ8 / mscs …) as-is |
| configs family | `family` | PIEZO / TRP / K2P / OSCA_TMEM63 / MSCL_MSCS / TMC / DEG_ENaC_ASIC — enum covers all 12 layers |
| — | `organism`, `organism_taxid` | canonical per gene: human (9606) for mammalian layers, E. coli for mscl/mscs — **from configs, to be added as explicit `organism`/`taxid` fields** (configs lack them today; loader round adds) |
| `protein.aliases[0..]` | `ortholog_group` | normalize to UPPERCASE gene symbol (§9 duty: case-fold so `Piezo1`/`PIEZO1` cannot split groups) |
| — | `activation_mechanism` | Force-from-Lipids for PIEZO/MscL/MscS/OSCA/TRAAK-TREK per master summary; Force-from-Filament for TMC; mixed/undetermined for others — from a config table, cited to the master summary |
| — | `ncbi_gene_id`, `sequence_length`, `go_terms`, `summary` | optional enrichment; NULL this load unless trivially sourced from configs |
| — | `source_db` = `UNIPROT`, `collected_date` = freeze date | provenance stub |

### 3.3 `structure` — 12 rows (piezo1 only)
CSV columns map 1:1 (`Title→title`, `Resolution_A→resolution_a`,
`Method→method`, `Organism→organism`, `Num_Chains→num_chains`,
`Has_Inhibitor→has_inhibitor`); `residues_covered`/`coverage_pct`/
`deposition_date`/`DOI` are empty in the CSV → NULL (raw PDB details hold
deposition/DOI/citation for future enrichment — same source the schema tests
now cite). `structure_source=PDB`. `channel_id` → the PIEZO1 channel row.
`publication_id` → publication upserted from the raw PDB primary citation
(12 citations, dedup'd — 8ZU3+8YFC share Shan 2025).

### 3.4 `biophysics_experiment` — 948 rows (staging-routing parity)
Routing: extraction `db_target_table='biophysics_experiment'` + gap-adjudicated
migrations (130 rows) — reuse the staging loader's `db_target_table` routing
table verbatim.

| Extraction | Column | Transform |
|---|---|---|
| `db_target_column` | card column routing | `conductance_ps`, `p50_value`+`p50_unit`, `t50_value`+`t50_unit`, `x50_value`+`x50_unit`, `tau_act_ms`, `tau_inact_ms`, `tau_deact_ms`, `reversal_potential_mv`, `slope`, `delta_p50_value`+`delta_p50_unit`, `pressure_threshold`→(schema-gap archive) |
| `value`/`error`/`value_relation` | card values | **105 unit conversions ported** (nS→pS ×1000, s→ms ×1000, min→ms ×60000, µs→ms ×0.001, mM→nM ×1e6) — hook: `REPORTED UNIT IS <UNIT>` in `extractor_note`; as-printed originals have NO formal column → **spec gap**: recommend `value_as_reported`+`unit_as_reported` on the card in v0.2 (decision pending) |
| `unit_db` | `*_unit` enums | mmHg→`PressureUnit.MMHG`, kPa→`KPA`, mN/m→`TensionUnit.MN_M`, dyn/cm→`DYN_CM`, µm→`IndentationUnit.UM` — loader FAILS on unmapped unit (strict) |
| `db_parameter_set` | `parameter_set` | verbatim (P50, T50, CONDUCTANCE_ONLY, …) |
| `stimulus_type` | `stimulus_type` | enum strict; extraction vocabulary {PRESSURE_CLAMP, SUCTION, OSMOTIC, …, OTHER} — loader asserts full coverage, maps strays to OTHER only with manifest entry |
| `stimulus_detail` | `stimulus_waveform` + `probe_geometry` | keep verbatim in `experiment_label` this load; structured parse deferred (spec: no lossy parse in v1.0) |
| `recording_mode` | `recording_mode` | enum strict {CELL_ATTACHED, INSIDE_OUT, OUTSIDE_OUT, WHOLE_CELL, OTHER} |
| `expression_system`/`cell_type`/`temperature_c`/`ph`/`bath_solution`/`pipette_solution`/`holding_potential_mv` | same-name MIMIC cols | verbatim |
| `modulator_name`(non-pharmacology rows) | `compound_id` | link to compound when the row is a ligand-context experiment (e.g. AA-activated Erev); NULL otherwise |
| `n` | `n` **[v0.2]** | verbatim replicate count |
| `measurement_id`…`extractor_note` | evidence columns **[v0.2]** | verbatim — F-004 tokens preserved; `measurement_id` UNIQUE |
| `condition_key` | `condition_key` **[v0.2]** | verbatim (row-local uniqueness key) |

### 3.5 `compound` — 85 rows (modulator_name dedup, staging parity)
`modulator_role`→`compound_type` normalization (agonist→ACTIVATOR,
blocker/antagonist→INHIBITOR_BLOCKER, potentiator→POTENTIATOR, conflict→
highest-frequency with manifest entry). piezo1 `compounds/` descriptors
(inchikey, MW, …) join where available; other layers name-only.
**`inchikey` UNIQUE risk**: piezo1 compounds carry keys; name-dedup'd
modulators from other layers mostly do not — insert NULL inchikey rows is safe
(SQLite UNIQUE tolerates NULLs), manifest discloses descriptor coverage.

### 3.6 `bioactivity` — 136 rows
Pharmacology kinds (`ec50/ic50/kd/ki/kb/pec50`, 136 rows): `activity_type`
= kind.upper() enum; `value`→`activity_value`; `unit`→`activity_units`;
`value_relation`→`relation`; `modulator_name`→compound link;
`assay_description` = `parameter_label` + `stimulus_detail` concatenation
(spec recommendation); `assay_format`/`cell_line`/`target_species` NULL this
load (parse deferred). Evidence columns as §2. `uq_bioactivity_dedup`
respected (staging had 0 collisions).

### 3.7 `variant` — 125 rows (hgvs_short dedup from 197 variant-carrying rows)
`variant_hgvs_short`→`mutation_short` (dedup key); `position`/`ref_aa`/`alt_aa`
parsed when short form is a clean substitution, else NULL; clinical columns
(clinvar/omim/dbsnp) NULL this load (vault holds none);
`organism` = channel organism. Variant↔experiment linkage: extraction rows
carry the variant context on the measurement row — the FK from experiment to
variant does NOT exist in v0.1; **spec gap**: recommend `variant_id` FK on
`biophysics_experiment` in v0.2 (decision pending) or encode in
`experiment_label`.

### 3.8 `external_reference`
piezo1 `cross_references/` (uniprot↔pdb mapping etc.) → CHANNEL xrefs.
**§9 duty**: loader validates each `(entity_type, entity_id)` target exists at
insert; orphans impossible by construction (insert-after-parent ordering).

### 3.9 `unmapped_measurement` **[v0.2, DECIDED]** — 16 rows
Adjudicated schema_gap rows (e.g. TRAAK-00026 thermal_threshold 31 °C,
pressure_threshold kind): `parameter_kind`/`value`/`unit`/`adjudication`
(from staging `schema_gap` table routing) + evidence columns.

## 4. §9 enforcement checklist (loader duties, v1.0)

- [ ] MIMIC: fail/warn rows missing stimulus velocity, probe geometry,
      recording mode, experimental context — v1.0 stance: **warn + manifest
      column** (corpus rows predate MIMIC; hard-fail would reject most rows);
      hard-fail activates for post-MIMIC sources.
- [ ] `external_reference` target validation at insert.
- [ ] `ortholog_group` uppercase normalization.
- [ ] Unit-enum strict mapping (unmapped unit = load error).
- [ ] Conservation: 1100 = biophysics 948 + bioactivity 136 + unmapped 16;
      publication 205; channel 12; structure 12; compound 85; variant 125
      (parity asserts against staging counts).
- [ ] Determinism: byte-stable dump (SQLite version pinned note; port the
      vault's `data/db/README.md` float-rendering caveat).
- [ ] Frozen-layer semantics: piezo1/piezo2 load as-is; their un-re-verified
      quote status recorded in `db_meta` (data_freeze manifest), not per-row.

## 5. Round plan

- **A2 (next)**: schema v0.2 (evidence columns, `unmapped_measurement`,
  `db_meta`; pending: `value_as_reported` pair, `variant_id` FK) + loader
  implementation + tests (enum coverage, conservation, determinism,
  negative-fixtures).
- **A3**: run the load against `data-v1.0`, publish `maicdb.sqlite` + manifest,
  cross-repo digest.

## 6. Open items (spec-level, need decision in A2)

1. `value_as_reported`/`unit_as_reported` columns (as-printed originals of
   the 105 converted rows) — recommended YES (staging carried them).
2. `variant_id` FK on `biophysics_experiment` — recommended YES.
3. `authors=[first_author]` partial disclosure vs NULL — recommended partial
   with manifest disclosure.
4. `stimulus_detail` structured parse — deferred beyond v1.0 (verbatim only).

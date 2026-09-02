# MAIC-DB Loader Mapping Spec v0.2 — data-v1.0 Corpus → Formal Schema

Status: schema v0.2 IMPLEMENTED (A2a, models.py @ 0.2.0); loader pending
(A2b). Decisions marked **[DECIDED 2026-09-01]** were approved by the lab
lead (§2 + §6 — all decided; nothing open). Rev v0.2 (same day): the independent
gate review of v0.1 (1 MAJOR + 7 MINOR + 4 NIT, all fixed — see PR #2
conversation); every corpus-facing figure below was recomputed by the
reviewer against the vault @ `data-v1.0` unless marked otherwise.

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
| `data/piezo1/compounds/`, `data/piezo1/cross_references/` | compound descriptors (21/21 with InChIKey), channel xrefs (piezo1 only) |
| `data/db/staging.sqlite` / `staging.sql` | staging preview (7 tables) — reference for transform parity, NOT a load source (CSVs are the source of truth; builder = single truth) |
| `data/extraction_schema.md` | column semantics + enums authority (doc side) |

**Output**: `maicdb.sqlite` (formal schema, loaded) + load manifest
(row counts, exclusions, enum coverage, conversion tally).

## 2. Schema v0.2 extensions **[DECIDED 2026-09-01 — user approval]**

The v0.1 schema (designed 2026-07, before the curation phase) has no home for
the evidence chain that F-004/F-005 built on, and no columns for 118 of the
130 gap-adjudicated migration values. Three extensions approved:

1. **Evidence columns (dedicated)** on `biophysics_experiment` AND `bioactivity`:
   `measurement_id TEXT UNIQUE` (vault natural key), `evidence_quote TEXT`,
   `evidence_location TEXT`, `confidence TEXT`, `extractor_note TEXT`
   (F-004 tokens live here verbatim), `condition_key TEXT`,
   `n TEXT` (replicate count as reported — records/patches/cells; TEXT, not
   INTEGER: 32 corpus rows carry ranges or text, e.g. "3-10", "≥75
   cells/data-point"; staging deliberately types n as TEXT. Deviates from the
   approved preview's INTEGER sketch for implementability).
2. **Six migration columns** on `biophysics_experiment`, staging-parity types:
   `ion_selectivity_ratio` (66 rows), `threshold_fold_shift` (23),
   `macroscopic_rise_time` (13), `thermal_threshold` (9), `ca_permeability`
   (4), `osmotic_threshold` (3). Together with the existing `delta_p50_*`
   (12), all 130 gap-adjudicated migration values land in typed columns;
   routing stays 948/136/16. Column types mirror the staging loader
   (one provenance exception: staging stages the 4 `ca_permeability` values
   inside `ion_selectivity_ratio` with `gap_kind='ca_permeability'` — e.g.
   ASIC-00051 = 18.5; formal v0.2 gives the kind a dedicated column); types
   finalized in schema v0.2 (`models.py` — realized as ion_selectivity_ratio +
   ratio_direction, threshold_fold_shift_value+unit, macroscopic_rise_time_ms,
   thermal_threshold_c, ca_permeability, osmotic_threshold_value+unit).
3. **`unmapped_measurement` archive table** (the 16 adjudicated-kept rows):
   `measurement_id UNIQUE`, `channel_id FK`, `parameter_kind`, `value`+`unit`,
   `adjudication`, the evidence columns, `publication_id FK`.

Also **`db_meta`** table (implemented): `schema_version`, `license`,
`release_date`, `mimic_standard_version`, `data_freeze_tag=data-v1.0` —
license value per §6.5 (CC-BY-4.0, decided).

## 3. Table-by-table mapping

### 3.1 `publication` — 205 rows (DOI dedup; 10 papers shared across layers, 2 of them by 3 layers)
| Extraction | Column | Transform |
|---|---|---|
| `doi` | `doi` | dedup key; all rows carry DOI |
| `pmid` | `pmid` | int; string digits cast |
| `first_author` | `authors` | `[first_author]` from the extraction corpus (full author arrays exist only in the vault's Zotero export — enrichment is §6.4) |
| `publication_year` | `year` | int |
| `journal` | `journal` | verbatim |
| `title` | `title` | **loaded** — the CSVs carry a per-DOI `title` (211 doi,title pairs; all 205 DOIs have ≥1 non-empty). Rule: first non-empty per DOI, manifest discloses the variant-count (~6) |
| — | `citation_text` | NULL |

### 3.2 `channel` — 12 rows (one per layer)
| Source | Column | Transform |
|---|---|---|
| configs `protein.gene_symbol` | `gene_symbol` | verbatim (PIEZO1, TRPV4, …) |
| `protein.aliases` | `gene_aliases` | JSON list |
| `protein.uniprot` | `uniprot_accession` | one accession per layer (mscl P0A742, mscs P0C0S1, …) — **except osca**: config carries slash-joined `O94886/Q5T3F8/Q9P1W3/Q9XEA1` (multi-gene family layer) → one family row per §6.2 (decided): accessions to external_reference, uniprot_accession NULL for that row |
| configs family | `family` | PIEZO / TRP / K2P / OSCA_TMEM63 / MSCL_MSCS / TMC / DEG_ENaC_ASIC — enum covers all 12 layers (verified) |
| — | `organism`, `organism_taxid` | canonical per gene: human (9606) for mammalian layers, E. coli for mscl/mscs — to be added as explicit config fields in A2 |
| `protein.aliases[0..]` | `ortholog_group` | normalize to UPPERCASE gene symbol (§9 duty: case-fold so `Piezo1`/`PIEZO1` cannot split groups) |
| — | `activation_mechanism` | Force-from-Lipids for PIEZO/MscL/MscS/OSCA/TRAAK-TREK per master summary; Force-from-Filament for TMC; mixed/undetermined for others — from a config table, cited to the master summary |
| — | `ncbi_gene_id`, `sequence_length`, `go_terms`, `summary` | optional enrichment; NULL this load unless trivially sourced |
| — | `source_db` = `UNIPROT`, `collected_date` = freeze date | provenance stub |

### 3.3 `structure` — 12 rows (piezo1 only)
CSV columns map 1:1 (`Title→title`, `Resolution_A→resolution_a`,
`Method→method`, `Organism→organism`, `Num_Chains→num_chains`,
`Has_Inhibitor→has_inhibitor`); `residues_covered`/`coverage_pct`/
`deposition_date`/`DOI` are empty in the CSV → NULL (raw PDB details hold
deposition/DOI/citation for future enrichment — same source the schema tests
cite). `structure_source=PDB`. `channel_id` → the PIEZO1 channel row.
`publication_id` → publication upserted from the raw PDB primary citation
(12 citations, dedup'd — 8ZU3+8YFC share Shan 2025).

### 3.4 `biophysics_experiment` — 948 rows (staging-routing parity)
Routing: extraction `db_target_table='biophysics_experiment'` (818 rows) +
gap-adjudicated migrations (130 rows; only via the staging routing table —
gap_kind breakdown: ion_selectivity_ratio 66, threshold_fold_shift 23,
macroscopic_rise_time 13, delta_p50 12, thermal_threshold 9, ca_permeability
4, osmotic_threshold 3).

| Extraction | Column | Transform |
|---|---|---|
| `db_target_column` | card column routing | `conductance_ps`, `p50_value`+`p50_unit`, `t50_value`+`t50_unit`, `x50_value`+`x50_unit`, `tau_act_ms`, `tau_inact_ms`, `tau_deact_ms`, `reversal_potential_mv`, `slope`, `iv_relation` (8 corpus rows; formal column + `IVRelation` enum exist), `delta_p50_value`+`delta_p50_unit` |
| gap migrations | §2.2 six columns | all 118 non-delta_p50 migration values land in typed columns (nothing NULLed silently) |
| `value`/`error`/`value_relation` | card values | **105 unit conversions ported** (nS→pS ×1000, s→ms ×1000, min→ms ×60000, µs→ms ×0.001, mM→nM ×1e6) — hook: `REPORTED UNIT IS <UNIT>` in `extractor_note`; as-printed originals land in `value_as_reported`/`unit_as_reported` (§6.1, implemented) |
| `unit_db` | `*_unit` enums | mmHg→`PressureUnit.MMHG`, kPa→`KPA`, mN/m→`TensionUnit.MN_M`, dyn/cm→`DYN_CM`, µm→`IndentationUnit.UM` — loader FAILS on unmapped unit (strict). One row (TRPV4-EX-00072) routes bare `p50_value` (db_target_column lacks the pair); its unit comes from `unit_db` (mmHg → MMHG), manifest entry |
| `db_parameter_set` | `parameter_set` | verbatim (P50, T50, CONDUCTANCE_ONLY, …) |
| `stimulus_type` | `stimulus_type` | enum strict; corpus vocabulary {PRESSURE_CLAMP, SUCTION, HYPOTONIC, …, OTHER} — loader asserts full coverage, maps strays to OTHER only with manifest entry |
| `stimulus_detail` | `stimulus_waveform` + `probe_geometry` | keep verbatim in `experiment_label` this load; structured parse deferred |
| `recording_mode` | `recording_mode` | enum strict — corpus uses **all 9** enum values (CELL_ATTACHED, INSIDE_OUT, OUTSIDE_OUT, WHOLE_CELL, PERFORATED_PATCH, PLANAR_PATCH, RECONSTITUTED_PROTEOLIPOSOME, TEVC, OTHER); coverage assert must expect 9 |
| `expression_system`/`cell_type`/`temperature_c`/`ph`/`bath_solution`/`pipette_solution`/`holding_potential_mv` | same-name MIMIC cols | verbatim |
| `modulator_name`(non-pharmacology rows) | `compound_id` | link to compound when the row is a ligand-context experiment; NULL otherwise |
| `n` | `n` **[v0.2, TEXT]** | verbatim replicate string |
| `measurement_id`…`extractor_note` | evidence columns **[v0.2]** | verbatim — F-004 tokens preserved; `measurement_id` UNIQUE |
| `condition_key` | `condition_key` **[v0.2]** | verbatim (row-local uniqueness key) |

### 3.5 `compound` — 85 rows (modulator_name dedup, staging parity)
`modulator_role`→`compound_type` normalization: agonist→ACTIVATOR,
blocker/antagonist→INHIBITOR_BLOCKER, potentiator→POTENTIATOR; multi-role
modulators resolve by **majority frequency across rows** with a manifest
entry — four in the corpus: Yoda1 (12/1), lysophosphatidylcholine (9/1),
arachidonic acid (5/1) → ACTIVATOR; **2,2,2-Trifluoroethanol (2/2) is the
sole tie** → deterministic tie-break resolves to INHIBITOR_BLOCKER (staging
stored its own CHECK-vocabulary member `ANTAGONIST` (uppercase); the formal enum
vocabulary normalizes it — parity deviation disclosed in the manifest).
piezo1 `compounds/` descriptors (21/21 with InChIKey) join where available;
other layers name-only. NULL `inchikey` rows are safe (SQLite UNIQUE
tolerates NULLs); manifest discloses descriptor coverage.

### 3.6 `bioactivity` — 136 rows
Corpus kind split: IC50 91 / EC50 21 / KD 13 / KI 8 / PEC50 3 (KB has 0 rows).
`activity_type` = kind.upper() enum; `value`→`activity_value`;
`unit`→`activity_units`; `value_relation`→`relation`;
`modulator_name`→compound link; `assay_description` = `parameter_label` +
`stimulus_detail` concatenation (spec recommendation);
`assay_format`/`cell_line`/`target_species` NULL this load (parse deferred).
Evidence columns as §2. `uq_bioactivity_dedup` respected.

### 3.7 `variant` — 125 rows (hgvs_short dedup from 197 variant-carrying rows)
`variant_hgvs_short`→`mutation_short` (dedup key); `position`/`ref_aa`/`alt_aa`
parsed when the short form is a clean substitution, else NULL; clinical columns
(clinvar/omim/dbsnp) NULL this load; `organism` = channel organism.
Variant↔experiment linkage: extraction rows carry variant context on the
measurement row; v0.1 had no FK → `variant_id` now implemented (§6.3).

### 3.8 `external_reference`
piezo1 `cross_references/` (uniprot↔pdb mapping etc.) → CHANNEL xrefs.
**§9 duty**: loader validates each `(entity_type, entity_id)` target exists at
insert; orphans impossible by construction (insert-after-parent ordering).

### 3.9 `unmapped_measurement` **[v0.2, DECIDED]** — 16 rows
Adjudicated-kept gap rows, composition: pressure_threshold 9, block_voltage 2,
x50 2, tau_act 1, ion_selectivity_ratio 2 (these are `parameter_kind`s of
rows the curation phase adjudicated to KEEP as gap-archive — distinct from
the 130 §3.4 migrations INTO biophysics). Columns per §2.3.

## 4. §9 enforcement checklist (loader duties, v1.0)

- [ ] MIMIC: warn + manifest column (corpus rows predate MIMIC; hard-fail
      activates for post-MIMIC sources).
- [ ] `external_reference` target validation at insert.
- [ ] `ortholog_group` uppercase normalization.
- [ ] Unit-enum strict mapping (unmapped unit = load error).
- [ ] Conservation: 1100 = biophysics 948 + bioactivity 136 + unmapped 16;
      publication 205 (10 shared); channel 12; structure 12; compound 85;
      variant 125; migrations 118+12 all land in typed columns (0 NULLed
      migration values).
- [ ] Determinism: byte-stable dump (SQLite version pinned note; port the
      vault's `data/db/README.md` float-rendering caveat).
- [ ] Frozen-layer semantics: piezo1/piezo2 load as-is; their un-re-verified
      quote status recorded in `db_meta`, not per-row.

## 5. Round plan

- **A2 (next)**: schema v0.2 (evidence columns incl. `n TEXT`, six migration
  columns, `unmapped_measurement`, `db_meta`; §6 decisions all settled 2026-09-01) +
  loader implementation + tests (enum coverage incl. 9 recording modes,
  conservation, determinism, negative fixtures).
- **A3**: run the load against `data-v1.0`, publish `maicdb.sqlite` +
  manifest, cross-repo digest.

## 6. Extension decisions — **all DECIDED 2026-09-01 (user approval, A2a kickoff)**

1. `value_as_reported`/`unit_as_reported` columns — **YES** (implemented in
   schema v0.2).
2. **Multi-gene layer → channel mapping (osca)** — **one family row**: the
   layer's curated canonical label as `gene_symbol`, the four accessions
   (O94886/Q5T3F8/Q9P1W3/Q9XEA1) go to `external_reference`, gene names to
   `gene_aliases`; `uniprot_accession` stays NULL for that row.
3. `variant_id` FK on `biophysics_experiment` — **YES** (implemented).
4. Author enrichment from the vault's Zotero export
   (`.pandoc/zotero-library-1.json`, DOI join, unmatched disclosed in the
   manifest) — **YES** (loader duty, A2b).
5. **`db_meta.license` = CC-BY-4.0** — decided for the DATA corpus
   (consistent with the code repo's pyproject license).
6. `stimulus_detail` structured parse — stays deferred beyond v1.0
   (verbatim only).

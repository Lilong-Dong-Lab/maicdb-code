# MIMIC v0.1 — internal draft

> **Status: INTERNAL DRAFT, not for release.** This document is a working
> draft for the project's own curation and analysis work. It is not a
> published standard, carries no version DOI, and must not be cited
> externally (decided 2026-11-06). It also defines no new storage: per the
> same decision, every mapping described here lives in the **derived
> analysis layer**, never as a write-back to the vault's curated data.

- **Date**: 2026-11-06
- **Basis**: README "The MIMIC Standard" (the five categories), the existing
  `biophysics_experiment` columns, and the measured corpus
  ([corpus baseline](../research/2026-11-06-corpus-baseline.md)).
- **Reproduction**: the per-field coverage figures re-derive from
  `uv run python scripts/corpus-stats.py`; the tier conjunctions in §4/§10 and
  the `stimulus_type` counts in §6.1 are pinned by census SQL in
  `tests/test_corpus_stats.py`. The §6.4 split is explicitly deferred and
  carries no per-value counts.

## 1. Purpose

MIMIC (Minimum Information about a Mechanically Induced Current) is the
field-level contract this project wants a mechanobiology measurement to
satisfy. The schema already reserves the columns; this draft decides which
fields are **required for a row to be comparable**, which vocabularies they
take, and what "missing" means — so that a validator and a coverage report
can be built against a written rule instead of an intuition.

## 2. Scope

| In scope (v0.1) | Out of scope (deferred to v0.2) |
|---|---|
| `biophysics_experiment` rows (948 at data-v1.0) | `bioactivity` rows (compound assays need their own minimum: assay format, cell line, readout) |
| Field tiers, vocabularies, missing-value semantics | `variant` / `structure` linkage rules |
| Row-, publication- and corpus-level scoring | Site rendering of MIMIC scores |
| The `condition_key` dialect problem | Any write-back to the curated data |

## 3. Design principles

1. **Tiers, not one bar.** A single "complete" bar would reject almost the
   whole corpus (§5). v0.1 uses three tiers: **L1** (the fields without which
   two rows cannot be compared), **L2** (fields a reader needs to judge the
   experiment), **L3** (fields that improve reuse).
2. **Controlled vocabulary or declared free text.** An enumerable field is an
   enum with a documented escape value; a genuinely open field (solutions,
   constructs) is free text and says so.
3. **Provenance is not a tier.** The evidence chain is already 99.8% complete
   (946 of 948 rows; only `evidence_location` has gaps) and is a precondition
   for any row, not something to score.
4. **Tri-state missingness.** A validator must distinguish *not recorded*,
   *not applicable* and *unparsed prose*; the derived layer carries the
   distinction, the source data does not have to.
5. **Derived, never destructive.** Mapping and normalisation produce a
   separate analysis output keyed by `measurement_id`; the curated value is
   never rewritten by this standard.

## 4. Tiers

| Tier | Meaning | Fields |
|---|---|---|
| **L1** | two rows comparable at all | provenance set + `recording_mode` + `stimulus_type` |
| **L2** | a reader can judge the experiment | + `cell_type` + `expression_system` |
| **L3** | reusable in modelling / meta-analysis | + `n` + `temperature_c` + `ph` + bath/pipette solutions + holding potential |

### Measured adherence (data-v1.0, cumulative)

Census SQL per row (each step adds one predicate to the previous one; the
provenance set is `measurement_id`, `evidence_quote`, `confidence`,
`condition_key`):

| Tier step | Rows | Share of 948 |
|---|---|---|
| provenance set | 948 | 100.0% |
| + `recording_mode` | 909 | 95.9% |
| + `stimulus_type` (**L1 complete**) | 808 | **85.2%** |
| + `cell_type`, `expression_system` (**L2 complete**) | 676 | **71.3%** |
| + `n` | 335 | 35.3% |
| + `temperature_c` | 23 | 2.4% |
| + `ph` | 11 | 1.2% |
| + `bath_solution` | 11 | 1.2% |
| + `pipette_solution` | 11 | 1.2% |
| + `holding_potential_mv` (**L3 complete**) | 11 | 1.2% |

Temperature is **not** an L1 field in v0.1: promoting it would drop the
qualified corpus from 85.2% (808) to 5.6% (53 rows, L1 ∩ temperature). It
stays L3, and the environment gap is reported as a corpus finding rather than
a row gate; full L3 adherence is 11 rows (1.2%).

The tier counts above score the **raw** corpus, so they include the 238
`stimulus_type = OTHER` rows that §6.1 blocks in v0.1. Excluding `OTHER`,
L1 = 578 (61.0%) and L2 = 467 (49.3%).

## 5. Field specification

Coverage is "rows with a non-NULL value / 948" at data-v1.0.

### 5.1 Stimulus

| Field | Tier | Type | Coverage | Note |
|---|---|---|---|---|
| `stimulus_type` | **L1** | enum (§6.1) | 86.9% | `OTHER` holds 238 rows (25%) and `NULL` 124 — the enum is the largest vocabulary task |
| `stimulus_waveform` | L3 | enum (step, ramp, pulse, sinusoidal, other) | 0% | column reserved, never populated |
| `stimulus_velocity` + unit | L3 | number + unit | 0% | needed for rate-dependent thresholds |
| `stimulus_duration_ms` | L3 | number | 0% | — |
| `probe_geometry` | L3 | enum (pipette, blunt probe, bead, AFM tip, membrane-only, other) | 0% | — |
| `probe_diameter_um` | L3 | number | 0% | — |

### 5.2 Recording

| Field | Tier | Type | Coverage | Note |
|---|---|---|---|---|
| `recording_mode` | **L1** | enum (§6.2) | 95.9% | — |
| `holding_potential_mv` | L3 | number | 65.3% | L2 candidate once measured per family |
| `sampling_rate_khz` | L3 | number | 0% | — |
| `filter_khz` | L3 | number | 0% | — |
| `analysis_method` | L3 | enum (§6.3) | 0% | column reserved; today the method is only implicit in `extractor_note` (189 of the 945 notes mention a fit) |

### 5.3 Cell context

| Field | Tier | Type | Coverage | Note |
|---|---|---|---|---|
| `cell_type` | **L2** | controlled label (native cell type or host line) | 82.4% | free text today; needs the §6.4 split |
| `expression_system` | **L2** | controlled label + detail | 95.7% | free text today, up to 296 characters per row (444 of the 907 populated rows exceed 90); decomposition deferred, §6.4 |

### 5.4 Environment

| Field | Tier | Type | Coverage | Note |
|---|---|---|---|---|
| `temperature_c` | L3 | number (°C) | 9.0% | 17–38 °C, median 24 — the thinnest environment field |
| `ph` | L3 | number | 57.7% | 5.0–9.5, median 7.3 |
| `bath_solution` | L3 | free text | 77.5% | declared free text; a composition vocabulary is v0.2 |
| `pipette_solution` | L3 | free text | 68.6% | same |

### 5.5 Analysis

| Field | Tier | Type | Coverage | Note |
|---|---|---|---|---|
| `n` | L3 | integer, or a range/text as recorded (the column is TEXT) | 53.1% | the field that separates 71% from 35%; 16 of the 503 populated rows hold values like `3-6` or `>4`, so a validator must parse integer-or-range rather than int |
| `n_cells` | L3 | integer | 0% | redundant with `n` until the two are defined apart |

### 5.6 Provenance (precondition, not scored)

| Field | Coverage | Note |
|---|---|---|
| `measurement_id`, `evidence_quote`, `confidence`, `condition_key` | 100% | `confidence` has no written rubric today — §6.5 fixes that |
| `evidence_location` | 99.8% | taxonomy in the corpus baseline (Results 71.9%) |
| `extractor_note` | 99.7% | record language as-recorded, never translated |

## 6. Controlled vocabularies (v0.1)

### 6.1 `stimulus_type`

The enum has ten members (`src/maicdb/enums.py`); v0.1 keeps all of them and
splits the two escape hatches rather than inventing new top-level names:

| Value | Rows | Action |
|---|---|---|
| `PRESSURE_CLAMP` | 314 | keep |
| `SUCTION` | 110 | keep |
| `INDENTATION` | 95 | keep |
| `TOUCH` | 22 | keep |
| `HYPOTONIC` | 15 | keep |
| `SHEAR_STRESS` | 12 | keep |
| `POSITIVE_PRESSURE` | 11 | keep |
| `MEMBRANE_STRETCH` | 7 | keep (defined as "bilayer deformation without a probe") |
| `OSMOTIC` | 0 | keep (member of the enum, unused at data-v1.0) |
| `OTHER` | 238 | **blocked in v0.1**: must be replaced by a value or by `OTHER: <free detail>` plus `stimulus_waveform`; the 238 rows are the first curation backlog item |
| `NULL` | 124 | treat as *not recorded*, not as *not applicable* |

### 6.2 `recording_mode`

Existing values are adequate: `WHOLE_CELL`, `CELL_ATTACHED`, `INSIDE_OUT`,
`OUTSIDE_OUT`, `TEVC`, `RECONSTITUTED_PROTEOLIPOSOME`, `PLANAR_PATCH`,
`PERFORATED_PATCH`. v0.1 retires `OTHER` (12 rows) the same way as §6.1 and
requires the two-electrode mode to name the oocyte context in `cell_type`.

### 6.3 `analysis_method`

New enum (0% covered today): `BOLTZMANN_FIT`, `HILL_FIT`, `LINEAR_FIT`,
`SINGLE_EXPONENTIAL_FIT`, `MULTI_EXPONENTIAL_FIT`, `THRESHOLD_CROSSING`,
`MANUAL_READ`, `OTHER`. `extractor_note` keeps the free-text detail.

### 6.4 `expression_system` → host + method + detail

The current column mixes three facts in one string. v0.1 defines the
decomposition (derived layer; `measurement_id` keeps the link):

| Component | Values | Status at data-v1.0 |
|---|---|---|
| `host_system` | `HEK293`, `CHO`, `XENOPUS_OOCYTE`, `E_COLI_SPHEROPLAST`, `RECONSTITUTED_MEMBRANE`, `NATIVE_CELL`, `OTHER` | 907 populated free-text rows; the split rule is **not yet committed**, so no per-value counts are stated here |
| `expression_method` | `TRANSIENT`, `STABLE`, `ENDOGENOUS`, `PURIFIED_RECONSTITUTED`, `UNKNOWN` | derived alongside |
| `expression_detail` | free text, verbatim | keeps the original string |

The split rule is v0.2 work. The measured facts are: 907 populated rows,
longest string 296 characters, 444 rows longer than 90 characters. An
ad-hoc pass produced a host-system breakdown, but because its rule was never
committed it does not re-derive from the sources cited at the top of this
document, so the breakdown is deliberately not reported. The mapping
decisions belong in a data-notes table with the rule itself, not in this
draft.

### 6.5 `confidence`

The only field with 100% coverage but no written rubric. v0.1 defines:

| Value | Criterion |
|---|---|
| `high` | value stated explicitly in text or table; unit explicit; condition unambiguous |
| `medium` | value readable from a figure / legend, or one condition component inferred by the extractor |
| `low` | value reconstructed from multiple statements, or the condition is known-incomplete |

Applied to the corpus this rubric would still produce 537/400/11; a re-audit
sample is the check that it is applied consistently (deferred work).

## 7. `condition_key`

Two dialects coexist: 569 structured (`253J_native_inside-out_-60mV_sym150KCl`)
and 379 prose (`Acutely dissociated mouse Müller glia, ... 25°C`).

v0.1 rule: the structured form is the target grammar —

```
<construct>_<cell>_<recording>_<potential>_<solution>
```

with `not-recorded` as an explicit token for an absent component. Prose keys
are labelled `UNSTRUCTURED` in the derived layer and are **not** silently
parsed; a parser may extract components from them, but any extracted value
carries its own provenance and never overwrites the original key.

## 8. Missing-value semantics

The derived layer distinguishes, per field:

| Label | Meaning |
|---|---|
| `NOT_RECORDED` | source is NULL and the paper does not say |
| `UNPARSED` | source is free text that a rule could not map (e.g. a host-system string the §6.4 rule cannot classify) |
| `NOT_APPLICABLE` | the field cannot exist for this design (e.g. probe geometry on a patch-only pressure clamp) |
| `PRESENT` | a value, with provenance |

`NOT_APPLICABLE` is an assertion by a curator and must cite the reason;
defaults are never `NOT_APPLICABLE`.

## 9. Scoring

- **Row level**: L1 / L2 / L3 complete, plus per-field status labels.
- **Publication level**: share of the paper's rows at each tier.
- **Corpus level**: the cumulative table in §4, re-derived by the validator.
- A row can be L1-complete and still fail the evidence precondition (two rows
  at data-v1.0 have a NULL `evidence_location`, so they fail the location
  component) — the validator reports the two independently.

## 10. Baseline adherence (v0.1 reading of data-v1.0)

| Measure | Value |
|---|---|
| Rows at L1 | 808 / 948 (85.2%) |
| Rows at L2 | 676 / 948 (71.3%) |
| Rows at L3 (`n`) | 335 / 948 (35.3%) |
| Rows at L3 (all environment fields) | 11 / 948 (1.2%) |
| Rows at L1 excluding `stimulus_type = OTHER` | 578 / 948 (61.0%) |
| Rows at L2 excluding `stimulus_type = OTHER` | 467 / 948 (49.3%) |
| Worst families at L1 | K2P 54/145 (37.2%), TRP 22/70 (31.4%) — `stimulus_type` gaps: K2P populates it on 59/145 rows, TRP on 33/70; the other five families are at 99.5–100% |
| `stimulus_type = OTHER` backlog | 238 rows |
| `expression_system` free-text rows | 907 (split deferred to v0.2) |
| Prose condition keys | 379 rows |

## 11. Open questions (decisions needed before v0.2)

1. **Temperature tier**: keep L3 (current proposal) or promote to L2 once
   coverage passes a threshold? A threshold proposal needs a decision.
2. **`n` vs `n_cells`**: define the distinction or retire one.
3. **K2P / TRP L1 failure**: is it a curation gap (re-extractable from source
   PDFs) or an inherent property of lipid-only experiments that should relax
   `stimulus_type`?
4. **Bioactivity's own standard**: `IC50/EC50/KD/KI` rows need assay-format
   and cell-line minima; v0.2 proposal required.
5. **Unit policy** (from the corpus baseline, F3): `mN/m` ≡ `dyn/cm` is a
   spelling decision; `psi → mmHg` and `um → nm` are conversions. Where does
   the rule live before any analysis merges buckets?

## 12. Appendix

### A. Schema mapping

| MIMIC category | Columns |
|---|---|
| Stimulus | `stimulus_type`, `stimulus_waveform`, `stimulus_velocity(_unit)`, `stimulus_duration_ms`, `probe_geometry`, `probe_diameter_um` |
| Recording | `recording_mode`, `holding_potential_mv`, `sampling_rate_khz`, `filter_khz`, `analysis_method` |
| Cell context | `cell_type`, `expression_system` |
| Environment | `temperature_c`, `ph`, `bath_solution`, `pipette_solution` |
| Analysis | `n`, `n_cells` |
| Provenance | `measurement_id`, `evidence_quote`, `evidence_location`, `confidence`, `extractor_note`, `condition_key` |

### B. Next artifact

`scripts/mimic-validate.py` (read-only): emits the §9 scoring per row and
publication as deterministic JSON, with the §8 status labels. It must not
write to the database, and its corpus totals must reproduce §4's table.

### C. References

- README "The MIMIC Standard"
- `docs/research/2026-11-06-corpus-baseline.md` (measured corpus shape)
- `docs/m3-website-spec.md` §4 (artifact census)

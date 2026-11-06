# MAIC-DB corpus baseline: literature and data (meta-research pass 1)

- **Date**: 2026-11-06
- **Question owner**: data-analysis track — before defining the MIMIC
  standard (internal draft v0.1), measure what the corpus actually contains
- **Method**: one read-only pass over the published artifact
  (`db/maicdb.sqlite`, data-v1.0) by `scripts/corpus-stats.py`. Every number
  below is a query result; nothing is transcribed by hand. Journal names are
  normalised through the alias table in the script, and the raw variants
  behind each canonical spelling are listed as a data-quality finding (the
  vault owns the canonical spelling).
- **Reproduction**:

  ```bash
  uv run python scripts/corpus-stats.py                    # Markdown
  uv run python scripts/corpus-stats.py --json /tmp/c.json # raw stats
  ```

  Two runs produce byte-identical output (verified by
  `test_stats_are_deterministic`). The generated report in §4 is verified
  byte-identical to a fresh run by
  `test_embedded_report_matches_generated_output`, so it cannot go stale; the
  findings above it are narrative, and only the figures their tests name are
  pinned.

## 1. What this baseline is for

The site currently renders the corpus row by row. This pass asks the prior
question — what is the shape of the corpus itself — so the MIMIC draft and
the meta-research programme are written against measured facts rather than
an impression. It changes no data, schema or site output; per the scope
decision it is a derived analysis layer only.

## 2. Headline numbers

| Question | Answer |
|---|---|
| Papers / biophysics rows / bioactivity rows | 211 / 948 / 136 |
| Channels / families | 12 / 7 |
| Publication years | 1986–2026 (peak 2018 with 15 papers) |
| Rows per paper | median 4, max 32; 8 papers contribute no biophysics/bioactivity rows (6 of those have no row in any measurement table) |
| Parameter rows | 16 registered parameters, 263 (conductance) down to 3 (osmotic threshold) |
| Confidence | high 537 (56.6%), medium 400 (42.2%), low 11 (1.2%) |
| Journal strings | 67 raw → 56 after normalisation (7 variant groups) |
| Condition keys | 939 unique / 948; 569 structured, 379 prose-style |
| MIMIC-design fields at 0% | 9 of 24 probed (stimulus velocity/waveform/duration, probe geometry/diameter, sampling rate, filter, analysis method, n_cells) |

## 3. Findings that matter for the two tracks

**F1 — Curation density does not follow literature volume.** Rows per
channel range from 160 (PIEZO1) to 18 (TRESK), but publications per channel
are far flatter (24 TMC … 6 TRESK): TRESK has 6 papers yet 34 bioactivity
rows, while PIEZO2 has 8 papers and 0 bioactivity rows. Any "under-studied
channel" claim must state which axis it means.

**F2 — Parameter coverage is extremely skewed.** `conductance` (263),
`p50` (152) and `tau_inact` (93) carry 54.3% of the 936 value-bearing rows;
`ca_permeability` (4), `osmotic_threshold` (3) and `thermal_threshold` (9)
are near-empty. The per-channel matrix shows the gaps are structural, not
random: no channel covers all 16 parameters, and 3 of 12 channels (TRESK 14,
PIEZO2 12, TREK-2 10) have zero rows for at least 10 of them.

**F3 — Unit heterogeneity is concentrated, and one column looks mis-typed.**
`t50` splits into `mN/m` (26) and `dyn/cm` (15) — numerically identical
(1 mN/m = 1 dyn/cm), so this is a spelling issue, not a conversion decision.
`p50` splits `mmHg` (148) / `psi` (4) — a real conversion; `x50` splits
`nm` (37) / `um` (9) (×1000); `osmotic_threshold` mixes `%`, `% HTS`, `mOsm`
(non-comparable without a written rule). The largest heterogeneity sits in
`threshold_fold_shift`, which carries three semantically incompatible units —
`%` (13), `fold` (6) and **`nm` (12)** — plus 4 rows with a value and no unit.
A length in a fold-shift column is probably a column-semantics error in the
source extraction, not a unit-choice problem; it needs a vault adjudication
before any analysis pools the column.

**F4 — Evidence provenance is the strongest part of the corpus.** quote,
confidence, condition key and measurement id sit at 100%; location at 99.8%.
By contrast the MIMIC experiment-metadata fields are thin: temperature 9.0%,
`n` 53.1%, pH 57.7%.

**F5 — Evidence locations cluster in narrative text.** 779 of 1084 rows
(71.9%) point at Results prose, 122 at tables, 101 at figure legends, 45 at
abstracts. Abstract-sourced rows are the weakest evidence class and are
countable exactly.

**F6 — Condition keys come in two dialects.** 569 rows use the structured
underscore form, 379 use prose. A MIMIC-aligned key grammar can only be
applied to the structured half; the prose half has to be re-curated or
marked as unstructured — the draft must say which.

**F7 — Journal spelling needs one canonical pass in the vault.** Normalisation
collapses 67 raw strings to 56 canonical names through 7 variant groups
(`J Biol Chem` / `Journal of Biological Chemistry`, `PNAS` plus four variants,
`J Neurosci` / `Journal of Neuroscience` / `The Journal of Neuroscience`,
`eLife` / `Elife`, `PLoS ONE` / `PLoS One`, …). Meta-research over journals is
misleading until this is fixed upstream.

**F8 — A publication row does not imply data.** 8 of 211 papers contribute no
biophysics or bioactivity rows; two of them (publication 35 and 90) do carry
`unmapped_measurement` rows, so 6 papers have no row at all across the three
measurement tables. They should be either justified (context papers) or
dropped, and the answer belongs in the data notes.

## 4. Generated report

Derived by `scripts/corpus-stats.py` from `db/maicdb.sqlite` (read-only).
Every number is a query result; no value is transcribed by hand.

### 1. Corpus scale

| Table | Rows |
|---|---|
| bioactivity | 136 |
| biophysics_experiment | 948 |
| channel | 12 |
| compound | 86 |
| external_reference | 6 |
| publication | 211 |
| unmapped_measurement | 16 |
| variant | 125 |

### 2. Publication bibliometrics

- Year range: **1986–2026**
- Distinct journal strings (raw): **67**
- Distinct journals after normalisation: **56**
- Rows per publication: total 1084 across 211 papers (median 4.0, max 32, 8 with no rows)

#### Publications per year

| Year | Publications |
|---|---|
| 1986 | 1 |
| 1993 | 1 |
| 1995 | 1 |
| 1996 | 1 |
| 1997 | 3 |
| 1998 | 3 |
| 1999 | 3 |
| 2000 | 3 |
| 2001 | 4 |
| 2002 | 8 |
| 2003 | 4 |
| 2004 | 8 |
| 2005 | 6 |
| 2006 | 4 |
| 2007 | 4 |
| 2008 | 3 |
| 2010 | 6 |
| 2011 | 10 |
| 2012 | 9 |
| 2013 | 14 |
| 2014 | 9 |
| 2015 | 12 |
| 2016 | 9 |
| 2017 | 13 |
| 2018 | 15 |
| 2019 | 11 |
| 2020 | 10 |
| 2021 | 11 |
| 2022 | 4 |
| 2023 | 5 |
| 2024 | 12 |
| 2025 | 2 |
| 2026 | 2 |

#### Top journals (normalised)

| Journal | Publications |
|---|---|
| Proceedings of the National Academy of Sciences | 23 |
| Journal of Biological Chemistry | 22 |
| The Journal of General Physiology | 20 |
| eLife | 15 |
| Nature Communications | 13 |
| Biophysical Journal | 12 |
| The Journal of Neuroscience | 11 |
| Neuron | 8 |
| The EMBO Journal | 8 |
| PLOS ONE | 7 |
| Cell Reports | 6 |
| British Journal of Pharmacology | 4 |
| Nature | 4 |
| Scientific Reports | 4 |
| The Journal of Physiology | 4 |

#### Journal spelling variants (data-quality list)

- **Journal of Biological Chemistry** ← `J Biol Chem`, `Journal of Biological Chemistry`
- **PLOS ONE** ← `PLoS ONE`, `PLoS One`
- **Proceedings of the National Academy of Sciences** ← `PNAS`, `Proc Natl Acad Sci U S A`, `Proc Natl Acad Sci USA`, `Proceedings of the National Academy of Sciences`, `Proceedings of the National Academy of Sciences USA`
- **The EMBO Journal** ← `EMBO J`, `The EMBO Journal`
- **The Journal of General Physiology** ← `J Gen Physiol`, `The Journal of General Physiology`
- **The Journal of Neuroscience** ← `J Neurosci`, `Journal of Neuroscience`, `The Journal of Neuroscience`
- **eLife** ← `Elife`, `eLife`

### 3. Channels

| Channel | Family | Biophysics rows | Bioactivity rows | Publications |
|---|---|---|---|---|
| PIEZO1 | PIEZO | 160 | 14 | 23 |
| TMC | TMC | 153 | 19 | 24 |
| ASIC | DEG_ENaC_ASIC | 108 | 24 | 19 |
| MscS | MSCL_MSCS | 103 | 1 | 23 |
| OSCA | OSCA_TMEM63 | 92 | 2 | 12 |
| MscL | MSCL_MSCS | 89 | 0 | 18 |
| TRPV4 | TRP | 70 | 37 | 23 |
| TREK-1 | K2P | 46 | 4 | 13 |
| TREK-2 | K2P | 42 | 0 | 16 |
| TRAAK | K2P | 39 | 1 | 10 |
| PIEZO2 | PIEZO | 28 | 0 | 8 |
| TRESK | K2P | 18 | 34 | 6 |

### 4. Parameter coverage (rows with a value, per channel)

| Channel | p50 | t50 | x50 | slope | tau_act | tau_inact | tau_deact | conductance | reversal_potential | delta_p50 | ion_selectivity_ratio | ca_permeability | threshold_fold_shift | macroscopic_rise_time | thermal_threshold | osmotic_threshold |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ASIC | 0 | 0 | 0 | 1 | 21 | 14 | 14 | 14 | 28 | 0 | 11 | 4 | 0 | 0 | 0 | 0 |
| MscL | 21 | 15 | 0 | 3 | 0 | 1 | 1 | 39 | 0 | 1 | 0 | 0 | 8 | 0 | 0 | 0 |
| MscS | 21 | 14 | 0 | 0 | 1 | 3 | 11 | 27 | 5 | 9 | 4 | 0 | 8 | 0 | 0 | 0 |
| OSCA | 36 | 0 | 4 | 0 | 13 | 12 | 2 | 13 | 2 | 0 | 8 | 0 | 0 | 2 | 0 | 0 |
| PIEZO1 | 56 | 9 | 4 | 2 | 0 | 28 | 4 | 31 | 14 | 6 | 5 | 0 | 1 | 0 | 0 | 0 |
| PIEZO2 | 0 | 0 | 0 | 0 | 0 | 15 | 0 | 4 | 4 | 0 | 0 | 0 | 0 | 4 | 0 | 0 |
| TMC | 2 | 0 | 38 | 0 | 1 | 9 | 0 | 47 | 17 | 0 | 27 | 0 | 12 | 0 | 0 | 0 |
| TRAAK | 2 | 1 | 0 | 2 | 4 | 2 | 4 | 19 | 4 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| TREK-1 | 12 | 1 | 0 | 3 | 1 | 9 | 0 | 13 | 5 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| TREK-2 | 1 | 1 | 0 | 2 | 0 | 0 | 0 | 30 | 0 | 0 | 3 | 0 | 0 | 0 | 2 | 0 |
| TRESK | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 17 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| TRPV4 | 1 | 0 | 0 | 0 | 4 | 0 | 4 | 9 | 17 | 0 | 8 | 0 | 6 | 6 | 6 | 3 |

| Parameter | Rows |
|---|---|
| p50 | 152 |
| t50 | 41 |
| x50 | 46 |
| slope | 13 |
| tau_act | 45 |
| tau_inact | 93 |
| tau_deact | 40 |
| conductance | 263 |
| reversal_potential | 97 |
| delta_p50 | 16 |
| ion_selectivity_ratio | 66 |
| ca_permeability | 4 |
| threshold_fold_shift | 35 |
| macroscopic_rise_time | 13 |
| thermal_threshold | 9 |
| osmotic_threshold | 3 |

### 5. Unit spellings per parameter

- **p50**: `mmHg` ×148, `psi` ×4
- **t50**: `mN/m` ×26, `dyn/cm` ×15
- **x50**: `nm` ×37, `um` ×9
- **osmotic_threshold**: `%` ×1, `% HTS` ×1, `mOsm` ×1
- **delta_p50**: `mmHg` ×16
- **threshold_fold_shift**: `%` ×13, `nm` ×12, `fold` ×6

### 6. Confidence

| Confidence | Rows |
|---|---|
| high | 537 |
| medium | 400 |
| low | 11 |

#### Confidence by family

| Family | Confidence | Rows |
|---|---|---|
| DEG_ENaC_ASIC | high | 91 |
| DEG_ENaC_ASIC | medium | 17 |
| K2P | high | 87 |
| K2P | medium | 58 |
| MSCL_MSCS | high | 72 |
| MSCL_MSCS | medium | 120 |
| OSCA_TMEM63 | high | 90 |
| OSCA_TMEM63 | medium | 2 |
| PIEZO | high | 159 |
| PIEZO | low | 2 |
| PIEZO | medium | 27 |
| TMC | high | 13 |
| TMC | low | 1 |
| TMC | medium | 139 |
| TRP | high | 25 |
| TRP | low | 8 |
| TRP | medium | 37 |

### 7. Evidence-location taxonomy

| Bucket | Rows |
|---|---|
| results | 779 |
| table | 122 |
| figure legend | 101 |
| abstract | 45 |
| results and discussion | 19 |
| other | 13 |
| (null) | 2 |
| discussion | 2 |
| methods | 1 |

### 8. Environment reporting

| Field | Rows | Min | Median | Max |
|---|---|---|---|---|
| ph | 547 | 5.0 | 7.3 | 9.5 |
| temperature_c | 85 | 17.0 | 24.0 | 38.0 |

### 9. Bioactivity block

- Rows: **136**, compounds: **69**, channels: **9**
- Activity types: `IC50` ×91, `EC50` ×21, `KD` ×13, `KI` ×8, `PEC50` ×3

### 10. MIMIC field coverage snapshot

#### stimulus

| Field | Rows | % of biophysics rows |
|---|---|---|
| stimulus_type | 824 | 86.9% |
| stimulus_waveform | 0 | 0.0% |
| stimulus_velocity | 0 | 0.0% |
| stimulus_duration_ms | 0 | 0.0% |
| probe_geometry | 0 | 0.0% |
| probe_diameter_um | 0 | 0.0% |

#### recording

| Field | Rows | % of biophysics rows |
|---|---|---|
| recording_mode | 909 | 95.9% |
| sampling_rate_khz | 0 | 0.0% |
| filter_khz | 0 | 0.0% |
| holding_potential_mv | 619 | 65.3% |
| analysis_method | 0 | 0.0% |

#### cell_context

| Field | Rows | % of biophysics rows |
|---|---|---|
| expression_system | 907 | 95.7% |
| cell_type | 781 | 82.4% |

#### environment

| Field | Rows | % of biophysics rows |
|---|---|---|
| temperature_c | 85 | 9.0% |
| ph | 547 | 57.7% |
| bath_solution | 735 | 77.5% |
| pipette_solution | 650 | 68.6% |

#### analysis

| Field | Rows | % of biophysics rows |
|---|---|---|
| n | 503 | 53.1% |
| n_cells | 0 | 0.0% |

#### provenance

| Field | Rows | % of biophysics rows |
|---|---|---|
| measurement_id | 948 | 100.0% |
| evidence_quote | 948 | 100.0% |
| evidence_location | 946 | 99.8% |
| confidence | 948 | 100.0% |
| condition_key | 948 | 100.0% |

### 11. Condition keys

- Rows: **948**, unique: **939**
- Structured (underscore, no spaces): **569**; prose-style (contains spaces): **379**

Corpus size used for every percentage above: 948 biophysics rows.

## 5. What to do next (proposed, in order)

1. **MIMIC draft v0.1 (internal, not for release)** written against
   F4/F5/F6: field tiers, controlled vocabularies for the free-text fields,
   and the two-dialect condition-key rule. Deliverable:
   `docs/mimic/mimic-v0.1.md`.
2. **Time-trend pass** (needs one more query): field completeness ×
   publication decade, to answer whether newer papers would satisfy MIMIC L1
   more often; adds a `--trend` section to the same script.
3. **Journal canonicalisation** in the vault (data authority), then re-run
   this baseline; the variant list above is the input.
4. **Unit rules**: decide `mN/m` ≡ `dyn/cm` (spelling only), the
   `psi → mmHg` and `um → nm` conversion policy, and the osmotic-threshold
   rule; record them as a data-notes decision before any analysis merges
   buckets.
5. **Meta-research questions** (each a later research note): curation vs
   literature volume; completeness trend; confidence × location type; PIEZO
   dominance and the frozen-layer bias.

## 6. Sources

- `db/maicdb.sqlite` (data-v1.0 artifact, opened read-only)
- `scripts/corpus-stats.py` (this report's producer; journal aliases and
  MIMIC column groups live in the script)
- `tests/test_corpus_stats.py` (pins the numbers above)
- `docs/m3-website-spec.md` §4 (the census values this pass re-confirms)


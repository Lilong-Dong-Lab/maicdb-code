# Analytics Pipeline Spec — MAIC-DB

| | |
|---|---|
| **Status** | Draft (approved in scope review 2026-11-05; P0 decisions open) |
| **Data baseline** | tag `data-v1.0`, vault head `5a8ff0ed5cacf62dd2517fd23a6f0d1848c93b7e`, `schema_version 0.2.0` (see `db/load-manifest.json`) |
| **MIMIC authority** | vault `report/MAICDB_Schema_Design.md` §4.3, `mimic_standard_version v0.1-draft` in `db_meta`; README §"The MIMIC Standard" |
| **Naming** | **MIMIC** (Minimum Information about a Mechanically Induced Current) is canonical. Known collision with PhysioNet MIMIC-IV; acceptable for now, revisit before the companion paper. |

## 1. Motivation

The static site (ADR-0004) displays curated records. It performs no analysis. The
proposal claims a reporting standard — MIMIC — but the published artifact carries
no evidence for or against it. The loop is open in three places:

1. The schema is **MIMIC-compatible by design**: every MIMIC-mandated column
   exists on `biophysics_experiment` (§4.3), nullable on purpose.
2. Enforcement was **deferred to the loader** and never switched on
   (vault §9: stimulus velocity, probe geometry, recording mode, experimental
   context).
3. Nobody has **measured** what fraction of source papers could satisfy
   MIMIC — the audit that would justify the standard as a proposal.

This spec defines one analysis module that closes all three: it scores records
against MIMIC, synthesizes the biophysics, and feeds both the website and the
publication figure set from the same code.

## 2. Goals and non-goals

**Goals**

- Turn MIMIC from a proposal into a measured result (compliance audit).
- Quantitative cross-channel comparisons of thresholds and kinetics.
- Effect-size views over variants and compounds.
- Field-trend views over 40 years of literature.
- One shared module → paper figures **and** site analytics pages.

**Non-goals**

- No re-curation of the frozen corpus inside this repo (the vault is the
  curation authority; gaps found here route back as vault issues).
- No live/in-browser computation; the site stays static (ADR-0004). All
  analytics are prebuilt JSON/figures.
- No causal claims from observational aggregates.

## 3. Data census (baseline)

Counts per table (`data-v1.0`): publication 211, channel 12, compound 86,
bioactivity 136, structure 12, variant 125, biophysics_experiment 948,
unmapped_measurement 16.

MIMIC metadata completeness over 948 experiments — the number that motivates
Track A:

| MIMIC category | Field | Populated | MIMIC category | Field | Populated |
|---|---|---|---|---|---|
| Stimulus | `stimulus_type` | 87% | Recording | `sampling_rate_khz` | 0% |
| Stimulus | `stimulus_waveform` | 0% | Recording | `filter_khz` | 0% |
| Stimulus | `stimulus_velocity` | 0% | Cell context | `expression_system` | 96% |
| Stimulus | `stimulus_duration_ms` | 0% | Cell context | `cell_type` | 82% |
| Stimulus | `probe_geometry` | 0% | Environment | `temperature_c` | 9% |
| Stimulus | `probe_diameter_um` | 0% | Environment | `ph` | 58% |
| Recording | `recording_mode` | 96% | Environment | `bath_solution` | 78% |
| Recording | `holding_potential_mv` | 65% | Environment | `pipette_solution` | 69% |
| Analysis | `analysis_method` | 0% | Analysis | `protocol_ref` | 0% |
| Analysis | `n_cells` | 0% | Analysis | `n` (legacy text) | 53% |

Re-derive with:

```sql
-- census (single row per field). For text columns, empty strings count as
-- unpopulated: COUNT(NULLIF(<col>, '')); for numeric columns COUNT(<col>)
-- suffices. On data-v1.0 both forms agree on all 20 fields (no empty
-- strings exist yet — the distinction matters for future releases).
SELECT ROUND(100.0*COUNT(<col>)/COUNT(*)) FROM biophysics_experiment;
-- table counts
SELECT 'biophysics_experiment', COUNT(*) FROM biophysics_experiment UNION ALL
SELECT 'publication', COUNT(*) FROM publication UNION ALL
SELECT 'variant', COUNT(*) FROM variant UNION ALL
SELECT 'bioactivity', COUNT(*) FROM bioactivity UNION ALL
SELECT 'compound', COUNT(*) FROM compound UNION ALL
SELECT 'structure', COUNT(*) FROM structure UNION ALL
SELECT 'channel', COUNT(*) FROM channel;
```

Two findings frame the whole pipeline:

- **The `n` split.** Replicate counts live in the legacy text column `n`
  (53%), not `n_cells` (0%). A naive audit reading `n_cells` would report
  the wrong number. The harmonization layer must coalesce the two.
- **Extraction vs reporting.** A NULL column means either *paper did not
  report* or *curator did not extract*. These demand different responses
  (field problem vs database gap). Without separating them, the audit
  measures our pipeline, not the field. → P0 tri-state decision (§7.1).

Value coverage for Track B: p50 152, conductance 263, tau_inact 93,
ion_selectivity 66, tau_act 45, x50 46, t50 41, tau_deact 40, slope 13,
delta_p50 16.

## 4. Architecture

```
 maicdb.sqlite (frozen artifact; read-only)
      │
      ▼
 [P1] harmonization/        units, coalesce(n, n_cells), log10 transforms,
      │                     same-fit row join (P50/slope split across rows),
      │                     derived quantities (pActivity, ΔP50 relative shift)
      ▼
 [P2] per_record/           MIMIC score + category sub-scores, field status
      │                     registry, quality flags      → per-record JSON
      ▼
 [P3] track_mimic_audit/    completeness heatmap, year trend, journal/format
 [P4] track_biophysics/     log-P50 meta-analysis, kinetics atlas, heterogeneity
 [P5] track_atlas/          ΔP50 effect table, compound×channel selectivity
      │ (P6 needs P1 only — no per-record scoring)
      ▼
 [P6] track_field_trends/   pubs/year, parameter adoption, assay-format drift
      │
      ▼
 [P7] delivery              site/_data/analysis/*.json (site pages, static)
                             figures/ (publication set, version-DOI captions)
```

Module home: `src/maicdb/analysis/`. Outputs land in `dist/analysis/<data-tag>/`
(release-local, like other `dist/` artifacts); the site build copies the JSON
payloads it needs. Exact output layout is finalized in the P1 PR.

**Design rules**

- Reads the frozen artifact only; never the live vault.
- Deterministic: same artifact tag → byte-identical outputs.
- Every figure caption carries the data version DOI (per ADR-0002).
- New dependencies (proposed: `numpy`, `scipy`, `matplotlib`; dev-only
  `pytest` pins already present) enter via one PR with this spec as the
  justification. Statistics below are implementable in `numpy`/`scipy`
  alone; `matplotlib` only renders figures.

## 5. Track definitions

### 5.1 Track A — MIMIC compliance audit (P3)

Per-experiment compliance score = fraction of **applicable** MIMIC fields
populated (applicability rules, §7.2). Unweighted first; category weights
only as a sensitivity analysis.

Views: completeness heatmap (field × family); compliance vs publication year
(1986–2026) with a pre/post-PIEZO era contrast; breakdown by journal, assay
format, recording mode; per-record badge on channel cards.

Precedent: MIAME/MIATA compliance studies. The headline test is the vault §9
four-field enforcement list — e.g. temperature alone (`temperature_c` 9%)
means ~91% of records fail; the four-field list as written means **100%**
fail (`stimulus_velocity` is 0% populated). State both numbers; the pair,
defended by the tri-state, is the paper's motivation figure.

### 5.2 Track B — cross-family biophysics (P4)

- **Thresholds.** Per-channel random-effects meta-analysis on log-P50
  (DerSimonian–Laird; cluster = publication × condition_key to respect
  within-paper dependence). Report pooled geometric mean, 95% CI, prediction
  interval, I². Split by stimulus modality — pressure (mmHg/kPa dual-report)
  never pools with indentation (µm) or stretch (mN/m). Tension conversion via
  the Laplace relation is deferred until probe geometry exists (0% today);
  this analysis defines the curation demand.
- **Kinetics atlas.** tau_act / tau_inact / tau_deact distributions per
  channel, log scale, individual points over boxes. No pooling statistic
  across families; descriptive.
- **Heterogeneity.** Same channel × same stimulus across labs: report
  between-lab spread. This is a reproducibility claim; keep it descriptive
  and cite k (studies) and n (records) everywhere.
- **Boltzmann ΔG demo.** Census caveat (verified against data-v1.0): `slope`
  exists on 13 records, but P50 and slope **never co-occur on one row**
  (0 of 948). Same-fit pairs are split across rows, linked only by
  `condition_key` prose (≈4–5 pairs at most). Exactly 3 of the 13 slopes
  are compound dose-response Hill slopes (Jedi1, Jedi2, spermine) with no
  mechanical counterpart; 2 more pair with T50 (tension) rows rather than
  P50. P1 must define the same-fit row join before this demo can
  run at all; it stays a methods demo, and n forbids claims.
- Temperature is reported at 9%: no Q10 correction is attempted at v1;
  temperature is a listed covariate, flagged as missing data.

### 5.3 Track C — variant and compound atlas (P5)

- ΔP50 (16 records): curated effect-size table (variant → functional_effect →
  ΔP50 normalized), mapped to structural domains where the variant position
  falls inside a covered structure. No inferential statistics at this n.
- Compound × channel matrix (136 activities): pActivity heatmap, per-compound
  selectivity index (max off-target gap). Honest about sparsity; cells show
  "no data" rather than zeros.

### 5.4 Track D — field trends (P6)

Publications per year by family; which parameters the field measured over
time; assay-format and model-system drift. Descriptive counts only.

## 6. Statistical guardrails (all tracks)

- Thresholds and kinetics analyzed on log scale; summaries reported as
  geometric means with n and k.
- No pooling across stimulus modalities or assay formats.
- Low-n outputs stay descriptive; every table carries k/n.
- Multiple-comparison corrections only where formal tests are run (Track B
  heterogeneity contrasts); audit track runs no hypothesis tests at v1.
- Every number in every output traces to a census SQL or an analysis
  artifact committed with the release.

## 7. P0 decisions (settled 2026-11-05 — recorded in ADR-0005)

### 7.1 Tri-state field status

Per MIMIC field, per record: `REPORTED` / `NOT_REPORTED_IN_PAPER` /
`NOT_EXTRACTED`. Options:

| Option | Mechanism | Pros | Cons |
|---|---|---|---|
| (a) Curation columns | Vault extraction schema adds explicit status per field | Most rigorous; audit = pure query | Heavy curation burden; re-touch of legacy corpus |
| (b) Derived + subsample | NULL = ambiguous by default; estimate extraction sensitivity from a ~30-paper validation subsample, correct audit-wide | No re-curation; statistically explicit | Correction is an estimate, not per-record truth |
| (c) Hybrid (recommended) | (b) for the frozen corpus now; (a) for newly curated records going forward | Defensible v1; path to full rigor | Two mechanisms to document |

Recommendation: **(c)**. **Decision (2026-11-05): (c) Hybrid** — recorded
in ADR-0005 (`docs/adr/0005-mimic-tri-state-hybrid.md`) with the
`mimic_gaps` vault column and the ~30-paper validation-subsample protocol.

### 7.2 Applicability rules (final — ADR-0005)

- `stimulus_velocity`, `probe_geometry`, `probe_diameter_um`: applicable only
  when `stimulus_type` ∈ {INDENTATION, TOUCH, SHEAR_STRESS} (moving-probe
  stimuli; geometry only for INDENTATION).
- `pipette_solution`, `holding_potential_mv`: applicable only for
  pipette-based modes (CELL_ATTACHED, INSIDE_OUT, OUTSIDE_OUT, WHOLE_CELL,
  PERFORATED_PATCH, PLANAR_PATCH).
- `sampling_rate_khz`, `filter_khz`: applicable only to electrophysiological
  recording modes.
- `n` (replicates), `stimulus_type`, `recording_mode`, `bath_solution`:
  applicable always.

### 7.3 Unit policy (final — ADR-0005)

- P50: dual-report mmHg and kPa; log10 for analysis.
- T50: mN/m. X50: µm. Kinetics: ms (column-native). Conductance: pS.
- pActivity = −log10(activity_value [M]) for bioactivity.
- ΔP50 normalized to the record's own unit; relative shift also reported.

## 8. Delivery (P7)

- Site: new **Analysis** section (audit + atlas + trends pages) reading
  `site/_data/analysis/*.json`; channel cards gain the MIMIC badge. Track D
  (field trends) lands on the Analysis section's trends page.
- Figures: publication-grade set under `dist/analysis/<data-tag>/figures/`,
  regenerated in CI against the pinned artifact.
- Methods page on the site documenting every statistical choice in §5–§6.
- CI: analysis suite runs with the test suite; pins follow the
  real-data-fixture rule (cite vault source or census SQL — CLAUDE.md).

## 9. Build order

| Phase | Content | Depends on |
|---|---|---|
| P0 | tri-state ADR, applicability rules, unit policy | user decision (§7.1) |
| P1 | harmonization layer + tests | P0 |
| P2 | per-record scoring + field registry | P1 |
| P3 | Track A audit | P2 |
| P4 | Track B biophysics | P2 |
| P6 | Track D trends | P1 |
| P5 | Track C atlas | P2 |
| P7 | delivery (site, figures, methods, CI) | P3 + P4 + P5 |

## 10. Provenance

Scope approved by the project lead in a 2026-11-05 review session (all four
tracks; shared module; MIMIC naming canonical). Drafted with Claude Code
assistance; census numbers generated live against `db/maicdb.sqlite`
(`data-v1.0`) — see §3 SQL.

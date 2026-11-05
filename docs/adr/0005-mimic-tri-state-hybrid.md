# MIMIC audit tri-state: hybrid field status; audit units and applicability pinned

The MIMIC compliance audit (analytics spec `docs/analytics-pipeline-spec.md`
§5.1) must separate two meanings of an empty field: the paper did not
report it, or the curator did not extract it. Without that split the audit
measures the curation pipeline, not the field. The split is not academic:
replicate counts live in the legacy text column `n` (53% populated) while
`n_cells` reads 0% — a naive audit reads the wrong number either way
(spec §3). This ADR settles the P0 decision the spec left open (§7.1), and
finalizes the two policies §7.2–7.3 drafted: MIMIC applicability rules and
the audit unit policy. Decided by the project lead 2026-11-05.

## Considered Options

- **Hybrid: `mimic_gaps` column for new curation + validation subsample for
  the frozen corpus (chosen)** — one new vault extraction column records,
  per row, which applicable MIMIC fields the paper does not report; a
  ~30-paper validation subsample estimates extraction sensitivity for
  `data-v1.0` and corrects the audit-wide numbers statistically.
- **Curation status columns per field (19 columns)** — maximally rigorous,
  every record carries explicit REPORTED / NOT_REPORTED / NOT_EXTRACTED.
  Rejected as v1: it re-touches the frozen corpus (forcing a re-release for
  the audit's sake) and multiplies curator burden 19×.
- **Derived + subsample only, no schema change** — cheapest; NULL stays
  ambiguous forever and the audit can never improve without re-deriving the
  correction. Rejected: it fixes the number, not the cause.

## Consequences

**Tri-state semantics (normative).** Per MIMIC field, per record:

1. field value present → **REPORTED**
2. field listed in the row's `mimic_gaps` → **NOT_REPORTED_IN_PAPER**
   (curator checked the source and it is absent)
3. field empty and not listed → **NOT_EXTRACTED** (ambiguous; must shrink
   over time)

**Vault side (lands in the same PR pair as this ADR).**
`data/extraction_schema.md` gains the `mimic_gaps` column (Context/MIMIC
section) and a rule: listed fields must come from the 19-field MIMIC
vocabulary (vault schema-design §4.3); a field with a value must not be
listed. Per the vault's V.1 no-unwired-rules discipline, the PR declares
the enforcement gap explicitly: the validator check activates with the
first curation batch carrying the column — today there are no such rows, so
a check would be vacuous. `record/progres_record.md` carries the gap line.

**maicdb-code side (deferred by design).** The loader/schema gains a
nullable home for `mimic_gaps` (column or load-time JSON — P1 decides) with
the `data-v1.1` loader work; the audit module reads the tri-state through
the harmonization layer (spec §4), never directly from the vault.

**Validation subsample protocol (frozen corpus).** ~30 papers, stratified
random by channel family (12 channels / 7 families; oversample
single-paper families so none is unrepresented), drawn from the 184 papers
backing `biophysics_experiment`. Re-read methods sections against the
19-field MIMIC checklist; mark REPORTED fields; compare against the DB's
populated fields per record. Report extraction sensitivity (of fields the
paper reports, fraction extracted) and over-extraction rate, with exact
binomial CIs; publish the correction with the audit outputs (spec §5.1).
The subsample's raw marking sheet is itself a data artifact — versioned
and cited, not a throwaway.

**Applicability rules (final; spec §7.2 supersedes to match).**

- `stimulus_velocity`, `probe_geometry`, `probe_diameter_um`: applicable
  only when `stimulus_type` ∈ {INDENTATION, TOUCH, SHEAR_STRESS}; geometry
  pair only for INDENTATION.
- `pipette_solution`, `holding_potential_mv`: applicable only for
  pipette-based modes (CELL_ATTACHED, INSIDE_OUT, OUTSIDE_OUT, WHOLE_CELL,
  PERFORATED_PATCH, PLANAR_PATCH).
- `sampling_rate_khz`, `filter_khz`: applicable only to electrophysiological
  recording modes.
- `n` (replicates), `stimulus_type`, `recording_mode`, `bath_solution`:
  applicable always.
- Compliance score = populated ÷ **applicable** fields, unweighted;
  weighted variants are sensitivity analyses only (spec §5.1).

**Unit policy (final; spec §7.3 supersedes to match).** P50 dual-report
mmHg and kPa, log10 in analysis; T50 mN/m; X50 µm; kinetics ms
(column-native); conductance pS; pActivity = −log10(activity [M]);
ΔP50 normalized to the record's own unit with the relative shift also
reported. No Laplace pressure→tension conversion until probe geometry
exists (0% today — Track B defines the curation demand).

- Evidence base: `docs/analytics-pipeline-spec.md` §3 (census, with SQL),
  §5.1–5.2, §7; gate findings from PR #65 (the `n` split; the four-field
  100% failure pair); vault `report/MAICDB_Schema_Design.md` §4.3 (the
  19-field MIMIC vocabulary), §9 (enforcement deferral).

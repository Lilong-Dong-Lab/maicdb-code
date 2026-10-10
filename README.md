# MAIC-DB: Mechanically Activated Ion Channel Database

[![Status](https://img.shields.io/badge/Status-Active%20Development-green)]()
[![License](https://img.shields.io/badge/License-Academic%20Research-blue)]()

**[English](README.md) | [简体中文](README_CN.md)**

> A comprehensive, specialized database for mechanobiology research, filling the critical gap in bioinformatics infrastructure for mechanically activated ion channels (MAICs).

---

## Table of Contents

- [Background & Motivation](#background--motivation)
- [Project Goals](#project-goals)
- [The Problem We Solve](#the-problem-we-solve)
- [Target Channel Families](#target-channel-families)
- [Database Architecture](#database-architecture)
- [The MIMIC Standard](#the-mimic-standard)
- [Therapeutic Applications](#therapeutic-applications)
- [Repository Structure](#repository-structure)
- [Querying the Database](#querying-the-database)
- [Related Resources](#related-resources)
- [Contributing](#contributing)
- [References](#references)

---

## Background & Motivation

The 2021 Nobel Prize in Physiology or Medicine was awarded for the discovery of **PIEZO channels**, marking mechanotransduction research's entry into a golden age. The field now has exponentially growing literature revealing how cells sense and respond to mechanical forces.

However, valuable quantitative data remains fragmented across thousands of research papers, creating a "Tower of Babel" with heterogeneous units, protocols, and reporting standards.

**MAIC-DB** aims to solve this by creating a centralized, normalized resource that links gene identity through protein biophysics to cellular mechanics.

---

## Project Goals

### Primary Objective

Build a specialized database capturing **quantitative biophysical parameters** of mechanically activated ion channels that are missing from existing bioinformatics resources.

### Key Deliverables

| Goal | Description |
|------|-------------|
| **Data Normalization** | Normalize heterogeneous activation data across studies |
| **Knowledge Integration** | Link gene identity → protein biophysics → cellular mechanics |
| **Drug Discovery Support** | Provide structured data for mechano-therapeutics development |
| **Clinical Interpretation** | Support genetic variant interpretation in mechanosensitive genes |

---

## The Problem We Solve

### What Existing Databases Provide

| Resource | Provides |
|----------|----------|
| IUPHAR/BPS Guide to Pharmacology | Gene nomenclature, ligand data |
| UniProt | Protein sequences |
| PDB | 3D structures |
| Channelpedia | Electrophysiological data |
| MechanoBase | Tissue/cellular mechanical properties |

### What's Missing (MAIC-DB's Niche)

| Parameter | Description | Example |
|-----------|-------------|---------|
| **P50/T50/X50** | Pressure/tension/indentation for 50% activation | 30 mmHg, 5 mN/m |
| **τ_act, τ_inact** | Activation and inactivation time constants | 2 ms, 50 ms |
| **Conductance** | Single-channel conductance | 35 pS |
| **Stimulus Parameters** | Probe geometry, velocity, recording mode | Patch-clamp, cell-attached |
| **Pressure-Response Curves** | Full dose-response relationships | Boltzmann fit parameters |

### The "Missing Middle" in Bioinformatics

```
Gene Sequences  ────────►  Protein Function  ────────►  Cellular Mechanics
     ✓                          ✗                          ✓
                    ↑
              MAIC-DB fills this gap
```

---

## Target Channel Families

| Family | Key Proteins | Mechanism | Significance |
|--------|--------------|-----------|--------------|
| **PIEZO** | PIEZO1, PIEZO2 | Force-from-lipids | 2021 Nobel Prize; touch, proprioception, vascular development |
| **TRP** | TRPV4, TRPA1, NOMPC | Polymodal sensors | Pain, temperature, mechanosensation |
| **K2P** | TREK-1, TREK-2, TRAAK | Force-from-lipids | Neuroprotection, anesthesia targets |
| **OSCA/TMEM63** | OSCA1.1, TMEM63A/B | Force-from-lipids | Plant-animal conserved; osmosensing |
| **MscL/MscS** | Bacterial channels | Force-from-lipids | Biophysical "standard candles"; osmotic protection |
| **TMC1/2** | MET complex components | Force-from-filament | Hearing mechanotransduction |
| **DEG/ENaC/ASIC** | MEC-4, ENaC, ASICs | Force-from-filament | Touch, acid sensing, degenerins |

### Activation Mechanisms

- **Force-from-Lipids (FFL)**: Membrane tension directly gates the channel (PIEZO, MscL, K2P)
- **Force-from-Filament (FFF)**: Force transmitted via cytoskeleton/ECM tethers (TMC, NOMPC)
- **Hybrid Models**: Modulation by both lipids and cytoskeleton (TRPV4)

---

## Database Architecture

### Proposed Schema Modules

```
┌─────────────────────────────────────────────────────────────────┐
│                        MAIC-DB Schema                           │
├─────────────┬─────────────┬─────────────┬───────────────────────┤
│  IDENTITY   │  BIOPHYSICS │ PHARMACOLOGY│       DISEASE         │
├─────────────┼─────────────┼─────────────┼───────────────────────┤
│ Gene symbol │ P50/T50     │ Ligand name │ Mutation              │
│ UniProt ID  │ Slope (k)   │ Ligand type │ Phenotype             │
│ PDB links   │ τ_act       │ IC50/EC50   │ Functional effect     │
│ Aliases     │ τ_inact     │ Δ-P50       │ Clinical significance │
│ Tissue exp. │ Conductance │ References  │ References            │
│ References  │ I-V curve   │             │                       │
└─────────────┴─────────────┴─────────────┴───────────────────────┘
```

### Key Data Fields

#### Identity Module
- Gene symbol (HGNC), UniProt ID, PDB IDs
- Protein aliases, orthologs
- Tissue expression patterns
- Subcellular localization

#### Biophysics Module
- Activation threshold (P50, T50, X50)
- Hill slope / Boltzmann parameters
- Time constants (τ_act, τ_inact)
- Single-channel conductance
- Ion selectivity
- Voltage dependence (if any)

#### Pharmacology Module
- Activators and inhibitors
- Small molecule modulators
- Peptide toxins
- Concentration-response parameters

#### Disease Module
- Genetic variants (SNVs, indels)
- Associated phenotypes
- Functional assay results
- Clinical interpretation

---

## The MIMIC Standard

**Minimum Information about a Mechanically Induced Current (MIMIC)** — a proposed reporting standard for mechanobiology experiments.

### Required Metadata

| Category | Parameters |
|----------|------------|
| **Stimulus** | Type (pressure, stretch, indentation), velocity, probe geometry |
| **Recording** | Mode (cell-attached, inside-out, whole-cell), amplifier, filter settings |
| **Cell Context** | Cell type, species, passage number, heterologous expression system |
| **Environment** | Temperature, bath solution, pipette solution |
| **Analysis** | Threshold criteria, curve fitting method, n values |

### Why This Matters

Standardized metadata enables:
- Cross-study comparisons
- Meta-analyses
- Reproducibility assessment
- Data quality scoring

---

## Therapeutic Applications

MAIC-DB supports the development of **mechano-therapeutics**:

| Application | Target | Potential Impact |
|-------------|--------|------------------|
| **Pain Management** | Piezo2 inhibitor | Non-opioid relief for neuropathic pain |
| **Fibrosis/Cancer** | TRPV4/Piezo1 blockers | Halt disease progression |
| **Cardiovascular** | Piezo1 modulators | Hypertension, vascular disorders |
| **Hereditary Diseases** | Variant interpretation | Hereditary xerocytosis, lymphatic dysplasia |
| **Hearing Loss** | TMC1/2 variants | Genetic diagnosis, potential therapies |

---

## Repository Structure

```
maicdb-code/
├── src/
│   ├── data/              # Data models and schemas
│   ├── api/               # API endpoints (if applicable)
│   ├── parsers/           # Literature data extraction
│   ├── normalization/     # Unit conversion, standardization
│   └── utils/             # Utility functions
├── tests/                 # Test suite
├── data/
│   ├── raw/               # Raw extracted data
│   ├── processed/         # Normalized datasets
│   └── exports/           # Database exports (JSON, CSV, SQL)
├── docs/                  # Technical documentation
│   ├── schema.md          # Database schema documentation
│   ├── api.md             # API documentation
│   └── contributing.md    # Contribution guidelines
├── scripts/               # Utility scripts
├── pyproject.toml         # Project configuration
└── README.md              # This file
```

---

## Querying the Database

The `maicdb.query` library (`src/maicdb/query.py`) provides read-only,
deterministic queries over the published artifact `db/maicdb.sqlite`
(schema 0.2.0 · 1100 rows · CC-BY-4.0). The `maicdb-query` CLI is its first
consumer; the website/API layers to come will wrap the same library.

```bash
# Channel card: identity + P50 rows with per-row provenance
# (PYTHONPATH=src works around the known venv .pth hidden-flag quirk —
#  see KNOWN-QUIRKS.md; a wheel install works without it)
PYTHONPATH=src uv run maicdb-query channel PIEZO1 --parameter p50
```

```text
PIEZO1 — Homo sapiens (family PIEZO)
UniProt: Q92508
ortholog group: PIEZO1
NOTE: PIEZO1/PIEZO2 rows are frozen-layer data whose evidence quotes have not been re-verified; verification percentages cover the 10 non-frozen layers only.

p50 — P50 pressure threshold (56 rows)
    sign convention: values are as recorded (negative P50 = suction; K2P layers all-negative); no |value| pooling is performed (data notes §6.1)
  PIEZO1-EX-00005  -28.0 mmHg  (as reported: -28.0 mm Hg)  confidence=high  n=21
    quote: The current-pressure relationship is characterized by maximal opening at -60 mm Hg, with a pressure for half-maximal activation (P50) of -28.0 ± 1.8 mm Hg (Fig. 1F).
    location: Results (Fig. 1F)
    extractor_note: N2A 内源性 stretch-activated 电流的 P50（Piezo1 克隆前）；后续 Fig. 2 siRNA 敲低 Piezo1 将该内源性电流归因 Piezo1，故作为 PIEZO1 相关 own-data 入行。error_type 未在正文/图注声明（Fig. 1 系列图注惯例 mean±SEM），留空。maximal opening at −60 mm Hg 为刺激值记入 ctx。
    condition_key: endogenous-N2A_cell-attached_suction_Boltzmann-P50_-80mV_Fig1F
… (55 more rows; absent evidence fields print "…: (not recorded)" instead of being omitted)
```

```bash
# Per-gene cross-comparison export (the numbers behind the A1 panels)
PYTHONPATH=src uv run maicdb-query export --parameter tau_inact --format csv > out.csv
```

```csv
gene,family,parameter,unit,count,min,median,max,measurement_ids,note
ASIC,DEG_ENaC_ASIC,tau_inact,ms,14,48.0,520.0,3160.0,ASIC-00012;ASIC-00016;ASIC-00004;ASIC-00006;ASIC-00110;ASIC-00111;ASIC-00112;ASIC-00048;ASIC-00046;ASIC-00047;ASIC-00034;ASIC-00087;ASIC-00033;ASIC-00086,
MscL,MSCL_MSCS,tau_inact,ms,1,1890.0,1890.0,1890.0,MSCL-EX-00015,
MscS,MSCL_MSCS,tau_inact,ms,3,250.0,2000.0,2800.0,MSCS-EX-00049;MSCS-EX-00061;MSCS-EX-00048,
OSCA,OSCA_TMEM63,tau_inact,ms,12,10.0,46.3,427.0,OSCA-EX-00002;OSCA-EX-00004;OSCA-EX-00081;OSCA-EX-00006;OSCA-EX-00010;OSCA-EX-00079;OSCA-EX-00014;OSCA-EX-00018;OSCA-EX-00043;OSCA-EX-00021;OSCA-EX-00024;OSCA-EX-00027,
… (9 more rows, incl. zero-count genes reported with count=0)
```

The trailing `note` column is empty except on rows carrying a caliber
rider — e.g. direction-blind ratio parameters, whose median is omitted
with the reason stated in that column.

`PYTHONPATH=src uv run maicdb-query provenance PIEZO1-EX-00005` prints a
measurement's full evidence row. Semantics, all enforced by tests:

- **Read-only** — the DB opens via the SQLite `mode=ro` URI; the query test
  suite leaves the artifact's SHA-256 unchanged.
- **Per-unit aggregation** — count/min/median/max group by stored unit
  (mmHg/psi, dyn/cm·mN/m, nm/um coexist by design); modalities are never
  pooled or inter-converted. Rows whose stored unit is NULL — and unit-less
  parameters such as `ion_selectivity_ratio` — aggregate under an empty
  unit, reported like any other bucket. Direction-blind ratio parameters
  (`ion_selectivity_ratio`, `ca_permeability`; `ratio_direction` NULL this
  load) report count/min/max with the median omitted — cross-direction
  medians are meaningless (A1 panel p4 semantics). Genes with zero rows for
  a parameter are reported (`count=0`), never hidden. The table aggregates
  normalized columns; as-recorded value/unit strings stay per-row in
  channel cards and `provenance`. Threshold values keep their as-recorded
  signs (disclosed; no |value| pooling). A gene symbol spanning multiple
  organisms (schema-supported) raises a clean `AmbiguousGeneError` instead
  of pooling or picking one silently.
- **Evidence chain everywhere** — every printed number carries its
  `measurement_id`, verbatim quote, location, confidence and extractor note;
  every aggregate row lists its `measurement_ids` (`;`-joined in CSV), one
  step from the quotes via `provenance`.
- **Frozen-layer wording** — outputs touching PIEZO1/PIEZO2 attach the §6.7
  boilerplate on every path — channel cards, each PIEZO comparison row
  (counted or zero), `provenance`, and the export document (CSV: stderr, so
  the data stream stays pure; JSON: a field) — and never render an
  affirmative verification status.
- **Determinism** — same input, byte-identical stdout; no timestamps.

Library consumers use the same functions directly:

```python
from maicdb.query import channel_card, export, open_readonly

engine = open_readonly("db/maicdb.sqlite")
card = channel_card(engine, "PIEZO1", parameters=["p50"])
csv_text = export(engine, "tau_inact", format="csv")
```

---

## Related Resources

| Resource | Location | Purpose |
|----------|----------|---------|
| **Research Vault** | `~/Documents/.../Project_DataBase_MAICDB` | Literature curation, knowledge synthesis |
| **Master Summary** | `mechanically_activated_ion_channels_summary.md` | Consolidated channel knowledge |
| **Progress Log** | `record/progres_record.md` | Project tracking |

### External Databases

- [IUPHAR/BPS Guide to Pharmacology](https://www.gtopdb.org/)
- [UniProt](https://www.uniprot.org/)
- [PDB](https://www.rcsb.org/)
- [Channelpedia](https://channelpedia.epfl.ch/)
- [AlphaFold DB](https://alphafold.ebi.ac.uk/)

---

## Contributing

*(To be developed)*

Contributions welcome in:
- Literature data extraction
- Schema design feedback
- Code development
- Documentation improvements

---

## References

### Key Literature

1. Kefauver, J.M., Ward, A.B. & Patapoutian, A. Discoveries in structure and physiology of mechanically activated ion channels. *Nature* **587**, 567–576 (2020). https://doi.org/10.1038/s41586-020-2933-1

2. Xiao, B. Mechanisms of mechanotransduction and physiological roles of PIEZO channels. *Nat Rev Mol Cell Biol* **25**, 886–903 (2024). https://doi.org/10.1038/s41580-024-00773-5

---

## License

This project is provided for academic research purposes in mechanobiology and related fields.

---

**Project Status**: Active Development | **Created**: 2026-03-08

## Releases

### v1.0.0-data (2026-09-02)

The first published database: schema v0.2 loaded from the vault's frozen
`data-v1.0` corpus (1100 curated measurement rows across 12 mechanically
activated ion channel families, 205+6 publications, full per-row evidence
chain, CC-BY-4.0). Artifacts in [`db/`](db/) — `maicdb.sqlite`,
byte-stable `maicdb.sql`, `load-manifest.json`. Regeneration, provenance and
every mapping decision: [`db/README.md`](db/README.md) and
[`docs/loader-mapping.md`](docs/loader-mapping.md).

**Project Status**: v1.0 data published | active development (query tooling next)

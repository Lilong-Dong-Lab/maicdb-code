# MAIC-DB: Mechanically Activated Ion Channel Database

[![Status](https://img.shields.io/badge/Status-Active%20Development-green)]()
[![License](https://img.shields.io/badge/License-Academic%20Research-blue)]()

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

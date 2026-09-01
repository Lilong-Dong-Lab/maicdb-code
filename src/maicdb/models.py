"""SQLAlchemy 2.0 ORM models for MAIC-DB.

The schema refines the documented four conceptual modules
(Identity / Biophysics / Pharmacology / Disease) into **six core tables plus
two support tables**:

* Identity      → :class:`Channel` (+ :class:`Structure` promoted to its own table)
* Biophysics    → :class:`BiophysicsExperiment` (the Mechano-Gating Card + MIMIC)
* Pharmacology  → :class:`Compound` + :class:`Bioactivity` (the compound↔channel M:N
                  junction with attributes)
* Disease       → :class:`Variant`
* support       → :class:`ExternalReference` (polymorphic external IDs) and
                  :class:`Publication` (normalized citations)

Every fact table carries:

* a surrogate integer ``id`` (primary key),
* a stable FAIR ``maicdb_id`` accession,
* a provenance stub (``source_db``, ``collected_date``, ``publication_id``),
* ``created_at`` / ``updated_at`` timestamps.

Design notes (see ``report/MAICDB_Schema_Design.md`` for full rationale):

* MIMIC stimulus/recording metadata is **embedded** on
  :class:`BiophysicsExperiment` (1:1 with the experiment; the "Mechano-Gating
  Card" is the database's most-queried row and should be one query away).
* Cross-references use a **hybrid** scheme: canonical accessions
  (``uniprot_accession``, ``pdb_id``, ``inchikey``, ``clinvar_accession``) live
  as indexed columns on the parent table for O(1) lookup; the long tail goes in
  the polymorphic :class:`ExternalReference` table so new source DBs never
  require a migration.
* Thresholds (P50/T50/X50) use **value + unit pairs** because units vary across
  labs (mmHg, kPa, mN/m, …); kinetics (τ) and conductance use fixed units
  baked into the column name.
* The Biophysics and Disease tables are **fully nullable** — empty-but-ready at
  launch, since the reference Piezo1 dataset contains no such data yet.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from maicdb.enums import (
    ActivationMechanism,
    ActivityType,
    AssayFormat,
    ClinvarSignificance,
    CompoundType,
    EntityType,
    Family,
    FunctionalEffect,
    IVRelation,
    IndentationUnit,
    ParameterSet,
    PressureUnit,
    RecordingMode,
    SourceDb,
    StimulusType,
    StructureSource,
    TensionUnit,
    VariantType,
    name_stored_enum,
    value_stored_enum,
)

__all__ = [
    "Channel",
    "Structure",
    "BiophysicsExperiment",
    "Compound",
    "Bioactivity",
    "Variant",
    "ExternalReference",
    "Publication",
]


class Base(DeclarativeBase):
    """Declarative base for all MAIC-DB models.

    Defined here (rather than in :mod:`maicdb.database`) so that simply
    importing :mod:`maicdb.models` registers every table on the metadata.
    :mod:`maicdb.database` re-exports it for convenience.
    """


# --------------------------------------------------------------------------- #
# Support: publications (normalized citations, shared across fact rows)
# --------------------------------------------------------------------------- #
class Publication(Base):
    """A normalized scientific citation, referenced by every fact table.

    Deduplicates DOIs/PMIDs that repeat across many rows (e.g. the 8 primary
    citations shared across the 12 mouse Piezo1 structures).
    """

    __tablename__ = "publication"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doi: Mapped[str | None] = mapped_column(Text, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(Text)
    journal: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    authors: Mapped[list[str] | None] = mapped_column(JSON)  # ["Guo YR", …]
    pmid: Mapped[int | None] = mapped_column(Integer, index=True)
    citation_text: Mapped[str | None] = mapped_column(Text)  # preformatted

    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Publication id={self.id} doi={self.doi!r}>"


# --------------------------------------------------------------------------- #
# Identity module
# --------------------------------------------------------------------------- #
class Channel(Base):
    """One row per (gene, organism). The central hub of the schema.

    The ``UNIQUE(gene_symbol, organism_taxid)`` constraint forces channels that
    the source data collapses across organisms (e.g. Piezo1 with both a human
    and a mouse ChEMBL target ID) into separate rows, joined by
    ``ortholog_group``.
    """

    __tablename__ = "channel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    maicdb_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    gene_symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    gene_aliases: Mapped[list[str] | None] = mapped_column(JSON)  # ["FAM38A", "Mib"]

    # Canonical external accessions (kept as columns for O(1) lookup)
    uniprot_accession: Mapped[str | None] = mapped_column(
        String(16), unique=True, index=True
    )
    protein_name: Mapped[str | None] = mapped_column(Text)

    # Organism kept as free text + NCBI taxid for interoperability
    organism: Mapped[str] = mapped_column(Text, nullable=False)
    organism_taxid: Mapped[int | None] = mapped_column(Integer, index=True)
    ncbi_gene_id: Mapped[int | None] = mapped_column(Integer, index=True)
    hgnc_id: Mapped[str | None] = mapped_column(String(32))

    sequence_length: Mapped[int | None] = mapped_column(Integer)  # amino acids

    # Taxonomy / function
    family: Mapped[Family] = mapped_column(name_stored_enum(Family), nullable=False, index=True)
    activation_mechanism: Mapped[ActivationMechanism | None] = mapped_column(name_stored_enum(ActivationMechanism), index=True)
    go_terms: Mapped[list[str] | None] = mapped_column(JSON)  # ["GO:0050982", …]
    ortholog_group: Mapped[str | None] = mapped_column(
        String(64), index=True
    )  # e.g. "PIEZO1" links human/mouse/rat orthologs
    summary: Mapped[str | None] = mapped_column(Text)

    # Provenance stub
    source_db: Mapped[SourceDb | None] = mapped_column(name_stored_enum(SourceDb), index=True)
    collected_date: Mapped[date | None] = mapped_column(Date)
    publication_id: Mapped[int | None] = mapped_column(
        ForeignKey("publication.id", ondelete="SET NULL")
    )

    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[str | None] = mapped_column(DateTime)

    # Relationships
    structures: Mapped[list[Structure]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
    biophysics_experiments: Mapped[list[BiophysicsExperiment]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
    bioactivities: Mapped[list[Bioactivity]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
    variants: Mapped[list[Variant]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
    primary_publication: Mapped[Publication | None] = relationship()

    __table_args__ = (
        # A channel is unique per gene + species.
        UniqueConstraint(
            "gene_symbol", "organism_taxid", name="uq_channel_gene_organism"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Channel maicdb_id={self.maicdb_id!r} gene={self.gene_symbol!r} "
            f"organism={self.organism!r}>"
        )


class Structure(Base):
    """One row per experimental or predicted 3D structure (PDB / AlphaFold).

    Several columns (``residues_covered``, ``coverage_pct``, ``deposition_date``,
    ``doi``) are empty in the reference Piezo1 CSV but populated in the prose
    README; they are nullable here so a future extraction pass can fill them
    without a migration. ``conformational_state``, ``auxiliary_subunits``, and
    ``mutation`` are likewise parsed-from-prose targets.
    """

    __tablename__ = "structure"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    maicdb_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channel.id", ondelete="CASCADE"), nullable=False, index=True
    )

    pdb_id: Mapped[str | None] = mapped_column(String(8), unique=True, index=True)
    structure_source: Mapped[StructureSource] = mapped_column(name_stored_enum(StructureSource), nullable=False, index=True)
    alphafold_model_id: Mapped[str | None] = mapped_column(
        String(64)
    )  # e.g. "AF-Q92508-F1-model_v6"
    alphafold_plddt_mean: Mapped[float | None] = mapped_column(Float)

    title: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(Text)  # PDB free text, e.g. "E, M"
    resolution_a: Mapped[float | None] = mapped_column(Float)  # Å; null for predicted
    organism: Mapped[str | None] = mapped_column(Text)  # may differ for homology models

    # Fields currently empty in the Piezo1 CSV but populated in prose README
    residues_covered: Mapped[str | None] = mapped_column(Text)  # "1-2547"
    coverage_pct: Mapped[float | None] = mapped_column(Float)
    num_chains: Mapped[int | None] = mapped_column(Integer)
    ligands: Mapped[str | None] = mapped_column(Text)  # co-crystallized ligands
    has_inhibitor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Fields currently trapped in README prose / structure titles
    auxiliary_subunits: Mapped[list[str] | None] = mapped_column(JSON)  # ["MDFIC"]
    mutation: Mapped[str | None] = mapped_column(Text)  # "A1988V", "E756del"
    conformational_state: Mapped[str | None] = mapped_column(
        Text, index=True
    )  # resting/curved, flattened, intermediate, open, …

    deposition_date: Mapped[date | None] = mapped_column(Date)
    release_date: Mapped[date | None] = mapped_column(Date)
    doi: Mapped[str | None] = mapped_column(Text, index=True)

    # Provenance stub
    source_db: Mapped[SourceDb | None] = mapped_column(name_stored_enum(SourceDb), index=True)
    collected_date: Mapped[date | None] = mapped_column(Date)
    publication_id: Mapped[int | None] = mapped_column(
        ForeignKey("publication.id", ondelete="SET NULL")
    )

    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[str | None] = mapped_column(DateTime)

    # Relationships
    channel: Mapped[Channel] = relationship(back_populates="structures")
    biophysics_experiments: Mapped[list[BiophysicsExperiment]] = relationship(
        back_populates="structure"
    )
    publication: Mapped[Publication | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Structure maicdb_id={self.maicdb_id!r} pdb_id={self.pdb_id!r}>"


# --------------------------------------------------------------------------- #
# Biophysics module — the Mechano-Gating Card + MIMIC metadata
# --------------------------------------------------------------------------- #
class BiophysicsExperiment(Base):
    """A single mechano-gating measurement with full MIMIC context.

    This is the database's **unique selling point**: a self-describing gating
    card. **All card and MIMIC columns are nullable** so the table is
    empty-but-ready at launch (the reference Piezo1 dataset has no such data).

    * Thresholds P50/T50/X50 use value + unit pairs (units vary across labs).
    * Kinetics (τ) and conductance use fixed units baked into the column name.
    * ``compound_id`` optionally bridges to Pharmacology for Δ-P50 experiments.
    * ``structure_id`` optionally links a measurement to a conformational state.
    """

    __tablename__ = "biophysics_experiment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    maicdb_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channel.id", ondelete="CASCADE"), nullable=False, index=True
    )
    structure_id: Mapped[int | None] = mapped_column(
        ForeignKey("structure.id", ondelete="SET NULL"), index=True
    )
    compound_id: Mapped[int | None] = mapped_column(
        ForeignKey("compound.id", ondelete="SET NULL"), index=True
    )  # set for Δ-P50 (ligand-induced threshold shift) experiments

    experiment_label: Mapped[str | None] = mapped_column(Text)
    parameter_set: Mapped[ParameterSet | None] = mapped_column(name_stored_enum(ParameterSet), index=True)

    # ---- Mechano-Gating Card: thresholds (value + unit pairs) ----
    p50_value: Mapped[float | None] = mapped_column(Float)
    p50_unit: Mapped[PressureUnit | None] = mapped_column(value_stored_enum(PressureUnit))
    t50_value: Mapped[float | None] = mapped_column(Float)
    t50_unit: Mapped[TensionUnit | None] = mapped_column(value_stored_enum(TensionUnit))
    x50_value: Mapped[float | None] = mapped_column(Float)
    x50_unit: Mapped[IndentationUnit | None] = mapped_column(
        value_stored_enum(IndentationUnit)
    )

    slope: Mapped[float | None] = mapped_column(Float)  # Boltzmann/Hill slope
    slope_unit: Mapped[str | None] = mapped_column(Text)  # unitless default

    # ---- Mechano-Gating Card: kinetics (fixed units in column name) ----
    tau_act_ms: Mapped[float | None] = mapped_column(Float)
    tau_inact_ms: Mapped[float | None] = mapped_column(Float)
    tau_deact_ms: Mapped[float | None] = mapped_column(Float)

    # ---- Mechano-Gating Card: conductance & I-V ----
    conductance_ps: Mapped[float | None] = mapped_column(Float)  # single-channel, pS
    reversal_potential_mv: Mapped[float | None] = mapped_column(Float)
    iv_relation: Mapped[IVRelation | None] = mapped_column(name_stored_enum(IVRelation), index=True)

    # ---- Δ-P50 (populated for ligand- or variant-induced threshold shifts) ----
    delta_p50_value: Mapped[float | None] = mapped_column(Float)
    delta_p50_unit: Mapped[PressureUnit | None] = mapped_column(
        value_stored_enum(PressureUnit)
    )

    # ---- MIMIC metadata (embedded; 1:1 with the experiment) ----
    stimulus_type: Mapped[StimulusType | None] = mapped_column(name_stored_enum(StimulusType), index=True)
    stimulus_waveform: Mapped[str | None] = mapped_column(Text)  # step/ramp/train/…
    stimulus_velocity: Mapped[float | None] = mapped_column(Float)
    stimulus_velocity_unit: Mapped[str | None] = mapped_column(Text)  # e.g. "mm/s"
    stimulus_duration_ms: Mapped[float | None] = mapped_column(Float)
    probe_geometry: Mapped[str | None] = mapped_column(Text)  # free text
    probe_diameter_um: Mapped[float | None] = mapped_column(Float)
    recording_mode: Mapped[RecordingMode | None] = mapped_column(name_stored_enum(RecordingMode), index=True)
    expression_system: Mapped[str | None] = mapped_column(Text)  # "HEK293T transient"
    cell_type: Mapped[str | None] = mapped_column(Text)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    ph: Mapped[float | None] = mapped_column(Float)
    bath_solution: Mapped[str | None] = mapped_column(Text)
    pipette_solution: Mapped[str | None] = mapped_column(Text)
    holding_potential_mv: Mapped[float | None] = mapped_column(Float)
    sampling_rate_khz: Mapped[float | None] = mapped_column(Float)
    filter_khz: Mapped[float | None] = mapped_column(Float)
    n_cells: Mapped[int | None] = mapped_column(Integer)
    analysis_method: Mapped[str | None] = mapped_column(Text)
    protocol_ref: Mapped[str | None] = mapped_column(Text)  # protocol DOI/ID

    # ---- Provenance stub ----
    source_db: Mapped[SourceDb | None] = mapped_column(name_stored_enum(SourceDb), index=True)
    collected_date: Mapped[date | None] = mapped_column(Date)
    publication_id: Mapped[int | None] = mapped_column(
        ForeignKey("publication.id", ondelete="SET NULL")
    )

    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[str | None] = mapped_column(DateTime)

    # Relationships
    channel: Mapped[Channel] = relationship(back_populates="biophysics_experiments")
    structure: Mapped[Structure | None] = relationship(back_populates="biophysics_experiments")
    compound: Mapped[Compound | None] = relationship(back_populates="biophysics_experiments")
    publication: Mapped[Publication | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BiophysicsExperiment maicdb_id={self.maicdb_id!r}>"


# --------------------------------------------------------------------------- #
# Pharmacology module
# --------------------------------------------------------------------------- #
class Compound(Base):
    """A chemical modulator (small molecule or peptide).

    ``inchikey`` is the structural dedup key. ``compound_type`` is normalized
    from the raw source vocabulary (``"inhibitor/blocker"``→``INHIBITOR_BLOCKER``,
    ``"ChEMBL-only"``→``UNCLASSIFIED``). ``Best_Activity_*`` values from the raw
    compounds CSV are NOT stored here — they are derived from :class:`Bioactivity`.
    """

    __tablename__ = "compound"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    maicdb_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    # Canonical external accessions
    chembl_id: Mapped[str | None] = mapped_column(String(32), index=True)
    pubchem_cid: Mapped[int | None] = mapped_column(Integer, index=True)
    bindingdb_id: Mapped[str | None] = mapped_column(String(32))

    # Structural identifiers / descriptors
    smiles: Mapped[str | None] = mapped_column(Text)
    inchikey: Mapped[str | None] = mapped_column(String(27), unique=True, index=True)
    inchi: Mapped[str | None] = mapped_column(Text)

    # Physicochemical properties
    molecular_weight: Mapped[float | None] = mapped_column(Float)
    clogp: Mapped[float | None] = mapped_column(Float)
    tpsa: Mapped[float | None] = mapped_column(Float)
    hbd: Mapped[int | None] = mapped_column(Integer)
    hba: Mapped[int | None] = mapped_column(Integer)
    rotatable_bonds: Mapped[int | None] = mapped_column(Integer)
    aromatic_rings: Mapped[int | None] = mapped_column(Integer)
    heavy_atoms: Mapped[int | None] = mapped_column(Integer)

    # Classification / drug-likeness
    compound_type: Mapped[CompoundType | None] = mapped_column(name_stored_enum(CompoundType), index=True)
    source: Mapped[str | None] = mapped_column(Text)  # PubChem / ChEMBL / literature
    lipinski_pass: Mapped[bool | None] = mapped_column(Boolean)
    veber_pass: Mapped[bool | None] = mapped_column(Boolean)
    is_duplicate: Mapped[bool | None] = mapped_column(Boolean)

    # Peptide / natural-product context
    natural_source: Mapped[str | None] = mapped_column(Text)  # e.g. "Grammostola rosea venom"
    peptide_sequence: Mapped[str | None] = mapped_column(Text)

    # Provenance stub
    source_db: Mapped[SourceDb | None] = mapped_column(name_stored_enum(SourceDb), index=True)
    collected_date: Mapped[date | None] = mapped_column(Date)
    publication_id: Mapped[int | None] = mapped_column(
        ForeignKey("publication.id", ondelete="SET NULL")
    )

    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[str | None] = mapped_column(DateTime)

    # Relationships
    bioactivities: Mapped[list[Bioactivity]] = relationship(
        back_populates="compound", cascade="all, delete-orphan"
    )
    biophysics_experiments: Mapped[list[BiophysicsExperiment]] = relationship(
        back_populates="compound"
    )
    publication: Mapped[Publication | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Compound maicdb_id={self.maicdb_id!r} name={self.name!r}>"


class Bioactivity(Base):
    """A compound↔channel measurement with attributes (the M:N junction).

    ``assay_description`` is kept verbatim AND parsed into ``assay_format``,
    ``cell_line``, and ``target_species`` (the parsing itself happens in the
    loader; the schema provides the target columns).
    """

    __tablename__ = "bioactivity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    maicdb_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    compound_id: Mapped[int] = mapped_column(
        ForeignKey("compound.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channel.id", ondelete="CASCADE"), nullable=False, index=True
    )

    target_chembl_id: Mapped[str | None] = mapped_column(
        String(32)
    )  # raw ChEMBL target id kept verbatim
    activity_type: Mapped[ActivityType | None] = mapped_column(name_stored_enum(ActivityType), index=True)
    activity_value: Mapped[float | None] = mapped_column(Float)
    activity_units: Mapped[str | None] = mapped_column(Text)  # "nM"
    pchembl: Mapped[float | None] = mapped_column(Float)
    relation: Mapped[str | None] = mapped_column(String(4))  # "=", "<", ">"

    assay_description: Mapped[str | None] = mapped_column(Text)  # verbatim free text
    assay_format: Mapped[AssayFormat | None] = mapped_column(name_stored_enum(AssayFormat), index=True)  # parsed
    cell_line: Mapped[str | None] = mapped_column(Text)  # parsed, e.g. "HEK293T"
    target_species: Mapped[str | None] = mapped_column(Text)  # parsed, e.g. "Homo sapiens"

    # Provenance stub
    source_db: Mapped[SourceDb | None] = mapped_column(name_stored_enum(SourceDb), index=True)
    collected_date: Mapped[date | None] = mapped_column(Date)
    publication_id: Mapped[int | None] = mapped_column(
        ForeignKey("publication.id", ondelete="SET NULL")
    )

    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[str | None] = mapped_column(DateTime)

    # Relationships
    compound: Mapped[Compound] = relationship(back_populates="bioactivities")
    channel: Mapped[Channel] = relationship(back_populates="bioactivities")
    publication: Mapped[Publication | None] = relationship()

    __table_args__ = (
        # Soft dedup target absorbing the compounds-CSV "Duplicate" semantics.
        # SQLite allows multiple NULLs in a UNIQUE index, so partial populations
        # do not collide.
        UniqueConstraint(
            "compound_id",
            "channel_id",
            "activity_type",
            "activity_value",
            "assay_description",
            name="uq_bioactivity_dedup",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Bioactivity maicdb_id={self.maicdb_id!r} "
            f"activity={self.activity_type!r}={self.activity_value!r}>"
        )


# --------------------------------------------------------------------------- #
# Disease module
# --------------------------------------------------------------------------- #
class Variant(Base):
    """A channel sequence variant with phenotype and functional effect.

    Empty-but-ready at launch. Mirrors the Δ-P50 pattern via
    ``delta_p50_*`` columns for variant-induced threshold shifts.
    """

    __tablename__ = "variant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    maicdb_id: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channel.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Genomic / protein coordinates
    hgvs_protein: Mapped[str | None] = mapped_column(Text)  # "p.Ala1988Val"
    hgvs_coding: Mapped[str | None] = mapped_column(Text)  # "c.5963C>T"
    mutation_short: Mapped[str | None] = mapped_column(String(32), index=True)  # "A1988V"
    position: Mapped[int | None] = mapped_column(Integer)
    ref_aa: Mapped[str | None] = mapped_column(String(8))
    alt_aa: Mapped[str | None] = mapped_column(String(8))
    variant_type: Mapped[VariantType | None] = mapped_column(name_stored_enum(VariantType), index=True)

    organism: Mapped[str | None] = mapped_column(Text)
    organism_taxid: Mapped[int | None] = mapped_column(Integer, index=True)

    # Clinical cross-references
    clinvar_accession: Mapped[str | None] = mapped_column(String(32), index=True)
    clinvar_significance: Mapped[ClinvarSignificance | None] = mapped_column(name_stored_enum(ClinvarSignificance), index=True)
    omim_id: Mapped[str | None] = mapped_column(String(16))
    dbsnp_rs: Mapped[str | None] = mapped_column(String(16), index=True)

    # Phenotype / function
    phenotype: Mapped[str | None] = mapped_column(Text)  # "Hereditary xerocytosis"
    phenotype_mim: Mapped[str | None] = mapped_column(String(16))
    functional_effect: Mapped[FunctionalEffect | None] = mapped_column(name_stored_enum(FunctionalEffect), index=True)

    # Variant-induced threshold shift (parallel to compound Δ-P50)
    delta_p50_value: Mapped[float | None] = mapped_column(Float)
    delta_p50_unit: Mapped[PressureUnit | None] = mapped_column(
        value_stored_enum(PressureUnit)
    )

    notes: Mapped[str | None] = mapped_column(Text)

    # Provenance stub
    source_db: Mapped[SourceDb | None] = mapped_column(name_stored_enum(SourceDb), index=True)
    collected_date: Mapped[date | None] = mapped_column(Date)
    publication_id: Mapped[int | None] = mapped_column(
        ForeignKey("publication.id", ondelete="SET NULL")
    )

    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[str | None] = mapped_column(DateTime)

    # Relationships
    channel: Mapped[Channel] = relationship(back_populates="variants")
    publication: Mapped[Publication | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Variant maicdb_id={self.maicdb_id!r} "
            f"mutation={self.mutation_short!r} effect={self.functional_effect!r}>"
        )


# --------------------------------------------------------------------------- #
# Support: polymorphic external references (the cross-reference long tail)
# --------------------------------------------------------------------------- #
class ExternalReference(Base):
    """An external-database identifier attached to any core entity.

    Polymorphic by (``entity_type``, ``entity_id``). SQLite cannot enforce a
    polymorphic foreign key, so the link is validated at the ORM/application
    layer; this keeps the schema extensible — adding a new source database never
    requires altering a parent table.

    Use the canonical-accession columns on parent tables for the handful of IDs
    that *are* an entity's identity; use this table for everything else.
    """

    __tablename__ = "external_reference"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[EntityType] = mapped_column(name_stored_enum(EntityType), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_db: Mapped[SourceDb] = mapped_column(name_stored_enum(SourceDb), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "source_db",
            "external_id",
            name="uq_xref_entity_source_id",
        ),
        # Fast "all xrefs of entity X".
        Index("ix_xref_entity", "entity_type", "entity_id"),
        # Fast reverse lookup "which MAIC entity maps to this external ID".
        Index("ix_xref_reverse", "source_db", "external_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ExternalReference {self.entity_type.value}:{self.entity_id} "
            f"{self.source_db.value}={self.external_id!r}>"
        )


# --------------------------------------------------------------------------- #
# Convenience collection for tooling / tests
# --------------------------------------------------------------------------- #
CORE_TABLES = (
    Channel,
    Structure,
    BiophysicsExperiment,
    Compound,
    Bioactivity,
    Variant,
)
ALL_TABLES = (
    Channel,
    Structure,
    BiophysicsExperiment,
    Compound,
    Bioactivity,
    Variant,
    ExternalReference,
    Publication,
)

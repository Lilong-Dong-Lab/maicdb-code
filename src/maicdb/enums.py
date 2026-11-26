"""Controlled vocabularies for MAIC-DB.

Every vocabulary is a :class:`enum.Enum`. When mapped to SQLite via
``sqlalchemy.Enum`` (re-exported here as :data:`SQLEnum`), each member is stored
as a ``VARCHAR`` plus an auto-generated ``CHECK`` constraint, giving both
human-readability and DB-level validation.

Two storage conventions are used (resolved in :mod:`maicdb.models`):

* **Name-stored enums** (default) — ``Family``, ``CompoundType``, ``ActivityType``,
  ``FunctionalEffect``, … store the *member name* (e.g. ``"INHIBITOR_BLOCKER"``).
  These are the taxonomic vocabularies; names are stable identifiers.
* **Value-stored enums** — the three *unit* enums (``PressureUnit``,
  ``TensionUnit``, ``IndentationUnit``) store the *member value* (e.g. ``"mmHg"``)
  via ``values_callable`` so the physical unit appears verbatim in the database.

Fields intentionally left as free-text rather than enums (too early-stage or
open-ended): ``organism`` (use ``organism_taxid`` for interoperability),
``method``, ``phenotype``, ``bath_solution``/``pipette_solution``,
``probe_geometry``, ``expression_system``, ``cell_type``, ``conformational_state``
(enum-ish with a documented value list but a free-text fallback).
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy import Enum as SQLEnum

__all__ = [
    "SQLEnum",
    "name_stored_enum",
    "value_stored_enum",
    "Family",
    "ActivationMechanism",
    "CompoundType",
    "ActivityType",
    "AssayFormat",
    "StimulusType",
    "RecordingMode",
    "PressureUnit",
    "TensionUnit",
    "IndentationUnit",
    "IVRelation",
    "VariantType",
    "ClinvarSignificance",
    "FunctionalEffect",
    "SourceDb",
    "EntityType",
    "StructureSource",
    "ParameterSet",
]


def name_stored_enum(enum_cls: type[Enum]) -> SQLEnum:
    """Return a SQLAlchemy ``Enum`` storing the member *name* with a CHECK constraint.

    Used for the taxonomic vocabularies (Family, CompoundType, …) so the stored
    value is the stable member name (e.g. ``"INHIBITOR_BLOCKER"``) and the column
    carries a ``CHECK (col IN (...))`` constraint listing every valid name.
    """
    return SQLEnum(enum_cls, native_enum=False, create_constraint=True)


def value_stored_enum(enum_cls: type[Enum]) -> SQLEnum:
    """Return a SQLAlchemy ``Enum`` that stores the member *value* (not name),
    with a CHECK constraint.

    Used for the unit enums so the physical unit string ("mmHg", "mN/m", …)
    appears verbatim in the column, and the CHECK constraint lists the allowed
    unit strings.
    """
    return SQLEnum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda e: [m.value for m in e],
    )


# --------------------------------------------------------------------------- #
# Identity module
# --------------------------------------------------------------------------- #
class Family(str, Enum):
    """Mechanically-activated ion channel families — 7 canonical + OTHER."""

    PIEZO = "PIEZO"
    TRP = "TRP"
    K2P = "K2P"
    OSCA_TMEM63 = "OSCA/TMEM63"
    MSCL_MSCS = "MscL/MscS"
    TMC = "TMC"
    DEG_ENaC_ASIC = "DEG/ENaC/ASIC"
    OTHER = "OTHER"


class ActivationMechanism(str, Enum):
    """How force reaches the channel gate (not mutually exclusive in nature)."""

    FORCE_FROM_LIPIDS = "Force-from-Lipids"  # FFL — membrane tension gates directly
    FORCE_FROM_FILAMENT = "Force-from-Filament"  # FFF/tether — via cytoskeleton/ECM
    HYBRID = "Hybrid"
    UNKNOWN = "Unknown"
    DISPUTED = "Disputed"


class StructureSource(str, Enum):
    """Origin of a 3D model."""

    PDB = "PDB"
    ALPHAFOLD = "AlphaFold"
    SWISS_MODEL = "SWISS-MODEL"
    OTHER = "OTHER"


class ParameterSet(str, Enum):
    """Which subset of the Mechano-Gating Card an experiment reports."""

    P50 = "P50"
    T50 = "T50"
    X50 = "X50"
    CONDUCTANCE_ONLY = "conductance_only"
    KINETICS_ONLY = "kinetics_only"
    FULL_CARD = "full_card"


class IVRelation(str, Enum):
    """Current–voltage relationship shape."""

    LINEAR = "linear"
    OUTWARD_RECTIFYING = "outward_rectifying"
    INWARD_RECTIFYING = "inward_rectifying"


# --------------------------------------------------------------------------- #
# Biophysics units (value-stored)
# --------------------------------------------------------------------------- #
class PressureUnit(str, Enum):
    """Units for half-activation pressure P50."""

    MMHG = "mmHg"
    KPA = "kPa"
    PA = "Pa"
    MBAR = "mbar"
    CMH2O = "cmH2O"
    PSI = "psi"


class TensionUnit(str, Enum):
    """Units for half-activation membrane tension T50."""

    MN_M = "mN/m"
    DYN_CM = "dyn/cm"
    PN_UM = "pN/um"
    N_M = "N/m"


class IndentationUnit(str, Enum):
    """Units for half-activation indentation X50."""

    UM = "um"
    MM = "mm"
    NM = "nm"


# --------------------------------------------------------------------------- #
# MIMIC stimulus / recording metadata
# --------------------------------------------------------------------------- #
class StimulusType(str, Enum):
    """Type of mechanical stimulus applied (MIMIC)."""

    PRESSURE_CLAMP = "pressure_clamp"
    SUCTION = "suction"
    POSITIVE_PRESSURE = "positive_pressure"
    INDENTATION = "indentation"
    MEMBRANE_STRETCH = "membrane_stretch"
    SHEAR_STRESS = "shear_stress"
    OSMOTIC = "osmotic"
    HYPOTONIC = "hypotonic"
    TOUCH = "touch"
    OTHER = "OTHER"


class RecordingMode(str, Enum):
    """Patch-clamp / electrophysiology recording configuration (MIMIC)."""

    CELL_ATTACHED = "cell-attached"
    INSIDE_OUT = "inside-out"
    OUTSIDE_OUT = "outside-out"
    WHOLE_CELL = "whole-cell"
    PERFORATED_PATCH = "perforated-patch"
    TEVC = "TEVC"  # two-electrode voltage clamp
    RECONSTITUTED_PROTEOLIPOSOME = "reconstituted_proteoliposome"
    PLANAR_PATCH = "planar_patch"
    OTHER = "OTHER"


# --------------------------------------------------------------------------- #
# Pharmacology module
# --------------------------------------------------------------------------- #
class CompoundType(str, Enum):
    """Functional classification of a modulator.

    The raw Piezo1 data uses ``"inhibitor/blocker"`` and the provenance tag
    ``"ChEMBL-only"``; these normalize to ``INHIBITOR_BLOCKER`` and
    ``UNCLASSIFIED`` respectively at load time.
    """

    ACTIVATOR = "activator"
    INHIBITOR_BLOCKER = "inhibitor_blocker"
    INHIBITOR = "inhibitor"
    ANTAGONIST = "antagonist"
    POTENTIATOR = "potentiator"
    UNKNOWN = "unknown"
    UNCLASSIFIED = "unclassified"


class ActivityType(str, Enum):
    """Bioactivity / potency measure. Extensible — ``OTHER`` absorbs new types."""

    EC50 = "EC50"
    IC50 = "IC50"
    KD = "Kd"
    KI = "Ki"
    KB = "Kb"
    PEC50 = "pEC50"
    POTENCY = "Potency"
    ACTIVITY = "Activity"
    INHIBITION = "Inhibition"
    AGONIST_ACTIVITY = "Agonist activity"
    BINDING_AFFINITY = "Binding affinity"
    GI50 = "GI50"
    OTHER = "OTHER"


class AssayFormat(str, Enum):
    """Assay format, parsed from free-text ``assay_description``."""

    FLIPR = "FLIPR"
    SPR = "SPR"
    PATCH_CLAMP = "patch_clamp"
    CALCIUM_IMAGING = "calcium_imaging"
    TEVC = "TEVC"
    ELECTROPHYSIOLOGY = "electrophysiology"
    RADIOLIGAND_BINDING = "radioligand_binding"
    FLUORESCENCE = "fluorescence"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# Disease module
# --------------------------------------------------------------------------- #
class VariantType(str, Enum):
    """Sequence-variant classification (ClinVar-style)."""

    MISSENSE = "missense"
    NONSENSE = "nonsense"
    FRAMESHIFT = "frameshift"
    INFRAME_DELETION = "inframe_deletion"
    INFRAME_INSERTION = "inframe_insertion"
    SPLICE_DONOR = "splice_donor"
    SPLICE_ACCEPTOR = "splice_acceptor"
    SYNONYMOUS = "synonymous"
    STOP_GAIN = "stop_gain"
    STOP_LOSS = "stop_loss"
    START_LOSS = "start_loss"
    DUPLICATION = "duplication"
    DELETION = "deletion"
    INDEL = "indel"
    UTR = "UTR"


class ClinvarSignificance(str, Enum):
    """ClinVar clinical significance tiers (ACMG/AMP-aligned)."""

    PATHOGENIC = "pathogenic"
    LIKELY_PATHOGENIC = "likely_pathogenic"
    UNCERTAIN_SIGNIFICANCE = "uncertain_significance"
    LIKELY_BENIGN = "likely_benign"
    BENIGN = "benign"
    CONFLICTING = "conflicting"
    RISK_FACTOR = "risk_factor"
    ASSOCIATION = "association"
    NOT_PROVIDED = "not_provided"
    OTHER = "OTHER"


class FunctionalEffect(str, Enum):
    """Effect of a variant (or ligand) on channel mechanosensitivity."""

    GAIN_OF_FUNCTION = "gain_of_function"
    LOSS_OF_FUNCTION = "loss_of_function"
    MIXED_GOF_LOF = "mixed_GoF_LoF"
    NO_EFFECT = "no_effect"
    GAIN_OF_MECHANOSENSITIVITY = "gain_of_mechanosensitivity"
    LOSS_OF_MECHANOSENSITIVITY = "loss_of_mechanosensitivity"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# Cross-cutting: provenance / external references
# --------------------------------------------------------------------------- #
class SourceDb(str, Enum):
    """External database / provenance source.

    Used both for the per-row provenance stub (``source_db``) and for the
    polymorphic :class:`external_reference` table.
    """

    UNIPROT = "UniProt"
    PDB = "PDB"
    ALPHAFOLD = "AlphaFold"
    HGNC = "HGNC"
    NCBI_GENE = "NCBI_Gene"
    CHEMBL_TARGET = "ChEMBL_Target"
    CHEMBL_MOLECULE = "ChEMBL_Molecule"
    PUBCHEM = "PubChem"
    BINDINGDB = "BindingDB"
    IUPHAR = "IUPHAR"
    CLINVAR = "ClinVar"
    OMIM = "OMIM"
    MECHANOBASE = "MechanoBase"
    MECHANOPRODB = "MechanoProDB"
    ICG = "ICG"
    CHANNELPEDIA = "Channelpedia"
    TRIP = "TRIP"
    GO = "GO"
    DOI = "DOI"
    LITERATURE = "Literature"


class EntityType(str, Enum):
    """Polymorphic parent of an :class:`external_reference` row."""

    CHANNEL = "channel"
    STRUCTURE = "structure"
    COMPOUND = "compound"
    VARIANT = "variant"
    BIOPHYSICS_EXPERIMENT = "biophysics_experiment"

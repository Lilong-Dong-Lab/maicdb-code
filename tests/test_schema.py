"""Schema validation for MAIC-DB.

These tests prove the schema **fits the real Piezo1 reference dataset** without
ingesting any CSV/JSON. They instantiate ORM objects from actual Piezo1 values
and assert the schema accepts them — covering type fit, constraints, enums,
foreign-key resolution, nullability, and the module bridges.

Grouped into:

* **Tier A** — structural: DDL applies cleanly, is idempotent, and renders
  ``CHECK`` constraints for enum columns.
* **Tier B** — real-data mapping: each table accepts the corresponding Piezo1
  field shapes, including the two empty-but-ready modules (Biophysics, Disease).
* **Drift** — the checked-in ``schema.sql`` stays in sync with the live ORM.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from maicdb.accessions import AccessionPrefix, format_accession
from maicdb.database import SCHEMA_PATH, create_all, make_engine, render_ddl
from maicdb.enums import (
    ActivityType,
    AssayFormat,
    CompoundType,
    EntityType,
    Family,
    FunctionalEffect,
    PressureUnit,
    RecordingMode,
    SourceDb,
    StimulusType,
    StructureSource,
    TensionUnit,
)
from maicdb.models import (
    ALL_TABLES,
    Bioactivity,
    BiophysicsExperiment,
    Channel,
    Compound,
    ExternalReference,
    Publication,
    Structure,
    Variant,
)

# --------------------------------------------------------------------------- #
# Helpers — build entities with realistic Piezo1 values
# --------------------------------------------------------------------------- #
_SEQ = {"CH": 0, "ST": 0, "BX": 0, "CP": 0, "BA": 0, "VR": 0}


def _acc(prefix: AccessionPrefix) -> str:
    """Tiny counter so each test row gets a unique accession."""
    _SEQ[str(prefix.value)] = _SEQ.get(str(prefix.value), 0) + 1
    return format_accession(prefix, _SEQ[str(prefix.value)])


def make_piezo1_channel(
    organism: str,
    taxid: int,
    uniprot: str | None,
) -> Channel:
    """A realistic Piezo1 channel row (human or mouse)."""
    return Channel(
        maicdb_id=_acc(AccessionPrefix.CHANNEL),
        gene_symbol="PIEZO1",
        gene_aliases=["FAM38A", "Mib"],
        uniprot_accession=uniprot,
        organism=organism,
        organism_taxid=taxid,
        ncbi_gene_id=9780 if taxid == 9606 else 52154,
        sequence_length=2521,
        family=Family.PIEZO,
        activation_mechanism="Force-from-Lipids",
        go_terms=["GO:0050982", "GO:0009612"],
        ortholog_group="PIEZO1",
        source_db=SourceDb.UNIPROT,
    )


def flush_get_id(session: Session, obj) -> int:
    """Flush *obj* and return its assigned surrogate id."""
    session.add(obj)
    session.flush()
    return obj.id


# --------------------------------------------------------------------------- #
# Tier A — structural
# --------------------------------------------------------------------------- #
def test_ddl_creates_cleanly_with_all_tables(engine):
    """create_all produces the 8 expected tables with declared columns."""
    table_names = set(inspect(engine).get_table_names())
    expected = {t.__tablename__ for t in ALL_TABLES}
    assert expected <= table_names, f"missing tables: {expected - table_names}"

    # Spot-check key columns on the hub table.
    channel_cols = {c["name"] for c in inspect(engine).get_columns("channel")}
    for required in {
        "id", "maicdb_id", "gene_symbol", "organism_taxid", "family",
        "ortholog_group", "uniprot_accession",
    }:
        assert required in channel_cols, f"channel missing column {required}"

    # The Mechano-Gating Card fields exist on the biophysics table.
    bx_cols = {c["name"] for c in inspect(engine).get_columns("biophysics_experiment")}
    for required in {
        "p50_value", "p50_unit", "tau_act_ms", "tau_inact_ms", "conductance_ps",
        "recording_mode", "stimulus_type", "compound_id",
    }:
        assert required in bx_cols, f"biophysics_experiment missing column {required}"


def test_create_all_is_idempotent(engine):
    """Re-applying create_all (checkfirst) raises no error."""
    create_all(engine)  # second application
    create_all(engine)  # third, to be sure


def test_enum_check_constraints_present(engine):
    """Enum columns render as VARCHAR with a CHECK constraint in SQLite."""
    # Pull the raw CREATE TABLE SQL from sqlite_master via the 2.0 connection API.
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type='table' AND name='channel'"
            )
        ).fetchone()
    create_sql = row[0]
    assert "CHECK" in create_sql.upper()
    # The family enum's allowed values appear in the constraint.
    assert "PIEZO" in create_sql


# --------------------------------------------------------------------------- #
# Tier B — real-data mapping
# --------------------------------------------------------------------------- #
def test_channel_two_organisms_split_and_unique(session):
    """The JSON's 2-organism collapse → two channel rows sharing ortholog_group.

    UNIQUE(gene_symbol, organism_taxid) enforces the split.
    """
    human = make_piezo1_channel("Homo sapiens", 9606, "Q92508")
    mouse = make_piezo1_channel("Mus musculus", 10090, uniprot=None)
    session.add_all([human, mouse])
    session.flush()

    assert human.id != mouse.id
    assert human.ortholog_group == mouse.ortholog_group == "PIEZO1"

    # A third row duplicating (gene_symbol, organism_taxid) must be rejected.
    dup = make_piezo1_channel("Homo sapiens", 9606, uniprot=None)
    dup.maicdb_id = _acc(AccessionPrefix.CHANNEL)
    session.add(dup)
    with pytest.raises(IntegrityError):
        session.flush()


def test_structure_accepts_prose_fields(session):
    """README-prose fields (conformational state, aux subunit, mutation, DOI) fit.

    Values vault-sourced (data-v1.0): PDB 8YFC per
    data/piezo1/structures/piezo1_pdb_structures.csv; DOI from the raw RCSB
    entry detail (data/piezo1/raw/piezo1_pdb_entries_detail/8YFC.json,
    primary citation Shan et al. 2025). deposition_date None — empty in the
    vault CSV (not captured). conformational_state is free-text prose
    (no vault column) kept as the schema-acceptance example.
    """
    ch = make_piezo1_channel("Homo sapiens", 9606, "Q92508")
    session.add(ch)
    session.flush()

    st = Structure(
        maicdb_id=_acc(AccessionPrefix.STRUCTURE),
        channel_id=ch.id,
        pdb_id="8YFC",
        structure_source=StructureSource.PDB,
        title="Human PIEZO1-A1988V-MDFIC",
        method="E, M",
        resolution_a=3.2,
        organism="Homo sapiens",
        num_chains=2,
        has_inhibitor=False,
        auxiliary_subunits=["MDFIC"],
        mutation="A1988V",
        conformational_state="curved/resting",
        deposition_date=None,   # empty in vault CSV
        doi="10.7554/eLife.101923",
    )
    session.add(st)
    session.flush()
    assert st.id is not None
    assert st.conformational_state == "curved/resting"


def test_structure_accepts_empty_csv_fields(session):
    """The CSV's empty columns (residues, coverage, doi) are nullable.

    PDB 8ZU3 values vault-sourced (data-v1.0,
    data/piezo1/structures/piezo1_pdb_structures.csv).
    """
    ch = make_piezo1_channel("Homo sapiens", 9606, "Q92508")
    session.add(ch)
    session.flush()

    st = Structure(
        maicdb_id=_acc(AccessionPrefix.STRUCTURE),
        channel_id=ch.id,
        pdb_id="8ZU3",
        structure_source=StructureSource.PDB,
        title="Human PIEZO1-MDFIC",
        method="E, M",
        resolution_a=3.1,
        organism="Homo sapiens",
        num_chains=2,
        residues_covered=None,  # EMPTY in CSV
        coverage_pct=None,      # EMPTY in CSV
        deposition_date=None,   # EMPTY in CSV
        doi=None,               # EMPTY in CSV
        has_inhibitor=False,
    )
    session.add(st)
    session.flush()
    assert st.residues_covered is None
    assert st.doi is None


def test_compound_type_enum_contract(engine):
    """Enum columns carry a CHECK constraint; invalid values are DB-rejected;
    raw source vocabulary must be normalized to a member before insert."""
    # Membership / normalization contract (no DB needed).
    valid_names = {m.name for m in CompoundType}
    assert "INHIBITOR_BLOCKER" in valid_names
    assert "UNCLASSIFIED" in valid_names  # bucket for the "ChEMBL-only" provenance tag
    assert "ChEMBL-only" not in valid_names  # must be normalized before insert

    # A valid member inserts via raw SQL.
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO compound (maicdb_id, name, compound_type) "
                "VALUES ('MAIC:CP:00001','Yoda1','ACTIVATOR')"
            )
        )
        # The normalized bucket for "ChEMBL-only" is also accepted.
        conn.execute(
            text(
                "INSERT INTO compound (maicdb_id, name, compound_type) "
                "VALUES ('MAIC:CP:00002','chembl-only-analog','UNCLASSIFIED')"
            )
        )
        conn.commit()

        # An invalid raw value is rejected by the CHECK constraint.
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO compound (maicdb_id, name, compound_type) "
                    "VALUES ('MAIC:CP:00003','bad','ChEMBL-only')"
                )
            )


def test_bioactivity_keeps_and_parses_assay_description(session):
    """assay_description is kept verbatim AND parsed into structured fields."""
    ch = make_piezo1_channel("Homo sapiens", 9606, "Q92508")
    cpd = Compound(
        maicdb_id=_acc(AccessionPrefix.COMPOUND),
        name="Yoda1",
        chembl_id="CHEMBL4303374",
        compound_type=CompoundType.ACTIVATOR,
    )
    session.add_all([ch, cpd])
    session.flush()

    desc = (
        "Agonist activity at human Piezo1 transfected in human HEK293T cells "
        "by FLIPR assay"
    )
    ba = Bioactivity(
        maicdb_id=_acc(AccessionPrefix.BIOACTIVITY),
        compound_id=cpd.id,
        channel_id=ch.id,
        target_chembl_id="CHEMBL5169186",
        activity_type=ActivityType.EC50,
        activity_value=26600.0,
        activity_units="nM",
        pchembl=4.58,
        assay_description=desc,        # verbatim, kept
        assay_format=AssayFormat.FLIPR,  # parsed
        cell_line="HEK293T",            # parsed
        target_species="Homo sapiens",  # parsed
        source_db=SourceDb.CHEMBL_MOLECULE,
    )
    session.add(ba)
    session.flush()
    assert ba.assay_description == desc
    assert ba.assay_format == AssayFormat.FLIPR


def test_bioactivity_mouse_target_resolves(session):
    """CHEMBL5169095 (mouse) target resolves to the mouse channel via FK."""
    human = make_piezo1_channel("Homo sapiens", 9606, "Q92508")
    mouse = make_piezo1_channel("Mus musculus", 10090, uniprot=None)
    cpd = Compound(
        maicdb_id=_acc(AccessionPrefix.COMPOUND),
        name="Yoda1",
        chembl_id="CHEMBL4303374",
    )
    session.add_all([human, mouse, cpd])
    session.flush()

    ba = Bioactivity(
        maicdb_id=_acc(AccessionPrefix.BIOACTIVITY),
        compound_id=cpd.id,
        channel_id=mouse.id,  # resolved to MOUSE channel
        target_chembl_id="CHEMBL5169095",
        activity_type=ActivityType.EC50,
        activity_value=600.0,
        activity_units="nM",
        source_db=SourceDb.CHEMBL_MOLECULE,
    )
    session.add(ba)
    session.flush()
    session.refresh(ba)
    assert ba.channel.organism == "Mus musculus"
    assert ba.target_chembl_id == "CHEMBL5169095"


def test_biophysics_empty_but_ready(session):
    """The Biophysics module commits with every card/MIMIC column NULL."""
    ch = make_piezo1_channel("Homo sapiens", 9606, "Q92508")
    session.add(ch)
    session.flush()

    bx = BiophysicsExperiment(
        maicdb_id=_acc(AccessionPrefix.BIOPHYSICS_EXPERIMENT),
        channel_id=ch.id,
        experiment_label="placeholder (no data yet)",
    )
    session.add(bx)
    session.flush()
    # All card + MIMIC columns are genuinely nullable at launch.
    assert bx.p50_value is None
    assert bx.conductance_ps is None
    assert bx.recording_mode is None


def test_biophysics_full_card_with_units(session):
    """A fully-populated Mechano-Gating Card with value+unit pairs + MIMIC.

    SYNTHETIC representative card — no single vault experiment populates a
    full card (1 extraction row = 1 experiment; wide value columns are
    mutually exclusive by design). Values sit inside vault-observed Piezo1
    ranges (data/piezo1/extraction: conductance 22.9–73 pS, T50 1.8–4.7 mN/m,
    tau_inact 13–33.8 ms); p50/slope/tau_act are illustrative.
    """
    ch = make_piezo1_channel("Homo sapiens", 9606, "Q92508")
    session.add(ch)
    session.flush()

    bx = BiophysicsExperiment(
        maicdb_id=_acc(AccessionPrefix.BIOPHYSICS_EXPERIMENT),
        channel_id=ch.id,
        parameter_set="full_card",
        p50_value=-30.0,
        p50_unit=PressureUnit.MMHG,
        t50_value=4.4,
        t50_unit=TensionUnit.MN_M,
        slope=8.0,
        tau_act_ms=2.1,
        tau_inact_ms=15.0,
        conductance_ps=23.5,
        # MIMIC metadata
        stimulus_type=StimulusType.PRESSURE_CLAMP,
        stimulus_waveform="step",
        recording_mode=RecordingMode.CELL_ATTACHED,
        expression_system="HEK293T transient",
        temperature_c=22.0,
        ph=7.4,
        holding_potential_mv=-80.0,
        n_cells=8,
    )
    session.add(bx)
    session.flush()
    assert bx.p50_unit == PressureUnit.MMHG
    assert bx.conductance_ps == pytest.approx(23.5)


def test_biophysics_delta_p50_compound_bridge(session):
    """compound_id + delta_p50 implements the Pharmacology↔Biophysics bridge."""
    ch = make_piezo1_channel("Homo sapiens", 9606, "Q92508")
    cpd = Compound(
        maicdb_id=_acc(AccessionPrefix.COMPOUND),
        name="Yoda1",
        chembl_id="CHEMBL4303374",
        compound_type=CompoundType.ACTIVATOR,
    )
    session.add_all([ch, cpd])
    session.flush()

    bx = BiophysicsExperiment(
        maicdb_id=_acc(AccessionPrefix.BIOPHYSICS_EXPERIMENT),
        channel_id=ch.id,
        compound_id=cpd.id,  # bridges to Pharmacology
        p50_value=-30.0,
        p50_unit=PressureUnit.MMHG,
        delta_p50_value=-10.0,  # ligand shifts threshold by -10 mmHg
        delta_p50_unit=PressureUnit.MMHG,
    )
    session.add(bx)
    session.flush()
    session.refresh(bx)
    assert bx.compound.name == "Yoda1"
    assert bx.delta_p50_value == pytest.approx(-10.0)


def test_variant_empty_but_ready(session):
    """The Disease module is ready: a GoF variant commits."""
    ch = make_piezo1_channel("Homo sapiens", 9606, "Q92508")
    session.add(ch)
    session.flush()

    v = Variant(
        maicdb_id=_acc(AccessionPrefix.VARIANT),
        channel_id=ch.id,
        hgvs_protein="p.Met2225Arg",
        mutation_short="M2225R",
        position=2225,
        ref_aa="M",
        alt_aa="R",
        organism="Homo sapiens",
        organism_taxid=9606,
        clinvar_accession="VCV000012345",
        phenotype="Hereditary xerocytosis",
        functional_effect=FunctionalEffect.GAIN_OF_FUNCTION,
        source_db=SourceDb.CLINVAR,
    )
    session.add(v)
    session.flush()
    assert v.functional_effect == FunctionalEffect.GAIN_OF_FUNCTION


@pytest.mark.parametrize(
    "enum_cls,member",
    [
        (ActivityType, ActivityType.EC50),
        (ActivityType, ActivityType.KD),
        (CompoundType, CompoundType.INHIBITOR_BLOCKER),
        (CompoundType, CompoundType.ACTIVATOR),
        (FunctionalEffect, FunctionalEffect.GAIN_OF_FUNCTION),
        (StimulusType, StimulusType.PRESSURE_CLAMP),
        (RecordingMode, RecordingMode.CELL_ATTACHED),
    ],
)
def test_enum_membership_for_real_data(enum_cls, member):
    """Every enum value the real Piezo1 data uses is a declared member."""
    assert member in list(enum_cls)


def test_publication_shared_across_structures(session):
    """Two structures cite one normalized publication (dedup).

    Real sharing pattern from the vault (data-v1.0): PDB 8ZU3 and 8YFC share
    one primary citation — Shan et al., eLife 2025, doi 10.7554/eLife.101923,
    pmid 40668110 (raw RCSB entry details,
    data/piezo1/raw/piezo1_pdb_entries_detail/{8ZU3,8YFC}.json; both
    structures in data/piezo1/structures/piezo1_pdb_structures.csv). The
    original fixture wrongly had 6B3R+6BPZ share one paper — they cite
    different primary citations (Guo & MacKinnon eLife 2017 vs Saotome et al.
    Nature 2018).
    """
    ch = make_piezo1_channel("Homo sapiens", 9606, "Q92508")
    session.add(ch)
    session.flush()

    pub = Publication(
        doi="10.7554/eLife.101923",
        title="Structure of human PIEZO1 and its slow-inactivating channelopathy mutants",
        journal="eLife",
        year=2025,
        authors=["Shan Y", "Guo X", "Zhang M", "Chen M", "Li Y", "Zhang M", "Pei D"],
        pmid=40668110,
    )
    session.add(pub)
    session.flush()

    s1 = Structure(
        maicdb_id=_acc(AccessionPrefix.STRUCTURE),
        channel_id=ch.id,
        pdb_id="8ZU3",
        structure_source=StructureSource.PDB,
        publication_id=pub.id,
    )
    s2 = Structure(
        maicdb_id=_acc(AccessionPrefix.STRUCTURE),
        channel_id=ch.id,
        pdb_id="8YFC",
        structure_source=StructureSource.PDB,
        publication_id=pub.id,
    )
    session.add_all([s1, s2])
    session.flush()
    rows = session.scalar(select(Structure).where(Structure.pdb_id == "8ZU3"))
    assert rows.publication_id == pub.id


def test_external_reference_reverse_lookup(session):
    """Reverse lookup by (source_db, external_id) returns the entity."""
    ch = make_piezo1_channel("Homo sapiens", 9606, "Q92508")
    session.add(ch)
    session.flush()

    xref = ExternalReference(
        entity_type=EntityType.CHANNEL,
        entity_id=ch.id,
        source_db=SourceDb.UNIPROT,
        external_id="Q92508",
        url="https://www.uniprot.org/uniprotkb/Q92508",
    )
    session.add(xref)
    session.flush()

    found = session.scalar(
        select(ExternalReference).where(
            ExternalReference.source_db == SourceDb.UNIPROT,
            ExternalReference.external_id == "Q92508",
        )
    )
    assert found is not None
    assert found.entity_id == ch.id


# --------------------------------------------------------------------------- #
# Drift — schema.sql stays in sync with the ORM
# --------------------------------------------------------------------------- #
def test_schema_sql_in_sync_with_models():
    """The committed schema.sql must match the ORM-generated DDL.

    If this fails, regenerate with ``maicdb-dump-schema`` (or
    ``uv run python -c 'from maicdb.database import dump_schema_sql as d; d()'``).
    """
    assert SCHEMA_PATH.exists(), (
        f"schema.sql missing at {SCHEMA_PATH}; run maicdb-dump-schema to generate it"
    )
    committed = SCHEMA_PATH.read_text(encoding="utf-8")
    live = render_ddl()
    assert committed == live, (
        "schema.sql is out of sync with the ORM models. "
        "Regenerate the DDL dump with `maicdb-dump-schema`."
    )


# --------------------------------------------------------------------------- #
# Sanity: the engine factory + create_all round-trip
# --------------------------------------------------------------------------- #
def test_make_engine_creates_schema():
    eng = make_engine()
    create_all(eng)
    names = set(inspect(eng).get_table_names())
    assert {"channel", "compound", "publication"} <= names

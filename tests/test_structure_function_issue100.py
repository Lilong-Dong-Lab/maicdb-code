"""Structure-function mapping and traversal tests for issue #100."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.pool import StaticPool

from maicdb.constructs import migrate_construct_links
from maicdb.enums import Family, StructureSource
from maicdb.models import BiophysicsExperiment, Channel, Structure, Variant
from maicdb.query import parameter_comparison
from maicdb.structure_function import (
    STRUCTURE_FUNCTION_SCHEMA_VERSION,
    migrate_structure_function,
    structure_function_page,
    variant_structure_locations,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "db" / "maicdb.sqlite"
requires_db = pytest.mark.skipif(
    not DB_PATH.exists(), reason=f"published DB not found at {DB_PATH}"
)


def _channel(session) -> Channel:
    channel = Channel(
        maicdb_id="MAIC:CH:00001",
        gene_symbol="PIEZO1",
        organism="Human",
        family=Family.PIEZO,
    )
    session.add(channel)
    session.flush()
    return channel


def _structure(session, channel: Channel, title: str) -> Structure:
    structure = Structure(
        maicdb_id="MAIC:ST:00001",
        channel_id=channel.id,
        pdb_id="8YFC",
        structure_source=StructureSource.PDB,
        title=title,
        mutation="A1988V",
    )
    session.add(structure)
    session.flush()
    return structure


def test_migration_records_residue_and_variant_location(session):
    channel = _channel(session)
    _structure(session, channel, "Human PIEZO1-A1988V-MDFIC")
    counts = migrate_structure_function(session)
    session.commit()
    assert counts["schema_version_after"] == STRUCTURE_FUNCTION_SCHEMA_VERSION
    assert counts["variants_created"] == 1
    assert counts["residues_created"] == 1
    assert counts["locations_created"] == 1
    assert counts["evidence_created"] == 1
    page = structure_function_page(session.get_bind(), "MAIC:ST:00001")
    assert page["residues"][0]["residue_number"] == 1988
    assert page["residues"][0]["number_system"] == "UNIPROT"
    assert page["traversals"][0]["variant"]["mutation_short"] == "A1988V"
    assert page["traversals"][0]["constructs"] == []
    assert page["evidence"][0]["quote"] == "Human PIEZO1-A1988V-MDFIC"

    repeat = migrate_structure_function(session)
    session.commit()
    assert repeat["residues_created"] == 0
    assert repeat["locations_created"] == 0
    assert repeat["evidence_created"] == 0


def test_variant_traverses_structure_construct_and_experiment(session):
    channel = _channel(session)
    structure = _structure(session, channel, "Human PIEZO1-A1988V-MDFIC")
    migrate_structure_function(session)
    variant = session.scalar(
        select(Variant).where(Variant.mutation_short == "A1988V")
    )
    experiment = BiophysicsExperiment(
        maicdb_id="MAIC:BX:00001",
        channel_id=channel.id,
        measurement_id="measurement-1",
        variant_id=variant.id,
        evidence_quote="The construct was measured.",
        conductance_ps=12.0,
    )
    session.add(experiment)
    session.commit()
    migrate_construct_links(session)
    session.commit()
    engine = session.get_bind()
    traversal = variant_structure_locations(engine, variant.id)[0]
    assert traversal["structure"]["maicdb_id"] == structure.maicdb_id
    assert traversal["constructs"][0]["maicdb_id"].startswith("MAIC:CN:")
    assert traversal["experiments"][0]["maicdb_id"] == experiment.maicdb_id
    comparison = parameter_comparison(engine, "conductance")
    assert comparison[0]["structure_ids"] == []


@requires_db
def test_frozen_corpus_structure_function_census():
    engine = create_engine(
        f"sqlite:///file:{DB_PATH}?mode=ro&uri=true",
        connect_args={"uri": True},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        counts = {
            table: conn.scalar(text(f"SELECT COUNT(*) FROM {table}"))
            for table in (
                "structure_residue",
                "structure_variant_location",
                "evidence_subject",
            )
        }
        counts["evidence_subject"] = conn.scalar(
            text(
                "SELECT COUNT(*) FROM evidence_subject "
                "WHERE subject_type='STRUCTURE'"
            )
        )
        schema_version = conn.scalar(
            text("SELECT value FROM db_meta WHERE key='schema_version'")
        )
        pdb_evidence = conn.scalar(
            text("SELECT COUNT(*) FROM evidence_item WHERE source='PDB'")
        )
    engine.dispose()
    assert counts == {
        "structure_residue": 4,
        "structure_variant_location": 4,
        "evidence_subject": 4,
    }
    assert pdb_evidence == 4
    assert schema_version == "0.8.0"

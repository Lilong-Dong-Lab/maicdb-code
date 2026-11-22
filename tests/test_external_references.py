from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from maicdb.database import create_all
from maicdb.enums import (
    ExternalReferenceRelationship,
    Family,
    SourceDb,
    StructureSource,
)
from maicdb.external_references import (
    EXTERNAL_REFERENCE_SCHEMA_VERSION,
    LEGACY_RELATIONSHIP_DISCLOSURE,
    LEGACY_VERSION_DISCLOSURE,
    add_external_reference,
    migrate_external_references,
)
from maicdb.models import (
    BiophysicsExperiment,
    Channel,
    Compound,
    ExternalReferenceRecord,
    Structure,
    Variant,
)
from maicdb.query import channel_card, export, parameter_comparison


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = REPO_ROOT / "db" / "maicdb.sqlite"


def _channel(session: Session) -> Channel:
    channel = Channel(
        maicdb_id="MAIC:CH:00001",
        gene_symbol="PIEZO1",
        organism="Homo sapiens",
        organism_taxid=9606,
        family=Family.PIEZO,
    )
    session.add(channel)
    session.flush()
    return channel


def _reference_values() -> dict:
    return {
        "resource": SourceDb.UNIPROT,
        "external_id": "Q92508",
        "relationship": ExternalReferenceRelationship.SAME_AS,
        "url": "https://www.uniprot.org/uniprotkb/Q92508",
        "external_version": None,
    }


def _record(**overrides) -> ExternalReferenceRecord:
    values = _reference_values()
    values.update(overrides)
    return ExternalReferenceRecord(**values)


def test_different_relationships_share_resource_and_identifier(session):
    channel = _channel(session)
    channel_id = channel.id
    add_external_reference(
        session,
        subject_type="channel",
        subject_id=channel_id,
        resource=SourceDb.UNIPROT,
        external_id="Q92508",
        relationship=ExternalReferenceRelationship.SAME_AS,
    )
    add_external_reference(
        session,
        subject_type="channel",
        subject_id=channel.id,
        resource=SourceDb.UNIPROT,
        external_id="Q92508",
        relationship=ExternalReferenceRelationship.RELATED_TO,
    )
    assert session.query(ExternalReferenceRecord).count() == 2


def test_duplicate_subject_resource_identifier_relationship_rejected(session):
    channel = _channel(session)
    channel_id = channel.id
    add_external_reference(
        session,
        subject_type="channel",
        subject_id=channel.id,
        resource=SourceDb.UNIPROT,
        external_id="Q92508",
    )
    assert session.query(ExternalReferenceRecord).count() == 1
    assert session.execute(
        text("SELECT COUNT(*) FROM channel_external_reference")
    ).scalar() == 1
    with pytest.raises(ValueError, match="duplicate semantic external reference"):
        add_external_reference(
            session,
            subject_type="channel",
            subject_id=channel_id,
            resource=SourceDb.UNIPROT,
            external_id="Q92508",
        )


def test_subject_integrity_rejects_missing_and_unknown_subjects(session):
    channel = _channel(session)
    channel_id = channel.id
    record = add_external_reference(
        session,
        subject_type="channel",
        subject_id=channel_id,
        resource=SourceDb.UNIPROT,
        external_id="P00000",
    )
    session.commit()
    record_id = record.id
    assert record_id is not None
    assert session.query(ExternalReferenceRecord).count() == 1
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO channel_external_reference "
                "(id, resource, external_id, relationship, channel_id) "
                "VALUES (:id, 'UNIPROT', 'Q92508', 'SAME_AS', 999999)"
            ),
            {"id": record_id},
        )


def test_version_applicability_is_explicit(session):
    channel = _channel(session)
    channel_id = channel.id
    add_external_reference(
        session,
        subject_type="channel",
        subject_id=channel_id,
        resource=SourceDb.CHEMBL_TARGET,
        external_id="CHEMBL5169186",
        external_version="33",
    )
    session.commit()
    assert session.query(ExternalReferenceRecord).one().external_version == "33"


def test_unknown_and_missing_versions_rejected(session):
    session.add(_record(external_version="unknown"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    session.add(
        _record(
            resource=SourceDb.CHEMBL_TARGET,
            url="https://www.ebi.ac.uk/chembl/gcov/CHEMBL5169186",
            external_id="CHEMBL5169186",
            external_version=None,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_loader_helper_requires_evidenced_applicable_version(session):
    channel = _channel(session)
    channel_id = channel.id
    with pytest.raises(ValueError, match="evidenced release version"):
        add_external_reference(
            session,
            subject_type="channel",
            subject_id=channel_id,
            resource=SourceDb.CHEMBL_TARGET,
            external_id="CHEMBL5169186",
        )
    assert session.query(ExternalReferenceRecord).count() == 0


def test_legacy_surface_is_compatibility_view(session):
    channel = _channel(session)
    add_external_reference(
        session,
        subject_type="channel",
        subject_id=channel.id,
        resource=SourceDb.UNIPROT,
        external_id="Q92508",
    )
    session.commit()
    inspector = inspect(session.get_bind())
    assert "external_reference" in inspector.get_view_names()
    assert "external_reference" not in inspector.get_table_names()
    row = session.execute(
        text(
            "SELECT channel_id, resource, external_id, relationship, "
            "external_version FROM external_reference"
        )
    ).one()
    assert row == (channel.id, "UNIPROT", "Q92508", "SAME_AS", None)


def test_all_supported_subjects_have_typed_link_tables_and_integrity(engine, session):
    channel = _channel(session)
    compound = Compound(maicdb_id="MAIC:CP:00001", name="Yoda1")
    variant = Variant(
        maicdb_id="MAIC:VA:00001", channel_id=channel.id, mutation_short="M2225R"
    )
    structure = Structure(
        maicdb_id="MAIC:ST:00001",
        channel_id=channel.id,
        structure_source=StructureSource.PDB,
    )
    experiment = BiophysicsExperiment(
        maicdb_id="MAIC:EX:00001", channel_id=channel.id
    )
    session.add_all([compound, variant, structure, experiment])
    session.flush()
    add_external_reference(
        session,
        subject_type="channel",
        subject_id=channel.id,
        resource=SourceDb.UNIPROT,
        external_id="Q92508",
    )
    add_external_reference(
        session, subject_type="compound", subject_id=compound.id,
        resource=SourceDb.CHEMBL_MOLECULE, external_id="CHEMBL4303374",
        external_version="33",
    )
    add_external_reference(
        session, subject_type="variant", subject_id=variant.id,
        resource=SourceDb.CLINVAR, external_id="VCV000012345",
    )
    add_external_reference(
        session, subject_type="structure", subject_id=structure.id,
        resource=SourceDb.PDB, external_id="8ZU3",
    )
    add_external_reference(
        session, subject_type="experiment", subject_id=experiment.id,
        resource=SourceDb.DOI, external_id="10.7554/eLife.101923",
        relationship=ExternalReferenceRelationship.PUBLISHED_IN,
    )
    assert session.query(ExternalReferenceRecord).count() == 5
    for table in inspect(session.get_bind()).get_table_names():
        if table.endswith("_external_reference"):
            assert table

def _prepare_legacy(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP VIEW external_reference")
        connection.exec_driver_sql(
            """
            CREATE TABLE external_reference (
                id INTEGER PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                source_db TEXT NOT NULL,
                external_id TEXT NOT NULL,
                url TEXT,
                created_at DATETIME
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO channel (maicdb_id, gene_symbol, organism, family)
            VALUES ('MAIC:CH:00001', 'PIEZO1', 'Homo sapiens', 'PIEZO')
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO external_reference (
                entity_type, entity_id, source_db, external_id, url, created_at
            ) VALUES (
                'channel', 1, 'UNIPROT', 'Q92508',
                'https://www.uniprot.org/uniprotkb/Q92508', '2026-01-01'
            ), (
                'channel', 1, 'CHEMBL_TARGET', 'CHEMBL5169186', NULL, '2026-01-01'
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO db_meta (key, value) VALUES ('schema_version', '0.5.0')"
        )


def test_migration_preserves_rows_fk_ids_and_atomic_transition(engine):
    _prepare_legacy(engine)
    result = migrate_external_references(engine)
    assert result["schema_version_before"] == "0.5.0"
    assert result["schema_version_after"] == EXTERNAL_REFERENCE_SCHEMA_VERSION
    assert result["legacy_rows_examined"] == 2
    assert result["semantic_rows_created"] == 2
    assert result["legacy_relationships_disclosed"] == 2
    assert result["missing_applicable_versions"] == 1
    assert LEGACY_RELATIONSHIP_DISCLOSURE in result["disclosures"]
    assert LEGACY_VERSION_DISCLOSURE in result["disclosures"]
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            """
            SELECT id, channel_id, resource, external_id, relationship, url,
                   external_version FROM external_reference ORDER BY id
            """
        ).all()
        assert rows == [
            (1, 1, "UNIPROT", "Q92508", "SAME_AS", "https://www.uniprot.org/uniprotkb/Q92508", None),
            (2, 1, "CHEMBL_TARGET", "CHEMBL5169186", "SAME_AS", "https://www.ebi.ac.uk/chembl/gcov/CHEMBL5169186", None),
        ]
        assert connection.execute(
            text("SELECT value FROM db_meta WHERE key = 'schema_version'")
        ).scalar_one() == EXTERNAL_REFERENCE_SCHEMA_VERSION


def test_migration_rejects_wrong_before_version_without_writing(engine):
    _prepare_legacy(engine)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE db_meta SET value = '0.1.0' WHERE key = 'schema_version'")
        )
    with pytest.raises(ValueError, match="unsupported schema migration"):
        migrate_external_references(engine)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM external_reference")
        ).scalar_one() == 2
        assert connection.execute(
            text("SELECT COUNT(*) FROM external_reference_record")
        ).scalar_one() == 0


def test_migration_is_idempotent_at_transition_level(engine):
    _prepare_legacy(engine)
    migrate_external_references(engine)
    with pytest.raises(ValueError, match="unsupported schema migration"):
        migrate_external_references(engine)


def test_migration_reuses_global_record_for_shared_semantic_reference(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP VIEW external_reference")
        connection.exec_driver_sql(
            """
            CREATE TABLE external_reference (
                id INTEGER PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                source_db TEXT NOT NULL,
                external_id TEXT NOT NULL,
                url TEXT,
                created_at DATETIME
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO channel (maicdb_id, gene_symbol, organism, family)
            VALUES ('MAIC:CH:SHARED', 'PIEZO1', 'Homo sapiens', 'PIEZO')
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO compound (maicdb_id, name)
            VALUES ('MAIC:CP:SHARED', 'Yoda1')
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO external_reference (
                entity_type, entity_id, source_db, external_id, url, created_at
            ) VALUES (
                'channel', 1, 'DOI', '10.7554/eLife.101923',
                'https://doi.org/10.7554/eLife.101923', '2026-01-01'
            ), (
                'compound', 1, 'DOI', '10.7554/eLife.101923',
                'https://doi.org/10.7554/eLife.101923', '2026-01-01'
            )
            """
        )
        connection.execute(
            text(
                "INSERT INTO db_meta (key, value) "
                "VALUES ('schema_version', '0.5.0')"
            )
        )

    result = migrate_external_references(engine)
    with engine.connect() as connection:
        records = connection.execute(
            text(
                "SELECT resource, external_id, relationship, url, "
                "external_version, legacy_version_disclosed "
                "FROM external_reference_record"
            )
        ).all()
        links = connection.execute(
            text(
                "SELECT channel_id FROM channel_external_reference "
                "UNION ALL SELECT compound_id FROM compound_external_reference"
            )
        ).all()

    assert result["legacy_rows_examined"] == 2
    assert result["semantic_rows_created"] == 2
    assert records == [
        (
            "DOI",
            "10.7554/eLife.101923",
            "SAME_AS",
            "https://doi.org/10.7554/eLife.101923",
            None,
            1,
        )
    ]
    assert links == [(1,), (1,)]


@pytest.mark.skipif(not ARTIFACT.exists(), reason="published artifact missing")
def test_artifact_migration_counts_disclosure_and_published_bytes_unchanged(tmp_path):
    original_hash = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    copied = tmp_path / "maicdb.sqlite"
    shutil.copyfile(ARTIFACT, copied)
    from maicdb.database import make_engine

    engine = make_engine(f"sqlite:///{copied}")
    result = migrate_external_references(engine)
    assert result["legacy_rows_examined"] == 6
    assert result["semantic_rows_created"] == 6
    assert result["missing_applicable_versions"] == 2
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == original_hash


def test_channel_card_and_parameter_exports_expose_semantic_references(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO channel (maicdb_id, gene_symbol, organism, family)
            VALUES ('MAIC:CH:00001', 'PIEZO1', 'Homo sapiens', 'PIEZO')
            """
        )
    with Session(engine) as session:
        add_external_reference(
            session,
            subject_type="channel",
            subject_id=1,
            resource=SourceDb.UNIPROT,
            external_id="Q92508",
        )
        session.commit()

    card = channel_card(engine, "PIEZO1", parameters=[])
    comparison = parameter_comparison(engine, "p50")
    exported = export(engine, "p50", format="json", disclose=False)
    expected = [
        {
            "resource": "UNIPROT",
            "external_id": "Q92508",
            "relationship": "SAME_AS",
            "url": "https://www.uniprot.org/uniprotkb/Q92508",
            "external_version": None,
        }
    ]
    assert card["gene"]["external_references"] == expected
    assert comparison[0]["external_references"] == []
    assert json.loads(exported)["rows"][0]["external_references"] == []
    csv_export = export(engine, "p50", format="csv", disclose=False)
    assert "external_references" in csv_export.splitlines()[0]


def test_parameter_exports_aggregate_contributing_experiment_references(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO channel (maicdb_id, gene_symbol, organism, family)
            VALUES ('MAIC:CH:00001', 'PIEZO1', 'Homo sapiens', 'PIEZO')
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO biophysics_experiment (
                maicdb_id, channel_id, p50_value, p50_unit
            ) VALUES ('MAIC:EX:00001', 1, -30.0, 'mmHg')
            """
        )
    with Session(engine) as session:
        add_external_reference(
            session,
            subject_type="experiment",
            subject_id=1,
            resource=SourceDb.DOI,
            external_id="10.7554/eLife.101923",
            relationship=ExternalReferenceRelationship.PUBLISHED_IN,
        )
        session.commit()

    expected = [
        {
            "resource": "DOI",
            "external_id": "10.7554/eLife.101923",
            "relationship": "PUBLISHED_IN",
            "url": "https://doi.org/10.7554/eLife.101923",
            "external_version": None,
        }
    ]
    comparison = parameter_comparison(engine, "p50")
    exported = export(engine, "p50", format="json", disclose=False)
    assert comparison[0]["external_references"] == expected
    assert json.loads(exported)["rows"][0]["external_references"] == expected

"""Compound-channel relationships and parameter provenance for issue 103."""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from maicdb.data_layers import DATA_LAYER_INVENTORY
from maicdb.enums import (
    CompoundChannelDirection,
    CompoundChannelRole,
    ConcentrationResponseSemantics,
)
from maicdb.models import Bioactivity, Channel, Compound, CompoundChannelRelationship
from maicdb.accessions import AccessionGenerator, AccessionPrefix
from maicdb.parameter_provenance import (
    COMPOUND_RELATIONSHIP_SCHEMA_VERSION,
    migrate_compound_relationships,
    relationships_for_bioactivity,
)
from maicdb.data_layers import migrate_data_layers
from maicdb.external_references import migrate_external_references
from maicdb.query import bioactivity_card, channel_card, open_readonly
from tests.test_site_build import BUILD_SCRIPT, REPO_ROOT, requires_db


DB_PATH = REPO_ROOT / "db" / "maicdb.sqlite"


def _channel(session: Session) -> Channel:
    channel = Channel(
        maicdb_id="MAIC:CH:00001",
        gene_symbol="PIEZO1",
        organism="Homo sapiens",
        family="PIEZO",
    )
    session.add(channel)
    session.flush()
    return channel


def _compound(session: Session, name: str = "Yoda1") -> Compound:
    compound = Compound(maicdb_id="MAIC:CP:00001", name=name)
    session.add(compound)
    session.flush()
    return compound


def test_schema_controls_relationship_semantics(session: Session):
    channel = _channel(session)
    compound = _compound(session)

    relationship = CompoundChannelRelationship(
        maicdb_id=AccessionGenerator().next(
            AccessionPrefix.COMPOUND_CHANNEL_RELATIONSHIP
        ),
        compound_id=compound.id,
        channel_id=channel.id,
        role=CompoundChannelRole.ACTIVATOR,
        direction=CompoundChannelDirection.COMPOUND_TO_CHANNEL,
        assay_context="calcium imaging",
        concentration_response=ConcentrationResponseSemantics.FULL_CURVE,
    )
    session.add(relationship)
    session.flush()
    relationship_id = relationship.id
    session.commit()

    with pytest.raises(IntegrityError) as integrity_error:
        session.add(
            CompoundChannelRelationship(
                maicdb_id="MAIC:CR:00002",
                compound_id=compound.id,
                channel_id=channel.id,
                role=CompoundChannelRole.ACTIVATOR,
                direction=CompoundChannelDirection.COMPOUND_TO_CHANNEL,
                concentration_response=ConcentrationResponseSemantics.SINGLE_POINT,
                assay_context="electrophysiology",
            )
        )
        session.flush()
    session.rollback()
    assert "UNIQUE constraint failed: compound_channel_relationship" in str(
        integrity_error.value
    )

    row = session.get(CompoundChannelRelationship, relationship_id)
    assert row is not None
    assert row.concentration_response is not None


def test_migration_preserves_rows_conflicts_and_schema_transition(engine: Engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO channel (maicdb_id, gene_symbol, organism, family) "
                "VALUES ('MAIC:CH:00001', 'PIEZO1', 'Homo sapiens', 'PIEZO')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO compound "
                "(maicdb_id, name, compound_type) VALUES "
                "('MAIC:CP:00001', 'Yoda1', 'ACTIVATOR')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO bioactivity (maicdb_id, compound_id, channel_id, "
                "assay_description) VALUES "
                "('MAIC:BA:00001', 1, 1, 'calcium imaging')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO db_meta (key, value) "
                "VALUES ('schema_version', '0.7.0')"
            )
        )

    before_ids = _identifiers_and_foreign_keys(engine)
    result = migrate_compound_relationships(engine)

    assert result["schema_version_before"] == "0.7.0"
    assert result["schema_version_after"] == COMPOUND_RELATIONSHIP_SCHEMA_VERSION
    assert result["relationships_created"] == 1
    assert result["conflicts"] == 0
    assert _identifiers_and_foreign_keys(engine) == before_ids

    with engine.connect() as connection:
        role = connection.execute(
            text(
                "SELECT role FROM compound_channel_relationship "
                "WHERE compound_id = 1 AND channel_id = 1"
            )
        ).scalar_one()
        schema_version = connection.execute(
            text("SELECT value FROM db_meta WHERE key = 'schema_version'")
        ).scalar_one()
    assert role == "ACTIVATOR"
    assert schema_version == COMPOUND_RELATIONSHIP_SCHEMA_VERSION
    assert set(inspect(engine).get_table_names()) >= {
        "compound_channel_relationship"
    }


def test_migration_does_not_silently_overwrite_conflicting_legacy_labels(engine: Engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO channel (maicdb_id, gene_symbol, organism, family) "
                "VALUES ('MAIC:CH:00001', 'PIEZO1', 'Homo sapiens', 'PIEZO')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO compound (maicdb_id, name, compound_type) "
                "VALUES ('MAIC:CP:00001', 'Conflicted', 'INHIBITOR_BLOCKER')"
            )
        )
        # A second legacy field-level signal contradicts the compound label.
        connection.execute(
            text(
                "INSERT INTO bioactivity (maicdb_id, compound_id, channel_id, "
                "assay_description, activity_type) VALUES "
                "('MAIC:BA:00001', 1, 1, 'activator assay', 'AGONIST_ACTIVITY')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO compound (maicdb_id, name, compound_type) "
                "VALUES ('MAIC:CP:00002', 'Conflicted2', 'ACTIVATOR')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO db_meta (key, value) "
                "VALUES ('schema_version', '0.7.0')"
            )
        )

    result = migrate_compound_relationships(engine)
    assert result["conflicts"] == 1

    with engine.connect() as connection:
        role, disclosure = connection.execute(
            text(
                "SELECT role, disclosure FROM compound_channel_relationship "
                "WHERE compound_id = 1 AND channel_id = 1"
            )
        ).one()
    assert role == "CONFLICT"
    assert "Conflicting legacy compound labels" in disclosure


def test_migration_accepts_repeated_calls(session: Session):
    _channel(session)
    _compound(session)
    session.add(
        Bioactivity(
            maicdb_id="MAIC:BA:00001",
            compound_id=session.scalar(select(Compound.id)),
            channel_id=session.scalar(select(Channel.id)),
        )
    )
    session.execute(
        text("INSERT INTO db_meta (key, value) VALUES ('schema_version', '0.7.0')")
    )
    session.commit()
    engine = session.get_bind()
    first = migrate_compound_relationships(engine)
    second = migrate_compound_relationships(engine)
    assert first["relationships_created"] == 1
    assert second["relationships_created"] == 0


def test_parameter_provenance_inventory_covers_issue_103_outputs():
    keys = {entry.key for entry in DATA_LAYER_INVENTORY}
    assert "bioactivity_card.activity_value_as_reported" in keys
    assert "channel_card.conversion_provenance" in keys
    assert "compound_channel_relationship.assay_context" in keys


def test_relationship_lookup_accepts_unmigrated_artifacts(engine: Engine):
    result = relationships_for_bioactivity(engine, [(1, 1)])

    assert result == {(1, 1): None}


@requires_db
def test_artifact_migration_and_bioactivity_query_expose_relationships(tmp_path: Path):
    import shutil

    original_hash = _file_hash(DB_PATH)
    copied = tmp_path / "maicdb.sqlite"
    shutil.copyfile(DB_PATH, copied)
    engine = create_engine_for_test(copied)
    migrate_external_references(engine)
    migrate_data_layers(engine)
    result = migrate_compound_relationships(engine)
    assert result["relationships_created"] > 0
    assert result["bioactivity_rows_covered"] == result["rows_examined"]

    card = bioactivity_card(engine, "PIEZO1")
    assert card["n_rows"] > 0
    row = card["rows"][0]
    assert row["relationship"]["role"] in {
        member.name for member in CompoundChannelRole
    }
    assert row["relationship"]["direction"] in {
        member.name for member in CompoundChannelDirection
    }
    assert row["parameter_provenance"]["activity_value_as_reported"] is not None
    assert row["parameter_provenance"]["conversion"] == "none; source units retained"
    assert row["evidence"]
    engine.dispose()
    assert _file_hash(DB_PATH) == original_hash


@requires_db
def test_channel_parameter_rows_carry_conversion_provenance_and_evidence():
    engine = open_readonly(DB_PATH)
    try:
        card = channel_card(engine, "PIEZO1", parameters=["p50"])
        row = next(
            row
            for row in card["parameters"]["p50"]["rows"]
            if row["measurement_id"] == "PIEZO1-EX-00005"
        )
        assert row["parameter_provenance"] == {
            "value_as_reported": "-28.0",
            "unit_as_reported": "mm Hg",
            "conversion": "none; source value and unit retained",
            "evidence_ids": [item["maicdb_id"] for item in row["evidence"]],
        }
    finally:
        engine.dispose()


@requires_db
def test_exports_and_pages_expose_issue_103_fields(tmp_path: Path):
    from maicdb.query import export

    engine = open_readonly(DB_PATH)
    try:
        payload = json.loads(export(engine, "p50", format="json"))
        counted_rows = [row for row in payload["rows"] if row["count"]]
        provenance = counted_rows[0]["parameter_provenance"]
        assert provenance["evidence_ids"]
        assert provenance["conversion"] == (
            "aggregates combine normalization-stable values; per-row "
            "conversion provenance is exposed by channel_card"
        )
        csv_export = export(engine, "p50", format="csv", disclose=False)
        header = next(csv.reader(csv_export.splitlines()))
        assert "parameter_provenance" in header
    finally:
        engine.dispose()

    copied_db = tmp_path / "maicdb.sqlite"
    shutil.copyfile(DB_PATH, copied_db)
    migrated_engine = create_engine_for_test(copied_db)
    migrate_external_references(migrated_engine)
    migrate_data_layers(migrated_engine)
    migrate_compound_relationships(migrated_engine)
    migrated_engine.dispose()
    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--db",
            str(copied_db),
            "--out",
            str(tmp_path / "site"),
        ],
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        check=True,
        capture_output=True,
        text=True,
    )
    tmp_path = tmp_path / "site"
    card = json.loads(
        (tmp_path / "_data" / "channels" / "piezo1.json").read_text(
            encoding="utf-8"
        )
    )
    bioactivity = card["bioactivity"]["rows"][0]
    assert bioactivity["relationship"]["role"]
    assert bioactivity["parameter_provenance"]["activity_value_as_reported"]
    assert (tmp_path / "_site" / "channels" / "piezo1" / "index.html").is_file()


def _identifiers_and_foreign_keys(engine: Engine) -> list[tuple]:
    with engine.connect() as connection:
        channel_rows = connection.execute(
            text("SELECT id, maicdb_id FROM channel ORDER BY id")
        ).all()
        compound_rows = connection.execute(
            text("SELECT id, maicdb_id FROM compound ORDER BY id")
        ).all()
        foreign_keys = connection.execute(
            text("PRAGMA foreign_key_list('bioactivity')")
        ).all()
    return [*channel_rows, *compound_rows, *foreign_keys]


def _file_hash(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_engine_for_test(path: Path) -> Engine:
    from sqlalchemy import create_engine

    return create_engine(f"sqlite:///{path}")

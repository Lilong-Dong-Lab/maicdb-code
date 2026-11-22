"""Native data-layer marking for value-bearing scientific outputs."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil

import pytest
from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from maicdb.analysis.site_payloads import analysis_payloads
from maicdb.data_layers import (
    DATA_LAYER_DEFINITIONS,
    DATA_LAYER_DISCLOSURE,
    DATA_LAYER_INVENTORY,
    DATA_LAYER_SCHEMA_VERSION,
    in_scope_entry,
    migrate_data_layers,
)
from maicdb.enums import DataLayer
from maicdb.external_references import migrate_external_references
from maicdb.models import DataLayerInventory, DataLayerVocabulary
from maicdb.query import (
    bioactivity_card,
    channel_card,
    export,
    open_readonly,
    parameter_comparison,
    provenance,
)
from tests.test_site_build import REPO_ROOT, requires_db, run_build

DB_PATH = REPO_ROOT / "db" / "maicdb.sqlite"


def test_inventory_covers_one_entry_for_every_controlled_layer():
    layers = {entry.layer for entry in DATA_LAYER_INVENTORY}
    assert layers == set(DataLayer)
    assert len({entry.key for entry in DATA_LAYER_INVENTORY}) == len(
        DATA_LAYER_INVENTORY
    )


def test_inventory_entries_have_auditable_rules():
    for entry in DATA_LAYER_INVENTORY:
        assert entry.surface
        assert entry.field
        assert entry.rule


def test_inventory_excludes_incidental_counts_and_metadata():
    fields = {entry.key for entry in DATA_LAYER_INVENTORY}
    assert "search_index.url" not in fields
    assert "analysis.trends.n_records" not in fields


def test_unknown_inventory_key_fails_loudly():
    with pytest.raises(KeyError, match="unknown data-layer inventory key"):
        in_scope_entry("not.a.value-bearing.output")


def test_schema_controls_the_data_layer_vocabulary(engine: Engine):
    assert set(DataLayer) == {
        DataLayer.SOURCE_REPORTED,
        DataLayer.CURATED,
        DataLayer.COMPUTED,
    }
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO data_layer (name, value, definition) "
                    "VALUES ('TEST', 'test', 'fixture-only')"
                )
            )


def test_schema_anchors_the_shared_inventory_contract(session: Session):
    for item in DATA_LAYER_DEFINITIONS:
        session.merge(
            DataLayerVocabulary(
                name=item["name"].name,
                value=item["name"].value,
                definition=item["definition"],
            )
        )
    for entry in DATA_LAYER_INVENTORY:
        session.merge(
            DataLayerInventory(
                key=entry.key,
                surface=entry.surface,
                field=entry.field,
                layer=entry.layer.name,
                rule=entry.rule,
            )
        )
    session.flush()
    rows = session.execute(
        text(
            "SELECT key, surface, field, layer, rule "
            "FROM data_layer_inventory ORDER BY key"
        )
    ).all()
    assert rows == [
        (entry.key, entry.surface, entry.field, entry.layer.name, entry.rule)
        for entry in sorted(DATA_LAYER_INVENTORY, key=lambda entry: entry.key)
    ]


@requires_db
def test_channel_card_distinguishes_source_and_curated_values():
    engine = open_readonly(DB_PATH)
    card = channel_card(engine, "PIEZO1", parameters=["p50"])
    row = next(
        row
        for row in card["parameters"]["p50"]["rows"]
        if row["measurement_id"] == "PIEZO1-EX-00005"
    )
    assert (
        row["data_layers"]["value_as_reported"]
        == DataLayer.SOURCE_REPORTED.value
    )
    assert (
        row["data_layers"]["unit_as_reported"]
        == DataLayer.SOURCE_REPORTED.value
    )
    assert row["data_layers"]["value"] == DataLayer.CURATED.value
    engine.dispose()


@requires_db
def test_parameter_comparison_and_exports_are_computed():
    engine = open_readonly(DB_PATH)
    rows = parameter_comparison(engine, "p50")
    counted = [row for row in rows if row["count"] > 0]
    assert all(row["data_layer"] == DataLayer.COMPUTED.value for row in counted)

    csv_export = export(engine, "p50", format="csv", disclose=False)
    header = next(csv.reader(csv_export.splitlines()))
    assert header.index("data_layer") == 13

    json_export = json.loads(export(engine, "p50", format="json"))
    assert all(
        row["data_layer"] == DataLayer.COMPUTED.value
        for row in json_export["rows"]
    )
    engine.dispose()


@requires_db
def test_bioactivity_card_and_provenance_are_curated():
    engine = open_readonly(DB_PATH)
    card = bioactivity_card(engine, "PIEZO1")
    assert card["n_rows"]
    assert all(
        row["data_layers"]["activity_value"] == DataLayer.CURATED.value
        for row in card["rows"]
    )

    row = provenance(engine, "PIEZO1-EX-00005")
    assert row is not None
    assert row["data_layers"]["value"] == DataLayer.CURATED.value
    bioactivity = provenance(engine, "ASIC-00025")
    assert bioactivity is not None
    assert bioactivity["data_layers"]["value"] == DataLayer.CURATED.value
    engine.dispose()


@requires_db
def test_all_analysis_payloads_are_computed():
    engine = open_readonly(DB_PATH)
    payloads = analysis_payloads(engine)
    assert payloads
    assert all(
        payload["data_layer"] == DataLayer.COMPUTED.value
        for payload in payloads.values()
    )
    engine.dispose()


@requires_db
def test_site_payloads_and_pages_carry_data_layer(tmp_path):
    run_build(tmp_path)
    data_dir = tmp_path / "_data"
    card = json.loads(
        (data_dir / "channels" / "piezo1.json").read_text(encoding="utf-8")
    )
    comparison = json.loads(
        (data_dir / "parameters" / "p50.json").read_text(encoding="utf-8")
    )
    audit = json.loads(
        (data_dir / "analysis" / "audit.json").read_text(encoding="utf-8")
    )
    assert all(
        "data_layers" in row
        for block in card["parameters"].values()
        for row in block["rows"]
    )
    assert all(row["data_layer"] == "computed" for row in comparison["rows"])
    assert audit["data_layer"] == "computed"
    assert (tmp_path / "_site" / "parameters" / "p50" / "index.html").is_file()


def test_migration_transition_preserves_identifiers_and_foreign_keys(engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO channel (maicdb_id, gene_symbol, organism, family) "
                "VALUES ('MAIC:CH:00001', 'PIEZO1', 'Homo sapiens', 'PIEZO')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO db_meta (key, value) "
                "VALUES ('schema_version', '0.6.0')"
            )
        )

    before_tables = set(inspect(engine).get_table_names())
    before_ids = _identifiers_and_foreign_keys(engine)
    result = migrate_data_layers(engine)
    assert result["schema_version_before"] == "0.6.0"
    assert result["schema_version_after"] == DATA_LAYER_SCHEMA_VERSION
    assert DATA_LAYER_DISCLOSURE in result["disclosures"]
    assert set(inspect(engine).get_table_names()) == before_tables | {
        "data_layer",
        "data_layer_inventory",
    }
    assert _identifiers_and_foreign_keys(engine) == before_ids


def test_migration_rejects_wrong_before_version_without_writing(engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO db_meta (key, value) "
                "VALUES ('schema_version', '0.5.0')"
            )
        )
    with pytest.raises(ValueError, match="unsupported schema migration"):
        migrate_data_layers(engine)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM data_layer_inventory")
        ).scalar_one() == 0


def test_migration_rejects_partial_inventory_without_writing(engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO db_meta (key, value) "
                "VALUES ('schema_version', '0.6.0')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO data_layer (name, value, definition) VALUES "
                "('COMPUTED', 'computed', 'fixture-only')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO data_layer_inventory "
                "(key, surface, field, layer, rule) VALUES "
                "('partial.fixture', 'fixture', 'value', 'COMPUTED', 'fixture')"
            )
        )
    with pytest.raises(ValueError, match="data_layer_inventory is not empty"):
        migrate_data_layers(engine)


@requires_db
def test_artifact_migration_contract_and_published_bytes_unchanged(tmp_path):
    original_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()
    copied = tmp_path / "maicdb.sqlite"
    shutil.copyfile(DB_PATH, copied)
    artifact_engine = create_engine(f"sqlite:///{copied}")
    reference_result = migrate_external_references(artifact_engine)
    migrate_data_layers(artifact_engine)
    with artifact_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT key, surface, field, layer, rule "
                "FROM data_layer_inventory ORDER BY key"
            )
        ).mappings().all()
        schema_version = connection.execute(
            text("SELECT value FROM db_meta WHERE key = 'schema_version'")
        ).scalar_one()
    artifact_engine.dispose()

    assert reference_result["schema_version_after"] == "0.6.0"
    assert schema_version == DATA_LAYER_SCHEMA_VERSION
    assert [tuple(row.values()) for row in rows] == [
        (entry.key, entry.surface, entry.field, entry.layer.name, entry.rule)
        for entry in sorted(DATA_LAYER_INVENTORY, key=lambda entry: entry.key)
    ]
    assert hashlib.sha256(DB_PATH.read_bytes()).hexdigest() == original_hash


def _identifiers_and_foreign_keys(engine: Engine) -> list[tuple]:
    with engine.connect() as connection:
        channel_row = connection.execute(
            text("SELECT id, maicdb_id FROM channel ORDER BY id")
        ).all()
        foreign_keys = connection.execute(
            text("PRAGMA foreign_key_list('biophysics_experiment')")
        ).all()
    return [*channel_row, *foreign_keys]

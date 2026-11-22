"""The shared inventory for value-bearing scientific outputs."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from maicdb.enums import DataLayer
from maicdb.models import Base, DataLayerInventory, DataLayerVocabulary

__all__ = [
    "DATA_LAYER_DISCLOSURE",
    "DataLayerEntry",
    "DATA_LAYER_INVENTORY",
    "DATA_LAYER_DEFINITIONS",
    "MIGRATION_SOURCE_SCHEMA_VERSION",
    "DATA_LAYER_SCHEMA_VERSION",
    "in_scope_entry",
    "ensure_data_layer_schema",
    "seed_data_layer_contract",
    "migrate_data_layers",
]


@dataclass(frozen=True)
class DataLayerEntry:
    """One value-bearing output and its auditable classification."""

    key: str
    surface: str
    field: str
    layer: DataLayer
    rule: str


DATA_LAYER_DISCLOSURE = (
    "Data layer marks source-reported, curated, and computed values; "
    "it is additive provenance and never changes the underlying fields."
)

MIGRATION_SOURCE_SCHEMA_VERSION = "0.6.0"
DATA_LAYER_SCHEMA_VERSION = "0.7.0"

DATA_LAYER_DEFINITIONS: tuple[dict, ...] = (
    {
        "name": DataLayer.SOURCE_REPORTED,
        "definition": "A value or unit serialized verbatim from its frozen source.",
    },
    {
        "name": DataLayer.CURATED,
        "definition": "A value normalized by the formal schema's curation rules.",
    },
    {
        "name": DataLayer.COMPUTED,
        "definition": "A value derived by a documented deterministic analysis rule.",
    },
)

DATA_LAYER_INVENTORY: tuple[DataLayerEntry, ...] = (
    DataLayerEntry(
        key="channel_card.value_as_reported",
        surface="channel_card",
        field="value_as_reported",
        layer=DataLayer.SOURCE_REPORTED,
        rule="Serialized from the frozen value reported by the source paper.",
    ),
    DataLayerEntry(
        key="channel_card.unit_as_reported",
        surface="channel_card",
        field="unit_as_reported",
        layer=DataLayer.SOURCE_REPORTED,
        rule="Serialized from the frozen unit reported by the source paper.",
    ),
    DataLayerEntry(
        key="channel_card.value",
        surface="channel_card",
        field="value",
        layer=DataLayer.CURATED,
        rule="The formal schema's normalized parameter value after curation.",
    ),
    DataLayerEntry(
        key="parameter_comparison.value_statistics",
        surface="parameter_comparison",
        field="min, median, max",
        layer=DataLayer.COMPUTED,
        rule="Statistics calculated from measured parameter values per gene and unit bucket.",
    ),
    DataLayerEntry(
        key="bioactivity_card.activity_value",
        surface="bioactivity_card",
        field="activity_value",
        layer=DataLayer.CURATED,
        rule="The formal schema's normalized bioactivity value after curation.",
    ),
    DataLayerEntry(
        key="provenance.value",
        surface="provenance",
        field="value",
        layer=DataLayer.CURATED,
        rule="The measurement's formal-schema value returned by the provenance lookup.",
    ),
    DataLayerEntry(
        key="analysis.audit.scores",
        surface="analysis",
        field="compliance and score values",
        layer=DataLayer.COMPUTED,
        rule="Derived by the MIMIC field-status scoring and aggregation rules.",
    ),
    DataLayerEntry(
        key="analysis.biophysics.statistics",
        surface="analysis",
        field="meta-analysis and spread outputs",
        layer=DataLayer.COMPUTED,
        rule="Calculated from the harmonized biophysics corpus by P4 modules.",
    ),
    DataLayerEntry(
        key="analysis.atlas.p_activity",
        surface="analysis",
        field="p_activity",
        layer=DataLayer.COMPUTED,
        rule="p_activity = -log10 of the activity value converted to molar units.",
    ),
    DataLayerEntry(
        key="analysis.atlas.selectivity",
        surface="analysis",
        field="selectivity gap values",
        layer=DataLayer.COMPUTED,
        rule="Calculated as the difference between two computed p_activity values.",
    ),
    DataLayerEntry(
        key="analysis.trends.counts",
        surface="analysis",
        field="publication and parameter trend counts",
        layer=DataLayer.COMPUTED,
        rule="Aggregated by the year-series and drift modules from the frozen corpus.",
    ),
)


def in_scope_entry(key: str) -> DataLayerEntry:
    """Return one inventory entry or fail loudly for an unknown key."""
    for entry in DATA_LAYER_INVENTORY:
        if entry.key == key:
            return entry
    raise KeyError(f"unknown data-layer inventory key {key!r}")


def ensure_data_layer_schema(engine: Engine) -> None:
    """Create the controlled vocabulary and inventory tables."""
    Base.metadata.create_all(
        engine,
        tables=[DataLayerVocabulary.__table__, DataLayerInventory.__table__],
        checkfirst=True,
    )


def seed_data_layer_contract(session: Session) -> dict[str, int]:
    """Insert the complete Data-layer contract without changing data values."""
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
    return {
        "vocabulary_rows": len(DATA_LAYER_DEFINITIONS),
        "inventory_rows": len(DATA_LAYER_INVENTORY),
    }


def migrate_data_layers(engine: Engine) -> dict:
    """Atomically add the Data-layer contract to a schema 0.6 artifact."""
    ensure_data_layer_schema(engine)
    counts: dict[str, int] = {}
    with engine.begin() as connection:
        before = connection.execute(
            text("SELECT value FROM db_meta WHERE key = 'schema_version'")
        ).scalar_one_or_none()
        if before != MIGRATION_SOURCE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema migration {before!r}; "
                f"expected {MIGRATION_SOURCE_SCHEMA_VERSION!r}"
            )
        existing_inventory_rows = connection.execute(
            text("SELECT COUNT(*) FROM data_layer_inventory")
        ).scalar_one()
        if existing_inventory_rows:
            raise ValueError("data_layer_inventory is not empty")
        for item in DATA_LAYER_DEFINITIONS:
            connection.execute(
                text(
                    "INSERT INTO data_layer (name, value, definition) "
                    "VALUES (:name, :value, :definition)"
                ),
                {
                    "name": item["name"].name,
                    "value": item["name"].value,
                    "definition": item["definition"],
                },
            )
        for entry in DATA_LAYER_INVENTORY:
            connection.execute(
                text(
                    "INSERT INTO data_layer_inventory "
                    "(key, surface, field, layer, rule) "
                    "VALUES (:key, :surface, :field, :layer, :rule)"
                ),
                {
                    "key": entry.key,
                    "surface": entry.surface,
                    "field": entry.field,
                    "layer": entry.layer.name,
                    "rule": entry.rule,
                },
            )
        connection.execute(
            text(
                "UPDATE db_meta SET value = :version "
                "WHERE key = 'schema_version'"
            ),
            {"version": DATA_LAYER_SCHEMA_VERSION},
        )
        counts["vocabulary_rows"] = connection.execute(
            text("SELECT COUNT(*) FROM data_layer")
        ).scalar_one()
        counts["inventory_rows"] = connection.execute(
            text("SELECT COUNT(*) FROM data_layer_inventory")
        ).scalar_one()

    return {
        "schema_version_before": before,
        "schema_version_after": DATA_LAYER_SCHEMA_VERSION,
        "rows_added": counts,
        "disclosures": [DATA_LAYER_DISCLOSURE],
    }

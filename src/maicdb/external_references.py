"""Storage, migration, and lookup helpers for semantic external references."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from sqlalchemy import select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from maicdb.enums import ExternalReferenceRelationship, SourceDb
from maicdb.models import (
    ChannelExternalReference,
    CompoundExternalReference,
    ExperimentExternalReference,
    ExternalReferenceRecord,
    StructureExternalReference,
    VariantExternalReference,
)
from maicdb.models import Base

__all__ = [
    "EXTERNAL_REFERENCE_SCHEMA_VERSION",
    "LEGACY_RELATIONSHIP_DISCLOSURE",
    "LEGACY_VERSION_DISCLOSURE",
    "SCHEMA_VERSION_DISCLOSURE",
    "COMPATIBILITY_VIEW_DDL",
    "add_external_reference",
    "all_external_references",
    "external_references_for_subject",
    "migrate_external_references",
]


EXTERNAL_REFERENCE_SCHEMA_VERSION = "0.6.0"
LEGACY_RELATIONSHIP_DISCLOSURE = (
    "Legacy external references did not record relationship semantics; "
    "migration assigns SAME_AS only where the identifier denotes the same subject."
)
LEGACY_VERSION_DISCLOSURE = (
    "Legacy external references did not record upstream resource versions; "
    "missing applicable versions remain NULL rather than being reconstructed."
)
SCHEMA_VERSION_DISCLOSURE = (
    "Schema 0.3 keeps primary identifier columns as convenience fields; "
    "subject-specific link tables are the authoritative semantic matrix."
)

_SubjectType = Literal[
    "channel", "compound", "variant", "structure", "experiment"
]

_SUBJECT_TABLES = {
    "channel": "channel_external_reference",
    "compound": "compound_external_reference",
    "variant": "variant_external_reference",
    "structure": "structure_external_reference",
    "experiment": "experiment_external_reference",
}
_SUBJECT_COLUMNS = {
    "channel": "channel_id",
    "compound": "compound_id",
    "variant": "variant_id",
    "structure": "structure_id",
    "experiment": "experiment_id",
}
_SUBJECT_MODELS = {
    "channel": ChannelExternalReference,
    "compound": CompoundExternalReference,
    "variant": VariantExternalReference,
    "structure": StructureExternalReference,
    "experiment": ExperimentExternalReference,
}
_VERSIONED_RESOURCES = {
    SourceDb.CHEMBL_TARGET,
    SourceDb.CHEMBL_MOLECULE,
    SourceDb.PUBCHEM,
}
_RESOURCE_URLS = {
    SourceDb.UNIPROT: "https://www.uniprot.org/uniprotkb/{external_id}",
    SourceDb.PDB: "https://www.rcsb.org/structure/{external_id}",
    SourceDb.CHEMBL_TARGET: "https://www.ebi.ac.uk/chembl/gcov/{external_id}",
    SourceDb.CHEMBL_MOLECULE: (
        "https://www.ebi.ac.uk/chembl/compound_report_card/{external_id}"
    ),
    SourceDb.PUBCHEM: "https://pubchem.ncbi.nlm.nih.gov/compound/{external_id}",
    SourceDb.CLINVAR: "https://www.ncbi.nlm.nih.gov/clinvar/{external_id}",
    SourceDb.DOI: "https://doi.org/{external_id}",
}


def _dedupe_references(rows: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for row in rows:
        key = (
            row["resource"],
            row["external_id"],
            row["relationship"],
            row["url"],
            row["external_version"],
        )
        if key not in seen:
            out.append(row)
            seen.add(key)
    return out


def external_references_for_experiments(
    engine: Engine, experiment_ids: list[int] | None
) -> list[dict]:
    """Aggregate contributing experiment links deterministically."""
    if not experiment_ids:
        return []
    if not _semantic_tables_present(engine):
        return []

    placeholders = ", ".join(f":id_{index}" for index in range(len(experiment_ids)))
    parameters = {f"id_{index}": value for index, value in enumerate(experiment_ids)}
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT DISTINCT r.resource, r.external_id, r.relationship, "
                "r.url, r.external_version "
                "FROM external_reference_record r "
                "JOIN experiment_external_reference subject "
                "ON subject.id = r.id "
                f"WHERE subject.experiment_id IN ({placeholders})"
            ),
            parameters,
        ).mappings()
        serialized = [
            {
                "resource": row["resource"],
                "external_id": row["external_id"],
                "relationship": row["relationship"],
                "url": row["url"],
                "external_version": row["external_version"],
            }
            for row in rows
        ]
        return _dedupe_references(serialized)
COMPATIBILITY_VIEW_DDL = """
CREATE VIEW external_reference AS
SELECT r.id, c.channel_id, cp.compound_id, v.variant_id,
       st.structure_id, e.experiment_id, r.resource, r.external_id,
       r.relationship, r.url, r.external_version, r.created_at
FROM external_reference_record r
LEFT JOIN channel_external_reference c ON c.id = r.id
LEFT JOIN compound_external_reference cp ON cp.id = r.id
LEFT JOIN variant_external_reference v ON v.id = r.id
LEFT JOIN structure_external_reference st ON st.id = r.id
LEFT JOIN experiment_external_reference e ON e.id = r.id
"""


def add_external_reference(
    session: Session,
    *,
    subject_type: _SubjectType,
    subject_id: int,
    resource: SourceDb,
    external_id: str,
    relationship: ExternalReferenceRelationship | None = None,
    external_version: str | None = None,
    allow_missing_version: bool = False,
    created_at: object | None = None,
) -> ExternalReferenceRecord:
    """Add one record and its subject-specific link."""
    if (
        resource in _VERSIONED_RESOURCES
        and not external_version
        and not allow_missing_version
    ):
        raise ValueError(f"{resource.name} requires an evidenced release version")
    if resource not in _VERSIONED_RESOURCES and external_version is not None:
        raise ValueError(f"{resource.name} does not carry a resource version")
    if resource not in _RESOURCE_URLS:
        raise ValueError(f"no canonical URL template is configured for {resource.name}")

    subject_column = _SUBJECT_COLUMNS[subject_type]
    controlled_relationship = relationship or ExternalReferenceRelationship.SAME_AS
    subject_model = _SUBJECT_MODELS[subject_type]
    subject_filter = {
        _SUBJECT_COLUMNS[subject_type]: subject_id,
        "resource": resource,
        "external_id": external_id,
        "relationship": controlled_relationship,
    }
    subject = session.scalar(
        select(subject_model).where(
            *[getattr(subject_model, name) == value for name, value in subject_filter.items()]
        )
    )
    if subject is not None:
        raise ValueError(
            "duplicate semantic external reference for subject "
            f"{subject_type} {subject_id}"
        )

    record = session.scalar(
        select(ExternalReferenceRecord).where(
            ExternalReferenceRecord.resource == resource,
            ExternalReferenceRecord.external_id == external_id,
            ExternalReferenceRecord.relationship == controlled_relationship,
        )
    )
    if record is None:
        record = ExternalReferenceRecord(
            resource=resource,
            external_id=external_id,
            relationship=controlled_relationship,
            url=_RESOURCE_URLS[resource].format(external_id=external_id),
            external_version=external_version,
            legacy_version_disclosed=allow_missing_version,
        )
        record.created_at = created_at
        session.add(record)
        session.flush()
    session.add(
        subject_model(
            id=record.id,
            resource=resource,
            external_id=external_id,
            relationship=controlled_relationship,
            **{subject_column: subject_id},
        )
    )
    session.flush()
    return record


def external_references_for_subject(
    source: Engine | Connection,
    subject_type: _SubjectType,
    subject_id: int,
) -> list[dict]:
    """Return one subject's links in deterministic public order."""
    own_connection = not isinstance(source, Connection)
    connection = source.connect() if own_connection else source
    try:
        if not _semantic_tables_present(connection):
            return []
        table = _SUBJECT_TABLES[subject_type]
        subject_column = _SUBJECT_COLUMNS[subject_type]
        rows = connection.execute(
            text(
                "SELECT r.resource, r.external_id, r.relationship, r.url, "
                "r.external_version FROM external_reference_record r "
                f"JOIN {table} subject ON subject.id = r.id "
                f"WHERE subject.{subject_column} = :subject_id "
                "ORDER BY r.resource, r.external_id, r.relationship"
            ),
            {"subject_id": subject_id},
        ).mappings()
        return [
            {
                "resource": row["resource"],
                "external_id": row["external_id"],
                "relationship": row["relationship"],
                "url": row["url"],
                "external_version": row["external_version"],
            }
            for row in rows
        ]
    finally:
        if own_connection:
            connection.close()


def all_external_references(engine: Engine) -> list[dict]:
    """Return every supported subject's links in deterministic order."""
    if not _semantic_tables_present(engine):
        return []

    queries = []
    for subject_type, table in _SUBJECT_TABLES.items():
        subject_column = _SUBJECT_COLUMNS[subject_type]
        queries.append(
            f"SELECT '{subject_type}' AS subject_type, "
            f"subject.{subject_column} AS subject_id, "
            "r.resource, r.external_id, r.relationship, r.url, "
            "r.external_version "
            f"FROM {table} subject "
            "JOIN external_reference_record r ON subject.id = r.id"
        )
    query = " UNION ALL ".join(queries) + (
        " ORDER BY subject_type, subject_id, resource, external_id, "
        "relationship"
    )

    with engine.connect() as connection:
        rows = connection.execute(
            text(query)
        ).mappings()
        return [
            {
                "subject_type": row["subject_type"],
                "subject_id": row["subject_id"],
                "resource": row["resource"],
                "external_id": row["external_id"],
                "relationship": row["relationship"],
                "url": row["url"],
                "external_version": row["external_version"],
            }
            for row in rows
        ]


def _semantic_tables_present(source: Engine | Connection) -> bool:
    connection = source.connect() if isinstance(source, Engine) else source
    own_connection = isinstance(source, Engine)
    try:
        return bool(
            connection.exec_driver_sql(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE name = 'external_reference_record' AND type = 'table'"
            ).scalar_one()
        )
    finally:
        if own_connection:
            connection.close()


def migrate_external_references(engine: Engine) -> dict:
    """Atomically migrate a schema 0.5 artifact to the semantic matrix."""
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        before = connection.execute(
            text("SELECT value FROM db_meta WHERE key = 'schema_version'")
        ).scalar_one_or_none()
        if before != "0.5.0":
            raise ValueError(
                f"unsupported schema migration {before!r}; expected '0.5.0'"
            )
        has_legacy_table = connection.execute(
            text(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type = 'table' AND name = 'external_reference'"
            )
        ).scalar_one()
        if not has_legacy_table:
            raise ValueError("legacy table external_reference is missing")
        legacy_rows = list(
            connection.execute(
                text(
                    "SELECT entity_type, entity_id, source_db, external_id, url "
                    "FROM external_reference ORDER BY id"
                )
            )
        )
        for values in legacy_rows:
            _migrate_row(connection, values)
        connection.execute(text("DROP TABLE external_reference"))
        connection.exec_driver_sql(COMPATIBILITY_VIEW_DDL)
        connection.execute(
            text(
                "UPDATE db_meta SET value = :version "
                "WHERE key = 'schema_version'"
            ),
            {"version": EXTERNAL_REFERENCE_SCHEMA_VERSION},
        )

    missing_versions = sum(
        1
        for _entity_type, _entity_id, source_db, _external_id, _url
        in legacy_rows
        if SourceDb[source_db] in _VERSIONED_RESOURCES
    )
    return {
        "schema_version_before": before,
        "schema_version_after": EXTERNAL_REFERENCE_SCHEMA_VERSION,
        "legacy_rows_examined": len(legacy_rows),
        "semantic_rows_created": len(legacy_rows),
        "legacy_relationships_disclosed": len(legacy_rows),
        "missing_applicable_versions": missing_versions,
        "disclosures": [
            LEGACY_RELATIONSHIP_DISCLOSURE,
            LEGACY_VERSION_DISCLOSURE,
        ],
    }


def _migrate_row(connection, values: tuple) -> None:
    entity_type, entity_id, source_db, external_id, url = values
    subject_type = _legacy_subject_type(entity_type)
    resource = SourceDb[source_db]
    record_id = connection.execute(
        text(
            "SELECT id FROM external_reference_record "
            "WHERE resource = :resource AND external_id = :external_id "
            "AND relationship = 'SAME_AS'"
        ),
        {
            "resource": resource.name,
            "external_id": external_id,
        },
    ).scalar_one_or_none()
    if record_id is None:
        result = connection.execute(
            text(
                "INSERT INTO external_reference_record "
                "(resource, external_id, relationship, url, external_version, "
                "legacy_version_disclosed) VALUES (:resource, :external_id, "
                "'SAME_AS', :url, :external_version, 1)"
            ),
            {
                "resource": resource.name,
                "external_id": external_id,
                "url": url or _RESOURCE_URLS.get(resource, "").format(
                    external_id=external_id
                ),
                "external_version": _migrated_version(resource),
            },
        )
        record_id = int(result.lastrowid)
    table = _SUBJECT_TABLES[subject_type]
    subject_column = _SUBJECT_COLUMNS[subject_type]
    connection.execute(
        text(
            f"INSERT INTO {table} "
            "(id, resource, external_id, relationship, "
            f"{subject_column}) VALUES (:record_id, :resource, :external_id, "
            "'SAME_AS', :subject_id)"
        ),
        {
            "record_id": record_id,
            "resource": resource.name,
            "external_id": external_id,
            "subject_id": entity_id,
        },
    )


def _legacy_subject_type(entity_type: str) -> _SubjectType:
    if entity_type == "BIOPHYSICS_EXPERIMENT":
        return "experiment"
    if entity_type.lower() in _SUBJECT_TABLES:
        return entity_type.lower()  # type: ignore[return-value]
    raise ValueError(f"unsupported legacy external-reference subject {entity_type!r}")


def _migrated_version(_resource: SourceDb) -> str | None:
    # Legacy rows carried no release marker; NULL preserves the missing fact.
    return None

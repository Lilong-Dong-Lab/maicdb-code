"""Compound-channel relationships and normalized parameter provenance."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from maicdb.accessions import AccessionGenerator, AccessionPrefix
from maicdb.enums import (
    ActivityType,
    CompoundChannelDirection,
    CompoundChannelRole,
    CompoundType,
    ConcentrationResponseSemantics,
)
from maicdb.models import (
    Base,
    Bioactivity,
    Compound,
    CompoundChannelRelationship,
)

__all__ = [
    "COMPOUND_RELATIONSHIP_SCHEMA_VERSION",
    "COMPOUND_RELATIONSHIP_DISCLOSURE",
    "ensure_compound_relationship_schema",
    "migrate_compound_relationships",
    "relationships_for_bioactivity",
]


COMPOUND_RELATIONSHIP_SCHEMA_VERSION = "0.8.0"
MIGRATION_SOURCE_SCHEMA_VERSION = "0.7.0"
COMPOUND_RELATIONSHIP_DISCLOSURE = (
    "Compound-channel relationship records are authoritative; legacy "
    "compound_type remains a documented convenience and migration field."
)
_ROLE_FROM_LEGACY = {
    CompoundType.ACTIVATOR: CompoundChannelRole.ACTIVATOR,
    CompoundType.INHIBITOR_BLOCKER: CompoundChannelRole.INHIBITOR_BLOCKER,
    CompoundType.INHIBITOR: CompoundChannelRole.INHIBITOR_BLOCKER,
    CompoundType.ANTAGONIST: CompoundChannelRole.ANTAGONIST,
    CompoundType.POTENTIATOR: CompoundChannelRole.POTENTIATOR,
    CompoundType.UNKNOWN: CompoundChannelRole.UNCLASSIFIED,
    CompoundType.UNCLASSIFIED: CompoundChannelRole.UNCLASSIFIED,
}
_ROLE_OBSERVED_ACTIVITY_TYPES = {
    ActivityType.AGONIST_ACTIVITY.value: CompoundChannelRole.ACTIVATOR,
    ActivityType.INHIBITION.value: CompoundChannelRole.INHIBITOR_BLOCKER,
}
def ensure_compound_relationship_schema(engine: Engine) -> None:
    """Create the schema 0.8 relationship table without changing data values."""
    Base.metadata.create_all(
        engine,
        tables=[CompoundChannelRelationship.__table__],
        checkfirst=True,
    )


def _next_relationship_accession(session: Session) -> str:
    highest = max(
        session.scalars(select(CompoundChannelRelationship.maicdb_id)),
        key=lambda accession: int(accession.rsplit(":", 1)[-1]),
        default=None,
    )
    number = int(highest.rsplit(":", 1)[-1]) if highest else 0
    return AccessionGenerator(
        {AccessionPrefix.COMPOUND_CHANNEL_RELATIONSHIP: number}
    ).next(AccessionPrefix.COMPOUND_CHANNEL_RELATIONSHIP)


def _assay_context(assays: list[str | None]) -> str | None:
    values = sorted({value.strip() for value in assays if value and value.strip()})
    if not values:
        return None
    return " | ".join(values)


def _role_for(
    legacy_role: CompoundChannelRole | None,
    observed_roles: set[CompoundChannelRole],
) -> tuple[CompoundChannelRole, str | None]:
    roles = set(observed_roles)
    if legacy_role is not None:
        roles.add(legacy_role)
    if len(roles) > 1:
        return (
            CompoundChannelRole.CONFLICT,
            "Conflicting legacy compound labels: "
            + "; ".join(sorted(role.name for role in roles))
            + ". No source classification was overwritten.",
        )
    if not roles:
        return CompoundChannelRole.UNCLASSIFIED, None
    role = roles.pop()
    disclosure = None
    if role == CompoundChannelRole.UNCLASSIFIED:
        disclosure = (
            "Legacy relationship semantics were not recorded; the relationship "
            "is explicitly unclassified."
        )
    return role, disclosure


def _relationship_payload(session: Session) -> dict[tuple[int, int], dict]:
    compounds = {
        compound.id: compound
        for compound in session.scalars(select(Compound).order_by(Compound.id))
    }
    fact_rows = list(
        session.execute(
            select(
                Bioactivity.compound_id,
                Bioactivity.channel_id,
                Bioactivity.assay_description,
                Bioactivity.activity_type,
                Bioactivity.relation,
                Bioactivity.activity_value,
            ).order_by(Bioactivity.maicdb_id)
        ).mappings()
    )
    contexts: dict[tuple[int, int], list[str | None]] = defaultdict(list)
    observed_roles: dict[tuple[int, int], set[CompoundChannelRole]] = defaultdict(set)
    for row in fact_rows:
        key = (row.compound_id, row.channel_id)
        contexts[key].append(row.assay_description)
        if row.activity_type is not None:
            expected_role = _ROLE_OBSERVED_ACTIVITY_TYPES.get(
                row.activity_type.value
            )
            if expected_role is not None:
                observed_roles[key].add(expected_role)
    pairs = {(row.compound_id, row.channel_id) for row in fact_rows}
    payload = {}
    for compound_id, channel_id in sorted(pairs):
        compound = compounds[compound_id]
        legacy_role = _ROLE_FROM_LEGACY.get(compound.compound_type)
        key = (compound_id, channel_id)
        role, conflict = _role_for(legacy_role, observed_roles[key])
        disclosure = (
            conflict
            if conflict is not None
            else (
                "Legacy relationship semantics were not recorded; the "
                "relationship is explicitly unclassified."
                if role == CompoundChannelRole.UNCLASSIFIED
                else None
            )
        )
        payload[key] = {
            "assay_context": _assay_context(contexts[key]),
            "role": role,
            "disclosure": disclosure,
        }
    return payload


def migrate_compound_relationships(engine: Engine) -> dict[str, int | str]:
    """Atomically materialize relationship records from legacy signals."""
    ensure_compound_relationship_schema(engine)
    with engine.begin() as connection:
        before = connection.execute(
            text("SELECT value FROM db_meta WHERE key = 'schema_version'")
        ).scalar_one_or_none()
        if before not in {
            MIGRATION_SOURCE_SCHEMA_VERSION,
            COMPOUND_RELATIONSHIP_SCHEMA_VERSION,
        }:
            raise ValueError(
                f"unsupported schema migration {before!r}; "
                f"expected {COMPOUND_RELATIONSHIP_SCHEMA_VERSION!r}"
            )
        with Session(connection) as session:
            existing = set(
                session.execute(
                    select(
                        CompoundChannelRelationship.compound_id,
                        CompoundChannelRelationship.channel_id,
                        CompoundChannelRelationship.role,
                        CompoundChannelRelationship.direction,
                    )
                ).all()
            )
            fact_rows = set(
                session.execute(
                    select(Bioactivity.compound_id, Bioactivity.channel_id)
                ).all()
            )
            bioactivity_pairs = set(fact_rows)
            payload = _relationship_payload(session)
            relationships_created = 0
            conflicts = 0
            for (compound_id, channel_id), values in payload.items():
                role = values["role"]
                direction = CompoundChannelDirection.COMPOUND_TO_CHANNEL
                key = (compound_id, channel_id, role, direction)
                if key in existing:
                    continue
                concentration_response = (
                    ConcentrationResponseSemantics.FULL_CURVE
                    if (compound_id, channel_id) in fact_rows
                    else ConcentrationResponseSemantics.NOT_APPLICABLE
                )
                relationship = CompoundChannelRelationship(
                    maicdb_id=_next_relationship_accession(session),
                    compound_id=compound_id,
                    channel_id=channel_id,
                    role=role,
                    direction=direction,
                    assay_context=values["assay_context"],
                    concentration_response=concentration_response,
                    disclosure=values["disclosure"],
                )
                session.add(relationship)
                session.flush()
                existing.add(key)
                relationships_created += 1
                if role == CompoundChannelRole.CONFLICT:
                    conflicts += 1
            for compound_id, channel_id in bioactivity_pairs:
                session.execute(
                    select(Bioactivity.id).where(
                        Bioactivity.compound_id == compound_id,
                        Bioactivity.channel_id == channel_id,
                    )
                )
            session.commit()
            connection.execute(
                text(
                    "INSERT INTO db_meta (key, value) VALUES "
                    "('schema_version', :version) ON CONFLICT(key) DO UPDATE "
                    "SET value = excluded.value"
                ),
                {"version": COMPOUND_RELATIONSHIP_SCHEMA_VERSION},
            )

    return {
        "schema_version_before": before,
        "schema_version_after": COMPOUND_RELATIONSHIP_SCHEMA_VERSION,
        "rows_examined": len(bioactivity_pairs),
        "bioactivity_rows_covered": len(bioactivity_pairs),
        "relationships_created": relationships_created,
        "conflicts": conflicts,
    }


def relationships_for_bioactivity(
    engine, facts: list[tuple[int, int]]
) -> dict[tuple[int, int], dict | None]:
    """Resolve the authoritative relationship for each bioactivity row."""
    facts = sorted(set(facts))
    if not facts:
        return {}
    keys = sorted(set(facts))
    out: dict[tuple[int, int], dict | None] = {key: None for key in keys}
    compound_ids = sorted({compound_id for compound_id, _channel_id in keys})
    channel_ids = sorted({channel_id for _compound_id, channel_id in keys})
    if not compound_ids or not channel_ids:
        return out
    with engine.connect() as connection:
        table_exists = inspect(connection).has_table(
            "compound_channel_relationship"
        )
    if not table_exists:
        return out
    with Session(engine) as session:
        relationships = list(
            session.scalars(
                select(CompoundChannelRelationship).where(
                    CompoundChannelRelationship.compound_id.in_(compound_ids),
                    CompoundChannelRelationship.channel_id.in_(channel_ids),
                )
            )
        )
        relationships.sort(
            key=lambda relationship: (
                relationship.compound_id,
                relationship.channel_id,
                relationship.id,
            )
        )
        for relationship in relationships:
            key = (relationship.compound_id, relationship.channel_id)
            if key in out and out[key] is None:
                out[key] = {
                    "maicdb_id": relationship.maicdb_id,
                    "role": relationship.role.name,
                    "direction": relationship.direction.name,
                    "assay_context": relationship.assay_context,
                    "concentration_response": (
                        relationship.concentration_response.name
                    ),
                    "disclosure": relationship.disclosure,
                }
    return out

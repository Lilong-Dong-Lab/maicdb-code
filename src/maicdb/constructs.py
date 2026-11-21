"""Construct migration and read-side traversal payloads."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from maicdb.accessions import AccessionGenerator, AccessionPrefix
from maicdb.models import (
    BiophysicsExperiment,
    Construct,
    ConstructVariant,
    DbMeta,
    ExperimentConstruct,
    Publication,
    Structure,
    Variant,
)

__all__ = [
    "CONSTRUCT_SCHEMA_VERSION",
    "SCHEMA_TRANSITION_DISCLOSURE",
    "construct_page",
    "construct_payloads_for_experiments",
    "construct_traversals_for_experiments",
    "constructs_for_experiment",
    "constructs_for_variant",
    "ensure_construct_schema",
    "experiments_for_construct",
    "migrate_construct_links",
    "variant_construct_page",
]

CONSTRUCT_SCHEMA_VERSION = "0.4.0"
SCHEMA_TRANSITION_DISCLOSURE = (
    "Construct links are authoritative traversal relationships; direct "
    "experiment variant and structure columns remain compatibility bridges."
)


def _scalar_text(value: object) -> str:
    return "" if value is None else str(value)


def _construct_key(row: BiophysicsExperiment) -> tuple[int, int | None, str]:
    return (
        row.channel_id,
        row.structure_id,
        _scalar_text(row.expression_system),
    )


def _construct_key_for_construct(
    construct: Construct,
) -> tuple[int, int | None, str]:
    return (
        construct.channel_id,
        construct.structure_id,
        _scalar_text(construct.expression_design),
    )


def _next_construct_accession(session: Session) -> str:
    highest = max(
        session.scalars(select(Construct.maicdb_id)),
        key=lambda accession: int(accession.rsplit(":", 1)[-1]),
        default=None,
    )
    number = int(highest.rsplit(":", 1)[-1]) if highest else 0
    return AccessionGenerator({AccessionPrefix.CONSTRUCT: number}).next(
        AccessionPrefix.CONSTRUCT
    )


def ensure_construct_schema(session: Session) -> str:
    """Return the pre-migration schema version; loader owns Construct DDL."""
    before = session.scalar(
        select(DbMeta.value).where(DbMeta.key == "schema_version")
    )
    return str(before or "")


def _record_schema_transition(session: Session, schema_before: str) -> None:
    if schema_before != CONSTRUCT_SCHEMA_VERSION:
        session.merge(DbMeta(key="schema_version", value=CONSTRUCT_SCHEMA_VERSION))


def migrate_construct_links(session: Session) -> dict[str, int | str]:
    """Migrate legacy direct links through lossless Construct records."""
    schema_before = ensure_construct_schema(session)
    constructs_by_key: dict[tuple[int, int | None, str], Construct] = {
        _construct_key_for_construct(construct): construct
        for construct in session.scalars(select(Construct))
    }
    existing_variant_pairs = set(
        session.execute(
            select(ConstructVariant.construct_id, ConstructVariant.variant_id)
        ).all()
    )
    existing_experiment_pairs = set(
        session.execute(
            select(
                ExperimentConstruct.experiment_id,
                ExperimentConstruct.construct_id,
            )
        ).all()
    )
    rows = list(
        session.scalars(
            select(BiophysicsExperiment)
            .where(
                BiophysicsExperiment.variant_id.is_not(None)
                | BiophysicsExperiment.structure_id.is_not(None)
            )
            .order_by(BiophysicsExperiment.maicdb_id)
        )
    )
    constructs_created = 0
    variant_links_created = 0
    experiment_links_created = 0
    for row in rows:
        key = _construct_key(row)
        construct = constructs_by_key.get(key)
        if construct is None:
            construct = Construct(
                maicdb_id=_next_construct_accession(session),
                channel_id=row.channel_id,
                structure_id=row.structure_id,
                expression_design=row.expression_system,
                source_db=row.source_db,
                collected_date=row.collected_date,
                publication_id=row.publication_id,
            )
            session.add(construct)
            session.flush()
            constructs_by_key[key] = construct
            constructs_created += 1
        if (
            row.variant_id is not None
            and (construct.id, row.variant_id) not in existing_variant_pairs
        ):
            session.add(
                ConstructVariant(
                    construct_id=construct.id,
                    variant_id=row.variant_id,
                )
            )
            existing_variant_pairs.add((construct.id, row.variant_id))
            variant_links_created += 1
        if (row.id, construct.id) not in existing_experiment_pairs:
            session.add(
                ExperimentConstruct(
                    experiment_id=row.id,
                    construct_id=construct.id,
                )
            )
            existing_experiment_pairs.add((row.id, construct.id))
            experiment_links_created += 1
    session.flush()
    _record_schema_transition(session, schema_before)
    session.flush()
    return {
        "schema_version_before": schema_before,
        "schema_version_after": CONSTRUCT_SCHEMA_VERSION,
        "constructs_created": constructs_created,
        "variant_links_created": variant_links_created,
        "experiment_links_created": experiment_links_created,
        "rows_examined": len(rows),
    }


def constructs_for_experiment(
    session: Session,
    experiment_id: int,
) -> list[Construct]:
    """Return all Constructs measured by one experiment."""
    return list(
        session.scalars(
            select(Construct)
            .join(ExperimentConstruct)
            .where(ExperimentConstruct.experiment_id == experiment_id)
            .order_by(Construct.maicdb_id)
        )
    )


def constructs_for_variant(session: Session, variant_id: int) -> list[Construct]:
    """Return all Constructs containing one variant."""
    return list(
        session.scalars(
            select(Construct)
            .join(ConstructVariant)
            .where(ConstructVariant.variant_id == variant_id)
            .order_by(Construct.maicdb_id)
        )
    )


def experiments_for_construct(
    session: Session,
    construct_id: int,
) -> list[BiophysicsExperiment]:
    """Return all experiments measuring one Construct."""
    return list(
        session.scalars(
            select(BiophysicsExperiment)
            .join(ExperimentConstruct)
            .where(ExperimentConstruct.construct_id == construct_id)
            .order_by(BiophysicsExperiment.maicdb_id)
        )
    )


def _construct_payload(construct: dict, variants_by_id=None) -> dict:
    if not isinstance(construct, dict):
        construct = {
            "maicdb_id": construct.maicdb_id,
            "channel_id": construct.channel_id,
            "structure_id": construct.structure_id,
            "tags": construct.tags,
            "truncations": construct.truncations,
            "mutation_set": construct.mutation_set,
            "expression_design": construct.expression_design,
            "notes": construct.notes,
            "source_db": str(getattr(construct.source_db, "name", construct.source_db)),
            "variants": construct.variants,
        }
    if variants_by_id is None:
        variants_by_id = {
            variant.id: _variant_payload(variant) for variant in construct["variants"]
        }
    if variants_by_id is None:
        variants_by_id = {}
    return {
        "maicdb_id": construct["maicdb_id"],
        "channel_id": construct["channel_id"],
        "structure_id": construct["structure_id"],
        "structure": construct.get("structure"),
        "variant_ids": sorted(variants_by_id),
        "variants": [variants_by_id[id] for id in sorted(variants_by_id)],
        "tags": construct["tags"],
        "truncations": construct["truncations"],
        "mutation_set": construct["mutation_set"],
        "expression_design": construct["expression_design"],
        "notes": construct["notes"],
        "source_db": construct["source_db"],
        "publication": construct.get("publication"),
    }


def _structure_payload(structure: Structure) -> dict:
    return {
        "id": structure.id,
        "maicdb_id": structure.maicdb_id,
        "pdb_id": structure.pdb_id,
        "title": structure.title,
    }


def _variant_payload(variant: Variant) -> dict:
    return {
        "id": variant.id,
        "maicdb_id": variant.maicdb_id,
        "hgvs_protein": variant.hgvs_protein,
        "mutation_short": variant.mutation_short,
        "position": variant.position,
    }


def _experiment_payload(experiment: BiophysicsExperiment) -> dict:
    return {
        "id": experiment.id,
        "maicdb_id": experiment.maicdb_id,
        "measurement_id": experiment.measurement_id,
        "experiment_label": experiment.experiment_label,
    }


def construct_payloads_for_experiments(
    engine: Engine,
    experiment_ids: list[int],
) -> dict[int, list[dict]]:
    """Return deterministic Construct payloads keyed by experiment id."""
    resolved: dict[int, list[dict]] = {id: [] for id in experiment_ids}
    if not experiment_ids:
        return resolved
    with engine.connect() as conn:
        table_names = set(inspect(conn).get_table_names())
        if not {"construct", "construct_variant", "experiment_construct"}.issubset(
            table_names
        ):
            return resolved
        links = conn.execute(
            select(ExperimentConstruct.experiment_id, Construct.id)
            .join(Construct, ExperimentConstruct.construct_id == Construct.id)
            .where(ExperimentConstruct.experiment_id.in_(experiment_ids))
            .order_by(ExperimentConstruct.experiment_id, Construct.maicdb_id)
        ).all()
        construct_ids = sorted({construct_id for _, construct_id in links})
        if not construct_ids:
            return resolved
        variants = defaultdict(list)
        variant_rows = conn.execute(
            select(ConstructVariant.construct_id, Variant)
            .join(Variant, ConstructVariant.variant_id == Variant.id)
            .where(ConstructVariant.construct_id.in_(construct_ids))
            .order_by(ConstructVariant.construct_id, Variant.maicdb_id)
        ).all()
        variants_by_id: dict[int, dict] = {}
        for row in variant_rows:
            construct_id = row[0]
            variant_payload = {
                "id": row[1],
                "maicdb_id": row[2],
                "hgvs_protein": row[4],
                "mutation_short": row[6],
                "position": row[7],
            }
            variants_by_id[variant_payload["id"]] = variant_payload
            variants[construct_id].append(variant_payload)
        constructs = {
            row[0]: {
                "maicdb_id": row[1],
                "channel_id": row[2],
                "structure_id": row[3],
                "tags": row[5],
                "truncations": row[6],
                "mutation_set": row[7],
                "expression_design": row[8],
                "notes": row[9],
                "source_db": str(getattr(row[10], "name", row[10])),
                "publication_id": row[12],
            }
            for row in conn.execute(
                select(Construct)
                .where(Construct.id.in_(construct_ids))
                .order_by(Construct.maicdb_id)
            )
        }
        structure_ids = {
            construct["structure_id"]
            for construct in constructs.values()
            if construct["structure_id"] is not None
        }
        structures = {
            row[Structure.id]: _structure_payload(row._mapping)
            for row in conn.execute(
                select(Structure).where(Structure.id.in_(structure_ids))
            )
        }
        publication_ids = {
            construct["publication_id"]
            for construct in constructs.values()
            if construct["publication_id"] is not None
        }
        publications = {
            row[Publication.id]: {
                "id": row[Publication.id],
                "doi": row[Publication.doi],
                "title": row[Publication.title],
            }
            for row in conn.execute(
                select(Publication).where(Publication.id.in_(publication_ids))
            )
        }
        payload_by_id: dict[int, dict] = {}
        for construct_id, construct in constructs.items():
            variant_payloads = {
                variant["id"]: variant for variant in variants[construct_id]
            }
            payload = _construct_payload(
                construct,
                variants_by_id=variant_payloads,
            )
            payload["structure"] = (
                structures[construct["structure_id"]]
                if construct["structure_id"] is not None
                else None
            )
            payload["publication"] = (
                publications.get(construct["publication_id"])
                if construct["publication_id"] is not None
                else None
            )
            payload_by_id[construct_id] = payload
        for experiment_id, construct_id in links:
            resolved[experiment_id].append(payload_by_id[construct_id])
    return resolved


def construct_traversals_for_experiments(
    engine: Engine,
    experiment_ids: list[int],
) -> dict[int, list[dict]]:
    """Return variant → Construct paths for each experiment id."""
    return {
        experiment_id: [
            {
                "construct": construct,
                "variants": construct["variants"],
            }
            for construct in construct_payloads_for_experiments(
                engine,
                [experiment_id],
            )[experiment_id]
        ]
        for experiment_id in experiment_ids
    }


def construct_page(engine: Engine, accession: str) -> dict | None:
    """Return one Construct and its experiment/variant traversal."""
    with Session(engine) as session:
        construct = session.scalar(
            select(Construct).where(Construct.maicdb_id == accession)
        )
        if construct is None:
            return None
        payload = _construct_payload(construct)
        payload["experiments"] = [
            _experiment_payload(experiment)
            for experiment in experiments_for_construct(session, construct.id)
        ]
        payload["variant_construct_experiments"] = [
            {
                "variant": variant,
                "construct_id": payload["maicdb_id"],
                "experiments": payload["experiments"],
            }
            for variant in payload["variants"]
        ]
        payload["disclosure"] = SCHEMA_TRANSITION_DISCLOSURE
        return payload


def variant_construct_page(engine: Engine, variant_id: int) -> dict | None:
    """Return one variant, its Constructs, and all reached experiments."""
    with Session(engine) as session:
        variant = session.get(Variant, variant_id)
        if variant is None:
            return None
        constructs = constructs_for_variant(session, variant_id)
        construct_payloads = [_construct_payload(construct) for construct in constructs]
        traversals = []
        for construct, payload in zip(constructs, construct_payloads, strict=True):
            traversals.append(
                {
                    "construct": payload,
                    "experiments": [
                        _experiment_payload(experiment)
                        for experiment in experiments_for_construct(
                            session,
                            construct.id,
                        )
                    ],
                }
            )
        return {
            "variant": _variant_payload(variant),
            "constructs": construct_payloads,
            "construct_experiments": traversals,
            "disclosure": SCHEMA_TRANSITION_DISCLOSURE,
        }

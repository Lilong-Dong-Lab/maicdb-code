"""Structure-function residue mapping and read-side traversal payloads."""

from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from maicdb.accessions import AccessionGenerator, AccessionPrefix
from maicdb.enums import (
    EvidenceSubjectType,
    EvidenceReviewState,
    EvidenceType,
    MappingSupport,
    ResidueNumberSystem,
    ResidueRole,
)
from maicdb.evidence import _next_evidence_accession
from maicdb.models import (
    BiophysicsExperiment,
    Construct,
    ConstructVariant,
    DbMeta,
    EvidenceItem,
    EvidenceSubject,
    ExperimentConstruct,
    Structure,
    StructureResidue,
    StructureVariantLocation,
    Variant,
)

__all__ = [
    "STRUCTURE_FUNCTION_SCHEMA_VERSION",
    "STRUCTURE_FUNCTION_DISCLOSURE",
    "migrate_structure_function",
    "structure_function_page",
    "variant_structure_locations",
]

STRUCTURE_FUNCTION_SCHEMA_VERSION = "0.7.0"
STRUCTURE_FUNCTION_DISCLOSURE = (
    "Structure construction mutations are extracted from deposited PDB titles; "
    "residue-level PDB coordinates remain null until SIFTS mappings are curated."
)
_TITLE_MUTATION = re.compile(r"(?<![A-Z0-9])([A-Z]\d+(?:[A-Z]|DEL|STOP))(?![A-Z0-9])")


def _accession(session: Session, prefix: AccessionPrefix, model) -> str:
    highest = max(
        session.scalars(select(model.maicdb_id)),
        key=lambda accession: int(accession.rsplit(":", 1)[-1]),
        default=None,
    )
    number = int(highest.rsplit(":", 1)[-1]) if highest else 0
    return AccessionGenerator({prefix: number}).next(prefix)


def _position(mutation: str) -> int | None:
    match = re.search(r"\d+", mutation)
    return int(match.group()) if match else None


def _title_mutation(title: str | None) -> str | None:
    if title is None:
        return None
    match = _TITLE_MUTATION.search(title.upper())
    if match is None:
        return None
    mutation = match.group(1)
    return mutation[:-3] + mutation[-3:].title() if mutation.endswith(("DEL", "STOP")) else mutation


def migrate_structure_function(session: Session) -> dict[str, int | str]:
    """Materialize title-derived construction mutations losslessly."""
    schema_before = session.scalar(
        select(DbMeta.value).where(DbMeta.key == "schema_version")
    )
    existing = set(
        session.execute(
            select(
                StructureVariantLocation.variant_id,
                StructureVariantLocation.structure_id,
            )
        ).all()
    )
    residues_created = 0
    locations_created = 0
    evidence_created = 0
    variants_created = 0
    linked_structures = set(
        session.execute(
            select(EvidenceSubject.subject_id).where(
                EvidenceSubject.subject_type == EvidenceSubjectType.STRUCTURE
            )
        ).scalars()
    )
    variants_by_mutation: dict[tuple[int, str], list[Variant]] = defaultdict(list)
    for variant in session.scalars(select(Variant)):
        variants_by_mutation[(variant.channel_id, variant.mutation_short or "")].append(variant)
    for structure in session.scalars(select(Structure).order_by(Structure.maicdb_id)):
        mutation = _title_mutation(structure.title)
        if mutation is None:
            continue
        key = (structure.channel_id, mutation)
        candidates = variants_by_mutation[key]
        if candidates:
            variant = sorted(candidates, key=lambda item: item.maicdb_id)[0]
        else:
            variant = Variant(
                maicdb_id=_accession(session, AccessionPrefix.VARIANT, Variant),
                channel_id=structure.channel_id,
                mutation_short=mutation,
                position=_position(mutation),
                source_db=structure.source_db,
                created_at=structure.created_at,
            )
            session.add(variant)
            session.flush()
            variants_by_mutation[key].append(variant)
            variants_created += 1
        if (variant.id, structure.id) in existing:
            continue
        position = _position(mutation)
        residue = None
        if position is not None:
            residue = session.scalar(
                select(StructureResidue).where(
                    StructureResidue.structure_id == structure.id,
                    StructureResidue.number_system == ResidueNumberSystem.UNIPROT,
                    StructureResidue.residue_number == position,
                )
            )
            if residue is None:
                residue = StructureResidue(
                    maicdb_id=_accession(
                        session,
                        AccessionPrefix.STRUCTURE_RESIDUE,
                        StructureResidue,
                    ),
                    structure_id=structure.id,
                    channel_id=structure.channel_id,
                    number_system=ResidueNumberSystem.UNIPROT,
                    residue_number=position,
                    residue_role=ResidueRole.CONSTRUCTION_MUTATION,
                    notes=f"Deposited structure title names {mutation}.",
                    created_at=structure.created_at,
                )
                session.add(residue)
                session.flush()
                residues_created += 1
        location = StructureVariantLocation(
            maicdb_id=_accession(
                session,
                AccessionPrefix.STRUCTURE_VARIANT_LOCATION,
                StructureVariantLocation,
            ),
            variant_id=variant.id,
            structure_id=structure.id,
            uniprot_residue_id=residue.id if residue is not None else None,
            pdb_residue_id=None,
            structural_region=None,
            support=MappingSupport.TITLE_MUTATION
            if residue is not None
            else MappingSupport.UNMAPPED,
            notes=f"Construction mutation {mutation} is named in the PDB title.",
            created_at=structure.created_at,
        )
        session.add(location)
        existing.add((variant.id, structure.id))
        locations_created += 1
        if structure.id not in linked_structures:
            item = EvidenceItem(
                maicdb_id=_next_evidence_accession(session),
                claim=f"{structure.pdb_id or structure.maicdb_id}: deposited title names construction mutation {mutation}",
                source="PDB",
                publication_id=structure.publication_id,
                quote=structure.title,
                evidence_type=EvidenceType.STRUCTURE,
                curator_note="Construction mutation extracted from the deposited PDB title.",
                review_state=EvidenceReviewState.UNREVIEWED,
                created_at=structure.created_at,
            )
            session.add(item)
            session.flush()
            session.add(
                EvidenceSubject(
                    evidence_item_id=item.id,
                    subject_type=EvidenceSubjectType.STRUCTURE,
                    subject_id=structure.id,
                )
            )
            linked_structures.add(structure.id)
            evidence_created += 1
    session.flush()
    session.merge(DbMeta(key="schema_version", value=STRUCTURE_FUNCTION_SCHEMA_VERSION))
    return {
        "schema_version_before": str(schema_before or ""),
        "schema_version_after": STRUCTURE_FUNCTION_SCHEMA_VERSION,
        "variants_created": variants_created,
        "residues_created": residues_created,
        "locations_created": locations_created,
        "evidence_created": evidence_created,
    }


def _tables_available(engine: Engine) -> bool:
    with engine.connect() as conn:
        return {"structure_residue", "structure_variant_location"}.issubset(
            set(inspect(conn).get_table_names())
        )


def _evidence_for_structure(engine: Engine, structure_id: int) -> list[dict]:
    with Session(engine) as session:
        rows = session.execute(
            select(EvidenceItem)
            .join(EvidenceSubject, EvidenceItem.id == EvidenceSubject.evidence_item_id)
            .where(
                EvidenceSubject.subject_type == EvidenceSubjectType.STRUCTURE,
                EvidenceSubject.subject_id == structure_id,
            )
            .order_by(EvidenceItem.maicdb_id)
        ).scalars()
        return [
            {
                "maicdb_id": item.maicdb_id,
                "claim": item.claim,
                "publication_id": item.publication_id,
                "quote": item.quote,
                "location": item.location,
                "evidence_type": str(getattr(item.evidence_type, "name", item.evidence_type)),
                "confidence": str(getattr(item.confidence, "name", item.confidence)),
            }
            for item in rows
        ]


def _constructs_for_variant(session: Session, variant_id: int) -> list[Construct]:
    return list(
        session.scalars(
            select(Construct)
            .join(ConstructVariant, ConstructVariant.construct_id == Construct.id)
            .where(ConstructVariant.variant_id == variant_id)
            .order_by(Construct.maicdb_id)
        )
    )


def _experiments_for_constructs(
    session: Session, construct_ids: list[int]
) -> list[BiophysicsExperiment]:
    if not construct_ids:
        return []
    return list(
        session.scalars(
            select(BiophysicsExperiment)
            .join(
                ExperimentConstruct,
                ExperimentConstruct.experiment_id == BiophysicsExperiment.id,
            )
            .where(ExperimentConstruct.construct_id.in_(construct_ids))
            .order_by(BiophysicsExperiment.maicdb_id)
        )
    )


def variant_structure_locations(engine: Engine, variant_id: int) -> list[dict]:
    """Return structure-function traversal payloads for one variant."""
    if not _tables_available(engine):
        return []
    with Session(engine) as session:
        rows = list(
            session.execute(
                select(StructureVariantLocation, Structure, Variant)
                .join(Structure, StructureVariantLocation.structure_id == Structure.id)
                .join(Variant, StructureVariantLocation.variant_id == Variant.id)
                .where(StructureVariantLocation.variant_id == variant_id)
                .order_by(Structure.maicdb_id)
            )
        )
        traversals: list[dict] = []
        for location, structure, variant in rows:
            constructs = _constructs_for_variant(session, variant.id)
            experiments = _experiments_for_constructs(
                session, [construct.id for construct in constructs]
            )
            traversals.append(
                {
                    "location": {
                        "maicdb_id": location.maicdb_id,
                        "neighborhood": location.neighborhood,
                        "structural_region": location.structural_region,
                        "support": str(getattr(location.support, "name", location.support)),
                        "notes": location.notes,
                    },
                    "structure": {
                        "maicdb_id": structure.maicdb_id,
                        "pdb_id": structure.pdb_id,
                        "title": structure.title,
                        "construction_mutation": structure.mutation,
                    },
                    "constructs": [
                        {"maicdb_id": construct.maicdb_id} for construct in constructs
                    ],
                    "experiments": [
                        {
                            "maicdb_id": experiment.maicdb_id,
                            "measurement_id": experiment.measurement_id,
                            "experiment_label": experiment.experiment_label,
                        }
                        for experiment in experiments
                    ],
                }
            )
        return traversals


def structure_function_page(engine: Engine, accession: str) -> dict | None:
    """Return one static structure-function page payload."""
    with Session(engine) as session:
        structure = session.scalar(
            select(Structure).where(Structure.maicdb_id == accession)
        )
        if structure is None:
            return None
        residues = list(
            session.scalars(
                select(StructureResidue)
                .where(StructureResidue.structure_id == structure.id)
                .order_by(
                    StructureResidue.number_system,
                    StructureResidue.residue_number,
                    StructureResidue.maicdb_id,
                )
            )
        )
        locations = list(
            session.scalars(
                select(StructureVariantLocation)
                .where(StructureVariantLocation.structure_id == structure.id)
                .order_by(StructureVariantLocation.maicdb_id)
            )
        )
        variants = {
            variant.id: variant
            for variant in session.scalars(
                select(Variant).where(
                    Variant.id.in_([location.variant_id for location in locations])
                )
            )
        }
        traversals: list[dict] = []
        for location in locations:
            variant = variants[location.variant_id]
            constructs = _constructs_for_variant(session, variant.id)
            experiments = _experiments_for_constructs(
                session, [construct.id for construct in constructs]
            )
            traversals.append(
                {
                    "variant": {
                        "maicdb_id": variant.maicdb_id,
                        "mutation_short": variant.mutation_short,
                    },
                    "location": {
                        "maicdb_id": location.maicdb_id,
                        "support": str(getattr(location.support, "name", location.support)),
                        "structural_region": location.structural_region,
                    },
                    "constructs": [
                        {"maicdb_id": construct.maicdb_id} for construct in constructs
                    ],
                    "experiments": [
                        {"maicdb_id": experiment.maicdb_id} for experiment in experiments
                    ],
                }
            )
        return {
            "maicdb_id": structure.maicdb_id,
            "pdb_id": structure.pdb_id,
            "title": structure.title,
            "construction_mutation": structure.mutation,
            "residues": [
                {
                    "maicdb_id": item.maicdb_id,
                    "number_system": str(getattr(item.number_system, "name", item.number_system)),
                    "residue_number": item.residue_number,
                    "residue_name": item.residue_name,
                    "residue_role": str(getattr(item.residue_role, "name", item.residue_role)),
                    "structural_region": item.structural_region,
                    "notes": item.notes,
                }
                for item in residues
            ],
            "traversals": traversals,
            "evidence": _evidence_for_structure(engine, structure.id),
            "disclosure": STRUCTURE_FUNCTION_DISCLOSURE,
        }

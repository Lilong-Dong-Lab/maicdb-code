"""Evidence item migration and the shared biophysics provenance path."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from maicdb.accessions import AccessionGenerator, AccessionPrefix
from maicdb.enums import (
    EvidenceConfidence,
    EvidenceMigrationState,
    EvidenceReviewState,
    EvidenceSubjectType,
    EvidenceType,
)
from maicdb.models import (
    Base,
    BiophysicsExperiment,
    DbMeta,
    EvidenceItem,
    EvidenceSubject,
)

__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "BIOPHYSICS_EVIDENCE_STATE",
    "UNMIGRATED_EVIDENCE_DISCLOSURE",
    "unmigrated_evidence_disclosure",
    "public_evidence_item",
    "confidence_from_legacy",
    "ensure_evidence_schema",
    "biophysics_evidence_items",
    "migrate_biophysics_evidence",
    "resolve_biophysics_evidence",
]

EVIDENCE_SCHEMA_VERSION = "0.3.0"
BIOPHYSICS_EVIDENCE_STATE = EvidenceMigrationState.MIGRATED
UNMIGRATED_EVIDENCE_DISCLOSURE = (
    "Bioactivity and unmapped measurements still carry legacy evidence fields; "
    "normalized Evidence items become authoritative for all fact families in "
    "ticket #98."
)


def unmigrated_evidence_disclosure() -> str:
    """Return the public disclosure for unmigrated fact families."""
    return UNMIGRATED_EVIDENCE_DISCLOSURE


def confidence_from_legacy(value: str | None) -> EvidenceConfidence | None:
    """Map the legacy free-text confidence vocabulary to its controlled form."""
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized in {"high", "high-confidence"}:
        return EvidenceConfidence.HIGH
    if normalized in {"medium", "medium-confidence"}:
        return EvidenceConfidence.MEDIUM
    if normalized in {"low", "low-confidence"}:
        return EvidenceConfidence.LOW
    return EvidenceConfidence.UNSTATED


def _next_evidence_accession(session: Session) -> str:
    last = session.scalar(
        select(EvidenceItem.maicdb_id).order_by(EvidenceItem.id.desc()).limit(1)
    )
    number = int(last.rsplit(":", 1)[-1]) if last else 0
    return AccessionGenerator({AccessionPrefix.EVIDENCE_ITEM: number}).next(
        AccessionPrefix.EVIDENCE_ITEM
    )


def _claim_for(row: BiophysicsExperiment) -> str:
    label = row.experiment_label
    if not label and row.parameter_set is not None:
        label = row.parameter_set.value.replace("_", " ")
    value = row.value_as_reported or ""
    unit = row.unit_as_reported or ""
    suffix = f" ({value} {unit})" if value or unit else ""
    measurement = row.measurement_id or row.maicdb_id
    if label:
        return f"{measurement}: {label}{suffix}"
    return f"{measurement}: measurement{suffix}"


def ensure_evidence_schema(session: Session) -> str:
    """Create Evidence tables and ensure the published schema version."""
    Base.metadata.create_all(
        session.get_bind(),
        tables=[EvidenceItem.__table__, EvidenceSubject.__table__],
        checkfirst=True,
    )
    before = session.scalar(select(DbMeta.value).where(DbMeta.key == "schema_version"))
    if before != EVIDENCE_SCHEMA_VERSION:
        session.merge(DbMeta(key="schema_version", value=EVIDENCE_SCHEMA_VERSION))
    return str(before or "")


def biophysics_evidence_items(
    session: Session,
) -> list[tuple[BiophysicsExperiment, EvidenceItem]]:
    """Resolve each biophysics row to its Evidence item through subject links."""
    rows = session.execute(
        select(BiophysicsExperiment, EvidenceItem)
        .join(
            EvidenceSubject,
            (EvidenceSubject.subject_type == EvidenceSubjectType.BIOPHYSICS_EXPERIMENT)
            & (EvidenceSubject.subject_id == BiophysicsExperiment.id),
        )
        .join(EvidenceItem, EvidenceSubject.evidence_item_id == EvidenceItem.id)
        .order_by(BiophysicsExperiment.maicdb_id, EvidenceItem.maicdb_id)
    ).all()
    return [tuple(row) for row in rows]


def public_evidence_item(item: EvidenceItem) -> dict:
    """Return the publication-resolved public Evidence shape."""
    publication = item.publication
    return {
        "maicdb_id": item.maicdb_id,
        "claim": item.claim,
        "source": item.source,
        "publication": None
        if publication is None
        else {
            "id": publication.id,
            "doi": publication.doi,
            "title": publication.title,
            "journal": publication.journal,
            "year": publication.year,
            "authors": publication.authors,
            "pmid": publication.pmid,
            "citation_text": publication.citation_text,
        },
        "quote": item.quote,
        "location": item.location,
        "evidence_type": item.evidence_type,
        "confidence": item.confidence,
        "curator_note": item.curator_note,
        "review_state": item.review_state,
        "review_timestamp": item.review_timestamp,
    }


def migrate_biophysics_evidence(session: Session) -> dict[str, int]:
    """Migrate legacy biophysics evidence without losing or duplicating rows."""
    schema_before = ensure_evidence_schema(session)
    linked_subject_ids = set(
        session.execute(
            select(EvidenceSubject.subject_id).where(
                EvidenceSubject.subject_type
                == EvidenceSubjectType.BIOPHYSICS_EXPERIMENT
            )
        ).scalars()
    )
    pending = (
        session.execute(
            select(BiophysicsExperiment)
            .where(BiophysicsExperiment.id.not_in(linked_subject_ids))
            .order_by(BiophysicsExperiment.maicdb_id)
        )
        .scalars()
        .all()
    )
    created = 0
    for row in pending:
        item = EvidenceItem(
            maicdb_id=_next_evidence_accession(session),
            claim=_claim_for(row),
            source=row.source_db.name if row.source_db else None,
            publication_id=row.publication_id,
            quote=row.evidence_quote,
            location=row.evidence_location,
            evidence_type=EvidenceType.MEASUREMENT,
            confidence=confidence_from_legacy(row.confidence),
            curator_note=row.extractor_note,
            review_state=EvidenceReviewState.UNREVIEWED,
        )
        session.add(item)
        session.flush()
        session.add(
            EvidenceSubject(
                evidence_item_id=item.id,
                subject_type=EvidenceSubjectType.BIOPHYSICS_EXPERIMENT,
                subject_id=row.id,
            )
        )
        created += 1
    session.flush()
    return {
        "rows_examined": len(pending) + len(linked_subject_ids),
        "evidence_created": created,
        "subject_links_created": created,
        "schema_version_before": int(schema_before.replace(".", "").lstrip("0") or 0),
    }


def resolve_biophysics_evidence(
    session: Session, experiment_id: int
) -> list[EvidenceItem]:
    """Return all Evidence items attached to one biophysics experiment."""
    return list(
        session.execute(
            select(EvidenceItem)
            .join(
                EvidenceSubject,
                EvidenceSubject.evidence_item_id == EvidenceItem.id,
            )
            .where(
                EvidenceSubject.subject_type
                == EvidenceSubjectType.BIOPHYSICS_EXPERIMENT,
                EvidenceSubject.subject_id == experiment_id,
            )
            .order_by(EvidenceItem.maicdb_id)
        )
        .scalars()
        .all()
    )

"""Evidence parity and authority cutover coverage for all fact families."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import select

from maicdb.evidence import (
    AUTHORITATIVE_EVIDENCE_DISCLOSURE,
    fact_family_coverage,
    migrate_bioactivity_evidence,
    migrate_biophysics_evidence,
    migrate_unmapped_evidence,
)
from maicdb.enums import EvidenceSubjectType
from maicdb.models import (
    Bioactivity,
    Channel,
    Compound,
    EvidenceItem,
    EvidenceSubject,
    Family,
    UnmappedMeasurement,
)
from maicdb.query import bioactivity_card, open_readonly, provenance

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "db" / "maicdb.sqlite"
requires_db = pytest.mark.skipif(
    not DB_PATH.exists(), reason=f"published DB not found at {DB_PATH}"
)


def _channel(session) -> Channel:
    channel = session.get(Channel, 1)
    if channel is None:
        channel = Channel(
            maicdb_id="MAIC:CH:00001",
            gene_symbol="TEST1",
            organism="Test organism",
            family=Family.OTHER,
        )
        session.add(channel)
        session.flush()
    return channel


def _compound(session) -> Compound:
    compound = session.get(Compound, 1)
    if compound is None:
        compound = Compound(
            maicdb_id="MAIC:CP:00001",
            name="Test compound",
        )
        session.add(compound)
        session.flush()
    return compound


def _bioactivity(session, maicdb_id: str, **overrides) -> Bioactivity:
    values = {
        "maicdb_id": maicdb_id,
        "compound_id": _compound(session).id,
        "channel_id": _channel(session).id,
        "activity_type": "IC50",
        "activity_value": 4.5,
        "activity_units": "nM",
        "relation": "=",
        "measurement_id": f"measurement-{maicdb_id}",
        "evidence_quote": "The measured IC50 was reported.",
        "evidence_location": "Results",
        "confidence": "high",
        "extractor_note": "curator note",
        "condition_key": "test-condition",
        "n": "3",
    }
    values.update(overrides)
    row = Bioactivity(**values)
    session.add(row)
    session.flush()
    return row


def _unmapped(session, maicdb_id: str, **overrides) -> UnmappedMeasurement:
    values = {
        "maicdb_id": maicdb_id,
        "channel_id": _channel(session).id,
        "parameter_kind": "pressure_threshold",
        "value": 35.0,
        "unit": "mm Hg",
        "measurement_id": f"measurement-{maicdb_id}",
        "evidence_quote": "The pressure threshold was reported.",
        "evidence_location": "Figure 2",
        "confidence": "medium",
        "extractor_note": "curator note",
        "condition_key": "test-condition",
        "n": "4",
    }
    values.update(overrides)
    row = UnmappedMeasurement(**values)
    session.add(row)
    session.flush()
    return row


def _evidence_for(session, subject_type: EvidenceSubjectType, subject_id: int):
    return list(
        session.scalars(
            select(EvidenceItem)
            .join(EvidenceSubject, EvidenceSubject.evidence_item_id == EvidenceItem.id)
            .where(
                EvidenceSubject.subject_type == subject_type,
                EvidenceSubject.subject_id == subject_id,
            )
        )
    )


def test_all_fact_families_migrate_idempotently(session):
    from tests.test_evidence import _experiment


    experiment = _experiment(session, "MAIC:BX:00001")
    bioactivity = _bioactivity(session, "MAIC:BA:00001")
    unmapped = _unmapped(session, "MAIC:UM:00001")

    counts = {
        "biophysics": migrate_biophysics_evidence(session),
        "bioactivity": migrate_bioactivity_evidence(session),
        "unmapped": migrate_unmapped_evidence(session),
    }
    assert counts["biophysics"]["evidence_created"] == 1
    assert counts["bioactivity"]["evidence_created"] == 1
    assert counts["unmapped"]["evidence_created"] == 1
    assert fact_family_coverage(session) == {
        "BIOPHYSICS_EXPERIMENT": 0,
        "BIOACTIVITY": 0,
        "UNMAPPED_MEASUREMENT": 0,
    }

    repeat = {
        "biophysics": migrate_biophysics_evidence(session),
        "bioactivity": migrate_bioactivity_evidence(session),
        "unmapped": migrate_unmapped_evidence(session),
    }
    assert all(count["evidence_created"] == 0 for count in repeat.values())
    assert session.scalar(select(EvidenceItem.maicdb_id).order_by(EvidenceItem.id)) == (
        "MAIC:EV:00001"
    )
    assert _evidence_for(
        session, EvidenceSubjectType.BIOPHYSICS_EXPERIMENT, experiment.id
    )[0].quote == experiment.evidence_quote
    assert _evidence_for(session, EvidenceSubjectType.BIOACTIVITY, bioactivity.id)[
        0
    ].quote == bioactivity.evidence_quote
    assert _evidence_for(
        session, EvidenceSubjectType.UNMAPPED_MEASUREMENT, unmapped.id
    )[0].quote == unmapped.evidence_quote


def test_bioactivity_claim_preserves_activity_fields(session):
    row = _bioactivity(
        session,
        "MAIC:BA:00002",
        activity_type="IC50",
        activity_value=4.5,
        activity_units="nM",
        relation="=",
    )
    migrate_bioactivity_evidence(session)
    item = _evidence_for(session, EvidenceSubjectType.BIOACTIVITY, row.id)[0]
    assert item.claim == "MAIC:BA:00002: IC50 = 4.5 nM"


def test_unmapped_claim_preserves_archive_fields(session):
    row = _unmapped(session, "MAIC:UM:00002", parameter_kind="block_voltage", unit="mV")
    migrate_unmapped_evidence(session)
    item = _evidence_for(session, EvidenceSubjectType.UNMAPPED_MEASUREMENT, row.id)[0]
    assert item.claim == "MAIC:UM:00002: block_voltage 35.0 mV"


@requires_db
def test_published_all_fact_families_are_fully_covered():
    with sqlite3.connect(DB_PATH) as conn:
        fact_counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "biophysics_experiment",
                "bioactivity",
                "unmapped_measurement",
            )
        }
        linked_counts = dict(
            conn.execute(
                """
                SELECT subject_type, COUNT(DISTINCT subject_id)
                FROM evidence_subject
                WHERE subject_type IN (
                    'BIOPHYSICS_EXPERIMENT', 'BIOACTIVITY', 'UNMAPPED_MEASUREMENT'
                )
                GROUP BY subject_type
                """
            ).fetchall()
        )
    assert fact_counts == {
        "biophysics_experiment": 960,
        "bioactivity": 137,
        "unmapped_measurement": 28,
    }
    assert linked_counts == {
        "BIOPHYSICS_EXPERIMENT": 960,
        "BIOACTIVITY": 137,
        "UNMAPPED_MEASUREMENT": 28,
    }


@requires_db
def test_published_field_level_parity_for_every_fact_family():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT 'BIOPHYSICS_EXPERIMENT' AS family,
                   e.id AS subject_id,
                   e.evidence_quote, e.evidence_location,
                   e.confidence, e.extractor_note,
                   e.source_db, e.publication_id,
                   i.quote, i.location, i.confidence, i.curator_note,
                   i.source, i.publication_id
            FROM biophysics_experiment e
            JOIN evidence_subject sub
              ON sub.subject_type = 'BIOPHYSICS_EXPERIMENT'
             AND sub.subject_id = e.id
            JOIN evidence_item i ON i.id = sub.evidence_item_id
            UNION ALL
            SELECT 'BIOACTIVITY', b.id,
                   b.evidence_quote, b.evidence_location,
                   b.confidence, b.extractor_note,
                   b.source_db, b.publication_id, i.quote, i.location, i.confidence,
                   i.curator_note, i.source, i.publication_id
            FROM bioactivity b
            JOIN evidence_subject sub
              ON sub.subject_type = 'BIOACTIVITY'
             AND sub.subject_id = b.id
            JOIN evidence_item i ON i.id = sub.evidence_item_id
            UNION ALL
            SELECT 'UNMAPPED_MEASUREMENT', u.id,
                   u.evidence_quote, u.evidence_location,
                   u.confidence, u.extractor_note,
                   u.source_db, u.publication_id, i.quote, i.location, i.confidence,
                   i.curator_note, i.source, i.publication_id
            FROM unmapped_measurement u
            JOIN evidence_subject sub
              ON sub.subject_type = 'UNMAPPED_MEASUREMENT'
             AND sub.subject_id = u.id
            JOIN evidence_item i ON i.id = sub.evidence_item_id
            ORDER BY family, subject_id
            """
        ).fetchall()
    assert len(rows) == 1125
    assert all(
        legacy[0] == normalized[0]
        and legacy[1] == normalized[1]
        and legacy[2].lower() == normalized[2].lower()
        and legacy[3] == normalized[3]
        and legacy[4] == normalized[4]
        and legacy[5] == normalized[5]
        for legacy, normalized in ((row[2:8], row[8:14]) for row in rows)
    )

@requires_db
def test_published_bioactivity_and_provenance_use_authoritative_path():
    card = bioactivity_card(open_readonly(DB_PATH), "ASIC")
    row = card["rows"][0]
    assert row["evidence"]
    assert AUTHORITATIVE_EVIDENCE_DISCLOSURE not in row
    assert "unmigrated_evidence_disclosure" not in row

    evidence = provenance(open_readonly(DB_PATH), "ASIC-00025")["evidence"][0]
    assert evidence["maicdb_id"] == "MAIC:EV:00961"
    assert evidence["evidence_type"] == "measurement"
    assert evidence["confidence"] == "high"
    assert evidence["review_state"] == "unreviewed"

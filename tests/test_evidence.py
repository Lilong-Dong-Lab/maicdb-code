from datetime import date
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from maicdb.evidence import (
    confidence_from_legacy,
    migrate_biophysics_evidence,
    _claim_for,
    resolve_biophysics_evidence,
)
from maicdb.enums import (
    EvidenceConfidence,
    EvidenceReviewState,
    EvidenceSubjectType,
    EvidenceType,
    Family,
    ParameterSet,
)
from maicdb.models import (
    BiophysicsExperiment,
    Channel,
    EvidenceItem,
    EvidenceSubject,
)
from maicdb.query import biophysics_evidence, channel_card

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


def _experiment(session, maicdb_id: str, **overrides) -> BiophysicsExperiment:
    values = {
        "maicdb_id": maicdb_id,
        "channel_id": _channel(session).id,
        "measurement_id": f"measurement-{maicdb_id}",
        "evidence_quote": "The measured threshold was reported.",
        "evidence_location": "Results",
        "confidence": "high",
        "extractor_note": "curator note",
        "value_as_reported": "12",
        "unit_as_reported": "mmHg",
    }
    values.update(overrides)
    experiment = BiophysicsExperiment(**values)
    session.add(experiment)
    session.flush()
    return experiment


def test_confidence_mapping_is_controlled():
    assert confidence_from_legacy("High") is EvidenceConfidence.HIGH
    assert confidence_from_legacy(" HIGH-CONFIDENCE ") is EvidenceConfidence.HIGH
    assert confidence_from_legacy("unrecognized") is EvidenceConfidence.UNSTATED
    assert confidence_from_legacy(None) is None


def test_claim_mapping_never_publishes_internal_none_or_enum_repr(session):
    enum_experiment = _experiment(
        session,
        "MAIC:BX:00001",
        experiment_label=None,
    )
    enum_experiment.parameter_set = ParameterSet.CONDUCTANCE_ONLY
    enum_experiment.unit_as_reported = None
    assert _claim_for(enum_experiment) == (
        "measurement-MAIC:BX:00001: conductance only (12 )"
    )

    unlabelled = _experiment(
        session,
        "MAIC:BX:00002",
        experiment_label=None,
        parameter_set=None,
        value_as_reported=None,
        unit_as_reported=None,
    )
    assert _claim_for(unlabelled) == "measurement-MAIC:BX:00002: measurement"


def test_migration_is_idempotent_and_lossless(session):
    first = _experiment(session, "MAIC:BX:00001")
    counts = migrate_biophysics_evidence(session)
    assert counts == {
        "rows_examined": 1,
        "evidence_created": 1,
        "subject_links_created": 1,
        "schema_version_before": 0,
    }
    repeat = migrate_biophysics_evidence(session)
    assert repeat["evidence_created"] == 0
    assert repeat["rows_examined"] == 1
    item = resolve_biophysics_evidence(session, first.id)[0]
    assert item.maicdb_id == "MAIC:EV:00001"
    assert item.claim.startswith("measurement-MAIC:BX:00001:")
    assert item.quote == first.evidence_quote
    assert item.location == first.evidence_location
    assert item.confidence is EvidenceConfidence.HIGH
    assert item.curator_note == first.extractor_note
    assert item.review_state is EvidenceReviewState.UNREVIEWED
    assert item.review_timestamp is None
    assert item.evidence_type is EvidenceType.MEASUREMENT
    assert session.scalar(select(EvidenceItem.maicdb_id)) == "MAIC:EV:00001"


def test_many_to_many_subject_reuse(session):
    experiment_one = _experiment(session, "MAIC:BX:00001")
    experiment_two = _experiment(session, "MAIC:BX:00002")
    migrate_biophysics_evidence(session)
    shared = EvidenceItem(
        maicdb_id="MAIC:EV:00003",
        claim="Shared measurement claim",
        evidence_type=EvidenceType.MEASUREMENT,
        review_state=EvidenceReviewState.REVIEWED,
        review_timestamp=date(2026, 11, 21),
    )
    session.add(shared)
    session.flush()
    session.add_all(
        [
            EvidenceSubject(
                evidence_item_id=shared.id,
                subject_type=EvidenceSubjectType.BIOPHYSICS_EXPERIMENT,
                subject_id=experiment_one.id,
            ),
            EvidenceSubject(
                evidence_item_id=shared.id,
                subject_type=EvidenceSubjectType.BIOPHYSICS_EXPERIMENT,
                subject_id=experiment_two.id,
            ),
        ]
    )
    session.flush()
    assert len(resolve_biophysics_evidence(session, experiment_one.id)) == 2
    assert len(resolve_biophysics_evidence(session, experiment_two.id)) == 2


def test_resolution_paths_use_stable_accession_order(session):
    experiment = _experiment(session, "MAIC:BX:00001")
    migrate_biophysics_evidence(session)
    higher_accession = EvidenceItem(
        maicdb_id="MAIC:EV:00003",
        claim="Higher stable accession, lower internal id",
        evidence_type=EvidenceType.MEASUREMENT,
    )
    lower_accession = EvidenceItem(
        maicdb_id="MAIC:EV:00002",
        claim="Lower stable accession, higher internal id",
        evidence_type=EvidenceType.MEASUREMENT,
    )
    session.add_all([higher_accession, lower_accession])
    session.flush()
    session.add_all(
        [
            EvidenceSubject(
                evidence_item_id=higher_accession.id,
                subject_type=EvidenceSubjectType.BIOPHYSICS_EXPERIMENT,
                subject_id=experiment.id,
            ),
            EvidenceSubject(
                evidence_item_id=lower_accession.id,
                subject_type=EvidenceSubjectType.BIOPHYSICS_EXPERIMENT,
                subject_id=experiment.id,
            ),
        ]
    )
    session.flush()
    resolved = resolve_biophysics_evidence(session, experiment.id)
    assert [item.maicdb_id for item in resolved] == [
        "MAIC:EV:00001",
        "MAIC:EV:00002",
        "MAIC:EV:00003",
    ]


def test_duplicate_subject_link_is_rejected(session):
    experiment = _experiment(session, "MAIC:BX:00001")
    item = EvidenceItem(
        maicdb_id="MAIC:EV:00001",
        claim="Test claim",
        evidence_type=EvidenceType.MEASUREMENT,
    )
    session.add(item)
    session.flush()
    session.add(
        EvidenceSubject(
            evidence_item_id=item.id,
            subject_type=EvidenceSubjectType.BIOPHYSICS_EXPERIMENT,
            subject_id=experiment.id,
        )
    )
    session.flush()
    session.add(
        EvidenceSubject(
            evidence_item_id=item.id,
            subject_type=EvidenceSubjectType.BIOPHYSICS_EXPERIMENT,
            subject_id=experiment.id,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_channel_card_uses_shared_evidence_resolution(session, engine):
    experiment = _experiment(session, "MAIC:BX:00001", p50_value=12)
    experiment.p50_unit = None
    migrate_biophysics_evidence(session)
    shared = EvidenceItem(
        maicdb_id="MAIC:EV:00003",
        claim="Supports the same measurement",
        evidence_type=EvidenceType.MEASUREMENT,
    )
    session.add(shared)
    session.flush()
    session.add(
        EvidenceSubject(
            evidence_item_id=shared.id,
            subject_type=EvidenceSubjectType.BIOPHYSICS_EXPERIMENT,
            subject_id=experiment.id,
        )
    )
    session.flush()
    card = channel_card(engine, "TEST1", parameters=["p50"])
    row = card["parameters"]["p50"]["rows"][0]
    assert [item["maicdb_id"] for item in row["evidence"]] == [
        "MAIC:EV:00001",
        "MAIC:EV:00003",
    ]
    assert row["evidence"][0]["publication"] is None
    assert not any(
        key == "publication_id" or key in {"doi", "title", "journal", "year", "authors", "pmid", "citation_text"}
        for key in row["evidence"][0]
    )
    assert all("editorial_history" not in item for item in row["evidence"])


def test_query_resolution_supports_missing_evidence(engine):
    assert biophysics_evidence(engine, []) == {}


@requires_db
def test_published_biophysics_evidence_has_full_coverage():
    with sqlite3.connect(DB_PATH) as conn:
        missing = conn.execute(
            """
            SELECT e.maicdb_id
            FROM biophysics_experiment AS e
            LEFT JOIN evidence_subject AS s
              ON s.subject_type = 'BIOPHYSICS_EXPERIMENT'
             AND s.subject_id = e.id
            LEFT JOIN evidence_item AS i ON i.id = s.evidence_item_id
            WHERE i.maicdb_id IS NULL
            ORDER BY e.maicdb_id
            LIMIT 1
            """
        ).fetchone()
    assert missing is None


@requires_db
def test_published_evidence_trace_is_stable():
    with sqlite3.connect(DB_PATH) as conn:
        experiment_id, measurement_id, evidence_id, quote = conn.execute(
            """
            SELECT e.id,
                   e.measurement_id,
                   i.maicdb_id,
                   i.quote
            FROM biophysics_experiment AS e
            JOIN evidence_subject AS s
              ON s.subject_type = 'BIOPHYSICS_EXPERIMENT'
             AND s.subject_id = e.id
            JOIN evidence_item AS i ON i.id = s.evidence_item_id
            WHERE e.measurement_id = 'PIEZO1-EX-00005'
            ORDER BY i.maicdb_id
            LIMIT 1
            """
        ).fetchone()
    assert measurement_id == "PIEZO1-EX-00005"
    assert evidence_id == "MAIC:EV:00409"
    assert quote != ""

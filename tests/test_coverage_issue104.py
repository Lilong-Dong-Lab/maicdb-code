"""Coverage statistics surface tests for issue #104."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text

from tests.test_site_build import requires_db

from maicdb.analysis.coverage import coverage_payload
from maicdb.enums import EvidenceReviewState, EvidenceSubjectType, EvidenceType
from maicdb.models import (
    Bioactivity,
    BiophysicsExperiment,
    Channel,
    Compound,
    EvidenceItem,
    EvidenceSubject,
    Publication,
    UnmappedMeasurement,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "db" / "maicdb.sqlite"


def _channel(session, symbol: str, family: str, ortholog: str | None) -> Channel:
    channel = Channel(
        maicdb_id=f"MAIC:CH:{symbol}",
        gene_symbol=symbol,
        organism="Test organism",
        family=family,
        ortholog_group=ortholog,
    )
    session.add(channel)
    session.flush()
    return channel


def _evidence(session, channel: Channel, state: EvidenceReviewState, when: date | None):
    item = EvidenceItem(
        maicdb_id=f"MAIC:EV:{channel.gene_symbol}{state.name}",
        claim=f"Claim for {channel.gene_symbol}",
        evidence_type=EvidenceType.MEASUREMENT,
        review_state=state,
        review_timestamp=when,
    )
    session.add(item)
    session.flush()
    row = BiophysicsExperiment(
        maicdb_id=f"MAIC:BX:{channel.gene_symbol}{state.name}",
        channel_id=channel.id,
    )
    session.add(row)
    session.flush()
    session.add(
        EvidenceSubject(
            evidence_item_id=item.id,
            subject_type=EvidenceSubjectType.BIOPHYSICS_EXPERIMENT,
            subject_id=row.id,
        )
    )
    return item


def test_coverage_payload_contains_four_metric_families(session):
    alpha = _channel(session, "ALPHA", "PIEZO", "ALPHA")
    beta = _channel(session, "BETA", "TRP", None)
    publication = Publication(doi="10.1/coverage")
    compound = Compound(maicdb_id="MAIC:CP:ALPHA", name="Compound")
    session.add_all([publication, compound])
    session.flush()
    session.add_all(
        [
            BiophysicsExperiment(
                maicdb_id="MAIC:BX:ALPHA",
                channel_id=alpha.id,
                publication_id=publication.id,
                p50_value=1.0,
            ),
            Bioactivity(
                maicdb_id="MAIC:BA:ALPHA",
                channel_id=alpha.id,
                compound_id=compound.id,
                publication_id=publication.id,
            ),
            UnmappedMeasurement(
                maicdb_id="MAIC:UM:BETA",
                channel_id=beta.id,
                parameter_kind="other",
                publication_id=publication.id,
            ),
        ]
    )
    session.flush()
    _evidence(session, alpha, EvidenceReviewState.ACCEPTED, date(2026, 11, 23))
    _evidence(session, beta, EvidenceReviewState.PROVISIONAL, date(2026, 11, 24))
    session.commit()

    payload = coverage_payload(session.get_bind())
    assert payload["all"]["totals"]["channels"] == 2
    assert payload["all"]["review"] == {
        "accepted": 1,
        "provisional": 1,
        "reviewed": 0,
        "unreviewed": 0,
        "conflicted": 0,
        "total": 2,
        "last_review_date": "2026-11-24",
    }
    assert {family["scope_key"] for family in payload["families"]} == {"PIEZO", "TRP"}
    assert {channel["scope_key"] for channel in payload["channels"]} == {
        "ALPHA",
        "BETA",
    }
    alpha_slice = next(c for c in payload["channels"] if c["scope_key"] == "ALPHA")
    assert alpha_slice["totals"]["bioactivities"] == 1
    beta_slice = next(c for c in payload["channels"] if c["scope_key"] == "BETA")
    assert beta_slice["totals"]["unmapped_measurements"] == 1


def test_cross_foot_totals_review_and_linkage(session):
    channel = _channel(session, "ALPHA", "PIEZO", "ALPHA")
    _evidence(
        channel=channel,
        session=session,
        state=EvidenceReviewState.UNREVIEWED,
        when=None,
    )
    session.commit()
    engine = session.get_bind()
    payload = coverage_payload(engine)
    with engine.connect() as conn:
        channel_count = conn.execute(text("SELECT COUNT(*) FROM channel")).scalar_one()
        review_total = conn.execute(
            text("SELECT COUNT(*) FROM evidence_item")
        ).scalar_one()
        linkage_total = conn.execute(
            text(
                "SELECT COUNT(*) FROM experiment_construct ec "
                "JOIN construct_variant cv ON cv.construct_id = ec.construct_id"
            )
        ).scalar_one()
    assert payload["all"]["totals"]["channels"] == channel_count
    assert payload["all"]["review"]["total"] == review_total
    assert payload["all"]["linkage"]["experiments_to_variants"] == linkage_total


def test_coverage_build_is_deterministic(tmp_path):
    from tests.test_site_build import run_build

    first = tmp_path / "first"
    second = tmp_path / "second"
    run_build(first)
    run_build(second)
    first = (tmp_path / "first" / "_data" / "analysis" / "coverage.json").read_bytes()
    second = (tmp_path / "second" / "_data" / "analysis" / "coverage.json").read_bytes()
    assert first == second


@requires_db
def test_artifact_census_covers_migrated_dependent_tables():
    from maicdb.analysis.coverage import NO_CORE_SCHEMA_CHANGE_DISCLOSURE
    from maicdb.query import open_readonly

    engine = open_readonly(DB_PATH)
    try:
        payload = coverage_payload(engine)
    finally:
        engine.dispose()
    assert payload["no_core_schema_change"] == NO_CORE_SCHEMA_CHANGE_DISCLOSURE
    assert payload["all"]["totals"] == {
        "channels": 12,
        "families": 7,
        "ortholog_groups": 12,
        "publications": 216,
        "experiments": 960,
        "bioactivities": 137,
        "unmapped_measurements": 28,
        "compounds": 86,
        "variants": 135,
        "structures": 12,
        "evidence_items": 1129,
        "external_references": 987,
    }
    assert payload["all"]["review"]["total"] == 1125
    assert payload["all"]["linkage"]["experiments_to_variants"] == 200

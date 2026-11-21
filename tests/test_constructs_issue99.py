"""Construct migration, lossless linkage, and bidirectional traversal tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from maicdb.constructs import (
    CONSTRUCT_SCHEMA_VERSION,
    construct_page,
    construct_traversals_for_experiments,
    migrate_construct_links,
    variant_construct_page,
)
from maicdb.enums import Family
from maicdb.models import (
    BiophysicsExperiment,
    Channel,
    Construct,
    Variant,
)
from maicdb.query import channel_card, open_readonly, parameter_comparison

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "db" / "maicdb.sqlite"
requires_db = pytest.mark.skipif(
    not DB_PATH.exists(), reason=f"published DB not found at {DB_PATH}"
)


def _channel(session) -> Channel:
    return Channel(
        maicdb_id="MAIC:CH:00001",
        gene_symbol="TEST1",
        organism="Test organism",
        family=Family.OTHER,
    )


def _variant(session, channel: Channel, maicdb_id: str, mutation_short: str):
    variant = Variant(
        maicdb_id=maicdb_id,
        channel_id=channel.id,
        mutation_short=mutation_short,
    )
    session.add(variant)
    session.flush()
    return variant


def _experiment(session, channel: Channel, maicdb_id: str, **overrides):
    values = {
        "maicdb_id": maicdb_id,
        "channel_id": channel.id,
        "measurement_id": f"measurement-{maicdb_id}",
        "evidence_quote": "The construct was measured.",
    }
    values.update(overrides)
    experiment = BiophysicsExperiment(**values)
    session.add(experiment)
    session.flush()
    return experiment


def test_migration_preserves_legacy_construct_sets_and_is_idempotent(session):
    channel = _channel(session)
    session.add(channel)
    session.flush()
    variant_one = _variant(session, channel, "MAIC:VR:00001", "A1")
    variant_two = _variant(session, channel, "MAIC:VR:00002", "B2")
    shared = _experiment(
        session,
        channel,
        "MAIC:BX:00001",
        variant_id=None,
        structure_id=None,
    )
    shared.structure_id = None
    shared.expression_system = "shared expression"
    shared.variant_id = variant_one.id
    second = _experiment(
        session,
        channel,
        "MAIC:BX:00002",
        expression_system="shared expression",
    )
    second.structure_id = None
    second.variant_id = variant_two.id
    distinct = _experiment(
        session,
        channel,
        "MAIC:BX:00003",
        expression_system="distinct expression",
    )
    distinct.structure_id = None
    distinct.variant_id = variant_two.id
    session.flush()

    counts = migrate_construct_links(session)
    session.commit()
    assert counts["schema_version_before"] == ""
    assert counts["schema_version_after"] == CONSTRUCT_SCHEMA_VERSION
    assert counts["constructs_created"] == 2
    assert counts["variant_links_created"] == 3
    assert counts["experiment_links_created"] == 3
    constructs = list(session.scalars(select(Construct).order_by(Construct.maicdb_id)))
    assert [len(item.variants) for item in constructs] == [2, 1]
    assert construct_traversals_for_experiments(session.get_bind(), [shared.id])[
        shared.id
    ][0]["variants"][0]["mutation_short"] == "A1"
    second_variants = construct_traversals_for_experiments(
        session.get_bind(),
        [second.id],
    )[second.id][0]["variants"]
    assert [variant["mutation_short"] for variant in second_variants] == ["A1", "B2"]

    repeat = migrate_construct_links(session)
    assert repeat["constructs_created"] == 0
    assert repeat["variant_links_created"] == 0
    assert repeat["experiment_links_created"] == 0
    assert len(list(session.scalars(select(Construct)))) == 2


def test_construct_and_variant_pages_traverse_both_directions(session):
    engine = session.get_bind()
    channel = _channel(session)
    session.add(channel)
    session.flush()
    variant = _variant(session, channel, "MAIC:VR:00001", "A1")
    experiment = _experiment(
        session,
        channel,
        "MAIC:BX:00001",
        variant_id=variant.id,
        expression_system="expression design",
    )
    migrate_construct_links(session)
    session.commit()

    accession = session.scalar(select(Construct.maicdb_id))
    construct_payload = construct_page(engine, accession)
    assert construct_payload["maicdb_id"] == accession
    assert construct_payload["expression_design"] == "expression design"
    assert construct_payload["experiments"][0]["maicdb_id"] == experiment.maicdb_id
    assert construct_payload["variant_construct_experiments"][0]["variant"][
        "mutation_short"
    ] == "A1"

    variant_payload = variant_construct_page(engine, variant.id)
    assert variant_payload["constructs"][0]["maicdb_id"] == accession
    assert variant_payload["construct_experiments"][0]["experiments"][0][
        "maicdb_id"
    ] == experiment.maicdb_id


def test_channel_card_and_export_expose_construct_paths(session):
    engine = session.get_bind()
    channel = _channel(session)
    session.add(channel)
    session.flush()
    variant = _variant(session, channel, "MAIC:VR:00001", "A1")
    _experiment(
        session,
        channel,
        "MAIC:BX:00001",
        variant_id=variant.id,
        conductance_ps=12.0,
    )
    migrate_construct_links(session)
    session.commit()

    card = channel_card(engine, "TEST1", parameters=["conductance"])
    row = card["parameters"]["conductance"]["rows"][0]
    traversal = row["constructs"][0]
    assert traversal["construct"]["maicdb_id"].startswith("MAIC:CN:")
    assert traversal["variants"][0]["mutation_short"] == "A1"
    comparison = parameter_comparison(engine, "conductance")
    assert comparison[0]["construct_ids"] == [traversal["construct"]["maicdb_id"]]


@requires_db
def test_frozen_corpus_migration_is_lossless_without_mutation():
    engine = open_readonly(DB_PATH)
    traversals = construct_traversals_for_experiments(
        engine,
        list(range(1, 961)),
    )
    construct_ids = [
        traversal["construct"]["maicdb_id"]
        for paths in traversals.values()
        for traversal in paths
    ]
    engine.dispose()
    assert len(construct_ids) == 200
    assert len(set(construct_ids)) == 52


@requires_db
def test_frozen_corpus_construct_census():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        f"sqlite:///file:{DB_PATH}?mode=ro&uri=true",
        connect_args={"uri": True},
        poolclass=StaticPool,
    )
    from sqlalchemy import text

    conn = engine.connect()
    counts = {
        table: conn.scalar(text(f"SELECT COUNT(*) FROM {table}"))
        for table in ("construct", "construct_variant", "experiment_construct")
    }
    direct_links = conn.execute(
        text(
            "SELECT COUNT(*) FROM biophysics_experiment "
            "WHERE variant_id IS NOT NULL"
        )
    ).scalar_one()
    conn.close()
    engine.dispose()
    assert counts == {"construct": 52, "construct_variant": 142, "experiment_construct": 200}
    assert direct_links == 200

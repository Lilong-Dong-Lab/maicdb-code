"""Deterministic database-depth and coverage statistics.

Issue #104 defines four metric families: totals, coverage, linkage, and
review state.  This module computes each family from the frozen artifact at
three scopes (whole database, family, and channel) using SQL grouped by a
single channel dimension.  It never mutates the artifact: no persisted
statistics model is introduced.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from maicdb.analysis.site_payloads import data_freeze_tag
from maicdb.data_layers import in_scope_entry

__all__ = ["coverage_payload", "NO_CORE_SCHEMA_CHANGE_DISCLOSURE"]

NO_CORE_SCHEMA_CHANGE_DISCLOSURE = (
    "Coverage statistics are derived at build time; issue #104 makes no "
    "core schema change."
)

_TOTALS_SQL = """
WITH channels AS ({channel_scope}),
scope(channel_id) AS (SELECT id FROM channels),
records AS (
    SELECT channel_id, id, publication_id FROM biophysics_experiment
    UNION ALL
    SELECT channel_id, id, publication_id FROM bioactivity
    UNION ALL
    SELECT channel_id, id, publication_id FROM unmapped_measurement
),
subject_xrefs(channel_id) AS (
    {xref_union}
)
SELECT
    (SELECT COUNT(*) FROM channels) AS channels,
    (SELECT COUNT(DISTINCT family) FROM channels) AS families,
    (SELECT COUNT(DISTINCT ortholog_group) FROM channels
       WHERE ortholog_group IS NOT NULL) AS ortholog_groups,
    (SELECT COUNT(DISTINCT r.publication_id) FROM records r
       WHERE r.publication_id IS NOT NULL) AS publications,
    (SELECT COUNT(*) FROM biophysics_experiment e JOIN scope
       ON e.channel_id = scope.channel_id) AS experiments,
    (SELECT COUNT(*) FROM bioactivity b JOIN scope
       ON b.channel_id = scope.channel_id) AS bioactivities,
    (SELECT COUNT(*) FROM unmapped_measurement u JOIN scope
       ON u.channel_id = scope.channel_id) AS unmapped_measurements,
    (SELECT COUNT(DISTINCT b.compound_id) FROM bioactivity b JOIN scope
       ON b.channel_id = scope.channel_id) AS compounds,
    (SELECT COUNT(*) FROM variant v JOIN scope
       ON v.channel_id = scope.channel_id) AS variants,
    (SELECT COUNT(*) FROM structure s JOIN scope
       ON s.channel_id = scope.channel_id) AS structures,
    (SELECT COUNT(DISTINCT es.evidence_item_id) FROM evidence_subject es
      JOIN biophysics_experiment e
        ON es.subject_type = 'BIOPHYSICS_EXPERIMENT' AND es.subject_id = e.id
      JOIN scope ON e.channel_id = scope.channel_id) AS evidence_items,
    (SELECT COUNT(*) FROM subject_xrefs) AS external_references
"""

_COVERAGE_SQL = """
WITH channels AS ({channel_scope}),
scope(channel_id) AS (SELECT id FROM channels),
evidence AS (
    SELECT DISTINCT b.channel_id AS channel_id
      FROM evidence_subject es
      JOIN bioactivity b
        ON es.subject_type = 'BIOACTIVITY' AND es.subject_id = b.id
    UNION
    SELECT DISTINCT u.channel_id AS channel_id
      FROM evidence_subject es
      JOIN unmapped_measurement u
        ON es.subject_type = 'UNMAPPED_MEASUREMENT' AND es.subject_id = u.id
    UNION
    SELECT DISTINCT e.channel_id AS channel_id
      FROM evidence_subject es
      JOIN biophysics_experiment e
        ON es.subject_type = 'BIOPHYSICS_EXPERIMENT' AND es.subject_id = e.id
),
constructs AS (
    SELECT DISTINCT c.channel_id AS channel_id
      FROM construct c
      JOIN experiment_construct ec ON ec.construct_id = c.id
),
residues AS (
    SELECT DISTINCT r.channel_id AS channel_id
      FROM structure_residue r
     WHERE r.residue_role = 'FUNCTIONAL_SITE'
),
xrefs AS (
    SELECT DISTINCT channel_id FROM ({xref_union}) AS xrefs
)
SELECT
    (SELECT COUNT(*) FROM channels) AS denominator,
    (SELECT COUNT(*) FROM channels WHERE maicdb_id IS NOT NULL
       AND gene_symbol IS NOT NULL AND organism IS NOT NULL
       AND family IS NOT NULL) AS required_fields,
    (SELECT COUNT(*) FROM channels WHERE id IN (SELECT channel_id FROM evidence)) AS evidence_links,
    (SELECT COUNT(*) FROM channels WHERE id IN (SELECT channel_id FROM constructs)) AS construct_links,
    (SELECT COUNT(*) FROM channels WHERE id IN (SELECT channel_id FROM residues)) AS residue_maps,
    (SELECT COUNT(*) FROM channels WHERE id IN (SELECT channel_id FROM xrefs)) AS external_references,
    (SELECT COUNT(*) FROM channels WHERE id IN (
        SELECT id FROM channels INTERSECT
        SELECT channel_id FROM evidence)) AS review_state
"""

_LINKAGE_SQL = """
WITH channels AS ({channel_scope}),
scope(channel_id) AS (SELECT id FROM channels),
records AS (
    SELECT channel_id, publication_id FROM biophysics_experiment
    UNION ALL
    SELECT channel_id, publication_id FROM bioactivity
    UNION ALL
    SELECT channel_id, publication_id FROM unmapped_measurement
),
subject_xrefs(channel_id) AS ({xref_union})
SELECT
    (SELECT COUNT(DISTINCT ec.experiment_id)
       FROM experiment_construct ec
       JOIN construct_variant cv ON cv.construct_id = ec.construct_id
       JOIN biophysics_experiment e ON e.id = ec.experiment_id
       JOIN scope ON e.channel_id = scope.channel_id) AS experiments_to_variants,
    (SELECT COUNT(DISTINCT l.variant_id)
       FROM structure_variant_location l
       JOIN variant v ON v.id = l.variant_id
       JOIN scope ON v.channel_id = scope.channel_id) AS variants_to_structures,
    (SELECT COUNT(DISTINCT r.structure_id)
       FROM structure_residue r
       JOIN structure s ON s.id = r.structure_id
       JOIN scope ON s.channel_id = scope.channel_id
      WHERE r.residue_role = 'FUNCTIONAL_SITE') AS structures_to_functional_residues,
    (SELECT COUNT(*) FROM records WHERE publication_id IS NOT NULL
       AND channel_id IN (SELECT channel_id FROM scope)) AS records_to_publications,
    (SELECT COUNT(*) FROM subject_xrefs) AS subjects_to_external_references
"""

_REVIEW_SQL = """
WITH channels AS ({channel_scope}),
scope(channel_id) AS (SELECT id FROM channels),
items AS (
    SELECT DISTINCT ei.id, ei.review_state, ei.review_timestamp
      FROM evidence_item ei
      JOIN evidence_subject es ON es.evidence_item_id = ei.id
      JOIN (
        SELECT b.channel_id, es2.id AS evidence_subject_id
          FROM evidence_subject es2 JOIN bioactivity b
            ON es2.subject_type = 'BIOACTIVITY' AND es2.subject_id = b.id
        UNION ALL
        SELECT u.channel_id, es2.id
          FROM evidence_subject es2 JOIN unmapped_measurement u
            ON es2.subject_type = 'UNMAPPED_MEASUREMENT'
           AND es2.subject_id = u.id
        UNION ALL
        SELECT e.channel_id, es2.id
          FROM evidence_subject es2 JOIN biophysics_experiment e
            ON es2.subject_type = 'BIOPHYSICS_EXPERIMENT'
           AND es2.subject_id = e.id
      ) channel_subjects
        ON channel_subjects.evidence_subject_id = es.id
      JOIN scope ON channel_subjects.channel_id = scope.channel_id
)
SELECT
    COUNT(*) FILTER (WHERE review_state = 'ACCEPTED') AS accepted,
    COUNT(*) FILTER (WHERE review_state = 'PROVISIONAL') AS provisional,
    COUNT(*) FILTER (WHERE review_state = 'REVIEWED') AS reviewed,
    COUNT(*) FILTER (WHERE review_state = 'UNREVIEWED') AS unreviewed,
    COUNT(*) FILTER (WHERE review_state = 'CONFLICTED') AS conflicted,
    COUNT(*) AS total,
    MAX(review_timestamp) AS last_review_date
FROM items
"""

_SEMANTIC_XREF_UNION = """
    SELECT channel_id FROM channel_external_reference
    UNION ALL
    SELECT b.channel_id
      FROM bioactivity b JOIN compound_external_reference x
        ON x.compound_id = b.compound_id
    UNION ALL
    SELECT v.channel_id FROM variant v
      JOIN variant_external_reference x ON x.variant_id = v.id
    UNION ALL
    SELECT s.channel_id FROM structure s
      JOIN structure_external_reference x ON x.structure_id = s.id
    UNION ALL
    SELECT e.channel_id FROM biophysics_experiment e
      JOIN experiment_external_reference x ON x.experiment_id = e.id
"""

_LEGACY_XREF_UNION = """
    SELECT entity_id AS channel_id FROM external_reference
     WHERE entity_type = 'CHANNEL'
    UNION ALL
    SELECT b.channel_id
      FROM bioactivity b JOIN external_reference x
        ON x.entity_type = 'COMPOUND' AND x.entity_id = b.compound_id
    UNION ALL
    SELECT v.channel_id FROM variant v
      JOIN external_reference x
        ON x.entity_type = 'VARIANT' AND x.entity_id = v.id
    UNION ALL
    SELECT s.channel_id FROM structure s
      JOIN external_reference x
        ON x.entity_type = 'STRUCTURE' AND x.entity_id = s.id
    UNION ALL
    SELECT e.channel_id FROM biophysics_experiment e
      JOIN external_reference x
        ON x.entity_type = 'BIOPHYSICS_EXPERIMENT' AND x.entity_id = e.id
"""


def _mapping(engine: Engine, sql: str, parameters: dict | None = None) -> dict:
    with engine.connect() as connection:
        row = connection.execute(text(sql), parameters or {}).mappings().one()
    return dict(row)


def _semantic_tables_present(engine: Engine) -> bool:
    required = {
        "channel_external_reference",
        "compound_external_reference",
        "variant_external_reference",
        "structure_external_reference",
        "experiment_external_reference",
    }
    with engine.connect() as connection:
        available = set(inspect(connection).get_table_names())
        return required <= available


def _scope(
    engine: Engine,
    scope_type: str,
    scope_key: str,
    channel_scope: str,
) -> dict:
    substitutions = {
        "channel_scope": channel_scope,
        "xref_union": (
            _SEMANTIC_XREF_UNION
            if _semantic_tables_present(engine)
            else _LEGACY_XREF_UNION
        ),
    }
    parameters = None if scope_key == "all" else {"scope": scope_key}

    def run(sql: str) -> dict:
        return _mapping(engine, sql.format(**substitutions), parameters)

    return {
        "scope_type": scope_type,
        "scope_key": scope_key,
        "totals": run(_TOTALS_SQL),
        "coverage": run(_COVERAGE_SQL),
        "linkage": run(_LINKAGE_SQL),
        "review": _review(engine, _REVIEW_SQL.format(**substitutions), parameters),
    }


def _review(engine: Engine, sql: str, parameters: dict | None = None) -> dict:
    row = _mapping(engine, sql, parameters)
    last_review = row.pop("last_review_date")
    row["last_review_date"] = (
        last_review.isoformat() if hasattr(last_review, "isoformat") else last_review
    )
    return row


def coverage_payload(engine: Engine) -> dict:
    """Return all deterministic coverage statistics for issue #104."""
    channel_rows: list[dict] = []
    with engine.connect() as connection:
        if "channel" in set(inspect(connection).get_table_names()):
            for row in connection.execute(
                text(
                    "SELECT id, family, gene_symbol FROM channel "
                    "ORDER BY family, gene_symbol, id"
                )
            ).mappings():
                channel_rows.append(dict(row))

    family_names = sorted({str(row["family"]) for row in channel_rows})
    payload = {
        "data_freeze_tag": data_freeze_tag(engine),
        "data_layer": in_scope_entry("analysis.coverage.counts").layer.value,
        "computed_layer": in_scope_entry("analysis.coverage.counts").layer.value,
        "no_core_schema_change": NO_CORE_SCHEMA_CHANGE_DISCLOSURE,
        "all": _scope(engine, "all", "all", "SELECT * FROM channel"),
        "families": [],
        "channels": [
            _scope(
                engine,
                "channel",
                str(row["gene_symbol"]),
                "SELECT * FROM channel WHERE gene_symbol = :scope",
            )
            for row in channel_rows
        ],
    }
    payload["all"]["totals"].update(_database_totals(engine))
    for name in family_names:
        payload["families"].append(
            {
                **_scope(
                    engine,
                    "family",
                    name,
                    "SELECT * FROM channel WHERE family = :scope",
                ),
                "channels": [
                    item["scope_key"]
                    for item in payload["channels"]
                    if next(
                        row
                        for row in channel_rows
                        if row["gene_symbol"] == item["scope_key"]
                    )["family"]
                    == name
                ],
            }
        )
    return payload


def _database_totals(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM publication) AS publications, "
                    "(SELECT COUNT(*) FROM compound) AS compounds, "
                    "(SELECT COUNT(*) FROM evidence_item) AS evidence_items"
                )
            )
            .mappings()
            .one()
        )
    return {key: int(value) for key, value in dict(row).items()}

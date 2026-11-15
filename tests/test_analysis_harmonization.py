"""Artifact-gated pins for the P1 harmonization deep module.

Seam: the public ``harmonize(engine) -> HarmonizedCorpus`` interface —
the single owner of value-row reads + conversions from the frozen
artifact (spec §4's P1 list). All pins are census-class (generated,
``tests/census_snapshot.json`` keys cited per test); the module's
conversions themselves are exactly pinned by the leaf-module tests
(``test_analysis_units.py`` etc.). This file pins the CORPUS — that
the deep module's outputs equal the frozen artifact's censuses — not
the leaf arithmetic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maicdb.analysis.harmonization import harmonize
from maicdb.query import open_readonly

DB_PATH = Path(__file__).parents[1] / "db" / "maicdb.sqlite"

requires_db = pytest.mark.skipif(
    not DB_PATH.exists(), reason=f"published DB not found at {DB_PATH}"
)

pytestmark = requires_db


@pytest.fixture(scope="module")
def engine():
    eng = open_readonly(DB_PATH)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def corpus(engine):
    return harmonize(engine)


class TestP50:
    def test_record_census(self, corpus, census_snapshot):
        """Census: biophysics.p50_records / p50_unit_split /
        p50_sign_split (generated pins — COUNT of p50_value rows, GROUP
        BY p50_unit, and the negative/positive/zero sign split over the
        mmHg domain)."""
        bp = census_snapshot["biophysics"]
        records = corpus.p50
        assert len(records) == bp["p50_records"]
        units = {
            r.p50_unit: sum(1 for x in records if x.p50_unit == r.p50_unit)
            for r in records
        }
        assert units == bp["p50_unit_split"]
        neg = sum(1 for r in records if r.p50_mmhg < 0)
        pos = sum(1 for r in records if r.p50_mmhg > 0)
        zero = sum(1 for r in records if r.p50_mmhg == 0)
        assert [neg, pos, zero] == bp["p50_sign_split"]

    def test_deterministic_order(self, corpus):
        """``ORDER BY maicdb_id`` — the corpus is deterministic: same
        artifact, byte-identical outputs (spec §4 design rule)."""
        ids = [r.maicdb_id for r in corpus.p50]
        assert ids == sorted(ids)


class TestTau:
    def test_totals_census(self, corpus, census_snapshot):
        """Census: biophysics.kinetics_totals (generated pin — COUNT of
        non-NULL values per tau column). Kinetics are column-native ms
        (ADR-0005 unit policy); harmonization adds no conversion."""
        totals = census_snapshot["biophysics"]["kinetics_totals"]
        assert sum(1 for r in corpus.tau if r.tau_act_ms is not None) == totals["tau_act"]
        assert (
            sum(1 for r in corpus.tau if r.tau_inact_ms is not None)
            == totals["tau_inact"]
        )
        assert (
            sum(1 for r in corpus.tau if r.tau_deact_ms is not None)
            == totals["tau_deact"]
        )

    def test_deterministic_order(self, corpus):
        ids = [r.maicdb_id for r in corpus.tau]
        assert ids == sorted(ids)


class TestBioactivity:
    def test_row_census(self, corpus, census_snapshot):
        """Census: atlas.matrix_activity_rows (generated pin — every
        bioactivity row feeding the compound × channel matrix)."""
        assert len(corpus.bioactivity) == census_snapshot["atlas"]["matrix_activity_rows"]

    def test_basis_census(self, corpus, census_snapshot):
        """Census: activity.pactivity_bases (generated pin — basis
        distribution over these same rows). The corpus resolves
        p_activity per row; NULL units pass through as None (basis
        missing_value), never coerced to ""."""
        bases = census_snapshot["activity"]["pactivity_bases"]
        counts: dict[str, int] = {}
        for r in corpus.bioactivity:
            counts[r.pa.basis] = counts.get(r.pa.basis, 0) + 1
        assert counts == bases

    def test_deterministic_order(self, corpus):
        ids = [r.maicdb_id for r in corpus.bioactivity]
        assert ids == sorted(ids)


class TestDeltaP50:
    def test_row_census(self, corpus, census_snapshot):
        """Census: atlas.delta_p50_rows / delta_p50_units /
        delta_p50_gene_split (generated pins over the ΔP50 effect-size
        rows)."""
        a = census_snapshot["atlas"]
        rows = corpus.delta_p50
        assert len(rows) == a["delta_p50_rows"]
        units: dict[str, int] = {}
        genes: dict[str, int] = {}
        for r in rows:
            units[r.unit] = units.get(r.unit, 0) + 1
            genes[r.gene_symbol] = genes.get(r.gene_symbol, 0) + 1
        assert units == a["delta_p50_units"]
        assert genes == a["delta_p50_gene_split"]

    def test_variant_census(self, corpus, census_snapshot):
        """Census: atlas.variant_linked_rows / variant_positions /
        domain_covered_total (generated pins — linkage, positions,
        structural-domain mappings)."""
        a = census_snapshot["atlas"]
        linked = [r for r in corpus.delta_p50 if r.variant_linked]
        assert len(linked) == a["variant_linked_rows"]
        positions = sorted(
            r.variant_position for r in linked if r.variant_position is not None
        )
        assert positions == sorted(a["variant_positions"])
        assert sum(len(r.domains) for r in corpus.delta_p50) == a["domain_covered_total"]

    def test_deterministic_order(self, corpus):
        ids = [r.maicdb_id for r in corpus.delta_p50]
        assert ids == sorted(ids)


class TestSameFit:
    def test_join_census(self, corpus, census_snapshot):
        """Census: joins.marker_hit_count / candidate_count (generated
        pins — slope-only rows carrying a same-fit marker, and the
        (slope, threshold) candidate pairs they spawn)."""
        j = census_snapshot["joins"]
        assert len(corpus.same_fit_hits) == j["marker_hit_count"]
        assert len(corpus.same_fit) == j["candidate_count"]

    def test_hits_are_slope_only_rows(self, corpus):
        """Discovery input is the slope-only subset: every marker hit's
        row is a slope-only row of the corpus."""
        slope_ids = {r.maicdb_id for r in corpus.slope_rows}
        for hit in corpus.same_fit_hits:
            assert hit.maicdb_id in slope_ids

    def test_deterministic_order(self, corpus):
        slope_ids = [r.maicdb_id for r in corpus.slope_rows]
        assert slope_ids == sorted(slope_ids)
        pairs = [(c.slope_maicdb_id, c.threshold_maicdb_id) for c in corpus.same_fit]
        assert pairs == sorted(pairs)


class TestCorpus:
    def test_deterministic(self, corpus, engine):
        """Spec §4 design rule: same artifact, byte-identical outputs —
        two full reads produce equal corpora (candidate pairing is
        order-stable, not just count-stable)."""
        assert harmonize(engine) == corpus

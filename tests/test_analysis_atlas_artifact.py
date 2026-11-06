"""Artifact-gated pins for the P5 atlas (Track C).

Two pin kinds, disclosed per test (P2–P4 convention):

* raw-SQL-re-derivable pins cite the census SQL that recomputes the
  number from ``db/maicdb.sqlite``;
* module-output determinism pins (cell counts, anchors) whose inputs
  are pinned by the raw-SQL censuses alongside.

The dominant disclosed fact: the spec's structural-domain mapping and
much of the variant chain are DATA-THIN at data-v1.0 — every such
vacuity is pinned as the honest descriptive result (they are curation
demands, not analysis defects).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from maicdb.analysis.atlas import (
    compound_channel_matrix,
    delta_p50_table,
    selectivity_index,
)
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
def effects(engine):
    return delta_p50_table(engine)


@pytest.fixture(scope="module")
def matrix(engine):
    return compound_channel_matrix(engine)


class TestDeltaP50:
    def test_sixteen_rows_all_mmhg(self, effects):
        """Census: COUNT(delta_p50_value) → 16; all rows mmHg (GROUP BY
        delta_p50_unit); value range 5.0–61.7 (MIN/MAX)."""
        assert len(effects) == 16
        assert {r.unit for r in effects} == {"mmHg"}
        assert min(r.delta_p50 for r in effects) == 5.0
        assert max(r.delta_p50 for r in effects) == pytest.approx(61.7, abs=1e-9)

    def test_variant_chain_is_data_thin(self, effects):
        """Census pins for every link of the spec's variant chain:
        variant-linked rows → 3 (SUM(variant_id IS NOT NULL)); the 3
        linked variants carry NULL hgvs_protein and NULL
        functional_effect; positions on 2 of 3 (both 2456 — JOIN
        variant); the structural-domain mapping is VACUOUS —
        COUNT(residues_covered) and COUNT(coverage_pct) on structure →
        0 of 12 — so all 16 rows map to zero domains. Each vacuity is
        a curation demand (spec §5.2's own pattern), pinned here so
        future curation that fills them turns this test green-on-new
        facts, not silently."""
        assert sum(1 for r in effects if r.variant_linked) == 3
        assert all(r.variant is None for r in effects)
        assert all(r.functional_effect is None for r in effects)
        assert sorted(
            r.variant_position for r in effects if r.variant_position is not None
        ) == [2456, 2456]
        assert sum(1 for r in effects if r.domains) == 0

    def test_gene_split(self, effects):
        """Census (JOIN channel GROUP BY gene over ΔP50 rows): MscL 1,
        MscS 9, PIEZO1 6."""
        from collections import Counter

        counts = Counter(r.gene_symbol for r in effects)
        assert counts == Counter({"MscS": 9, "PIEZO1": 6, "MscL": 1})


class TestMatrix:
    def test_sparse_shape(self, matrix):
        """Census: 136 activity rows (all with activity_value); 73
        distinct compound × channel pairs → the matrix has 73 cells
        summing k=136 (21 pairs carry >1 measurement — the 63 extra
        rows aggregate into cell means, n per cell). Possible cells
        69 × 9 = 621 → ~12% populated: sparse by construction."""
        assert len(matrix) == 73
        assert sum(c.k for c in matrix) == 136
        multi_extra = sum(c.k - 1 for c in matrix)
        assert multi_extra == 63

    def test_value_coverage_and_bases(self, engine, matrix):
        """Census via P1's basis classes (the bioactivity corpus): 70
        of 73 cells resolve a mean pActivity; basis totals over all
        136 measurements — molar 128, missing_value 3 (NULL units,
        passed through as None so the basis names the truth),
        already_plog 1, mass_no_mw 4 (μg/ml silica rows without MW) —
        exactly MATCHING P1's own artifact census of these same rows
        (tests/test_analysis_artifact.py TestPActivityPins). Also
        pinned here (gate PR #77 MINOR-2): pchembl is NULL on all 136
        rows (SELECT COUNT(pchembl) FROM bioactivity → 0) — the
        value-axis choice rests on it; a future release that fills
        pchembl must revisit this module."""
        with engine.connect() as conn:
            pchembl_null = conn.execute(
                text("SELECT COUNT(*) FROM bioactivity WHERE pchembl IS NULL")
            ).one()[0]
        assert pchembl_null == 136
        with_value = [c for c in matrix if c.pactivity is not None]
        assert len(with_value) == 70
        bases: dict[str, int] = {}
        for c in matrix:
            for basis, n in c.basis_counts:
                bases[basis] = bases.get(basis, 0) + n
        assert bases == {
            "molar": 128,
            "missing_value": 3,
            "already_plog": 1,
            "mass_no_mw": 4,
        }

    def test_family_distribution(self, matrix):
        """Census (JOIN channel GROUP BY family over the 73 pairs):
        K2P 36, TRP 13, DEG/ENaC/ASIC 8, TMC 7, PIEZO 6, OSCA/TMEM63 2,
        MscL/MscS 1."""
        from collections import Counter

        counts = Counter(c.family for c in matrix)
        assert counts == Counter(
            {
                "K2P": 36,
                "TRP": 13,
                "DEG_ENaC_ASIC": 8,
                "TMC": 7,
                "PIEZO": 6,
                "OSCA_TMEM63": 2,
                "MSCL_MSCS": 1,
            }
        )


class TestSelectivity:
    def test_rows_and_the_single_gapped_compound(self, matrix):
        """Module-output determinism: 66 compounds have ≥1 populated
        channel; exactly 4 have ≥2 (a measurable off-target gap). The
        largest gap: gadolinium (Gd3+) — best TRAAK 5.301, off-target
        TMC, gap 1.121 (inputs census-derivable from its bioactivity
        rows; determinism pin on the aggregation)."""
        si = selectivity_index(matrix)
        assert len(si) == 66
        gapped = [r for r in si if r.selectivity_gap is not None]
        assert len(gapped) == 4
        top = max(gapped, key=lambda r: r.selectivity_gap)
        assert top.compound_name == "gadolinium (Gd3+)"
        assert top.best_channel == "TRAAK"
        assert top.best_pactivity == pytest.approx(5.301, abs=1e-3)
        assert top.best_off_target_channel == "TMC"
        assert top.selectivity_gap == pytest.approx(1.121, abs=1e-3)

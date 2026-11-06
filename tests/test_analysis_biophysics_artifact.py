"""Artifact-gated pins for the P4 biophysics meta-analyses (Track B).

Two pin kinds, disclosed per test (P2/P3/P6 convention):

* raw-SQL-re-derivable pins cite the census SQL that recomputes the
  number from ``db/maicdb.sqlite``;
* module-output determinism pins (D–L pooled means, I², CI/PI bounds,
  kinetics quartiles, ΔG demo) whose INPUTS are pinned by the raw-SQL
  censuses alongside — the D–L arithmetic itself is exactly pinned by
  hand-computed cases in ``tests/test_analysis_biophysics.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from maicdb.analysis.biophysics import (
    KPA_PER_MMHG,
    boltzmann_demo,
    kinetics_atlas,
    lab_spread,
    load_p50_records,
    threshold_meta,
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
def records(engine):
    return load_p50_records(engine)


class TestInputCensuses:
    def test_p50_corpus(self, records):
        """Census: p50_value COUNT → 152; units 148 mmHg + 4 psi
        (GROUP BY p50_unit); negatives 88 (SUM(p50_value < 0)); zeros 0
        (the log domain's hard guard); positives 64."""
        assert len(records) == 152
        units = {r.p50_unit: sum(1 for x in records if x.p50_unit == r.p50_unit)
                 for r in records}
        assert units == {"mmHg": 148, "psi": 4}
        neg = sum(1 for r in records if r.p50_mmhg < 0)
        pos = sum(1 for r in records if r.p50_mmhg > 0)
        zero = sum(1 for r in records if r.p50_mmhg == 0)
        assert (neg, pos, zero) == (88, 64, 0)

    def test_condition_key_degeneration(self, engine):
        """Census (the cluster-fallback justification): P50 rows with a
        condition_key → 152, DISTINCT condition_key → 152 — the spec's
        publication × condition_key unit is record-level on data-v1.0,
        so the module clusters at publication level (see
        ``biophysics.cluster_key``)."""
        with engine.connect() as conn:
            n, k = conn.execute(
                text(
                    "SELECT COUNT(*), COUNT(DISTINCT condition_key) FROM "
                    "biophysics_experiment WHERE p50_value IS NOT NULL "
                    "AND condition_key IS NOT NULL"
                )
            ).one()
        assert (n, k) == (152, 152)

    def test_cell_structure(self, records):
        """Census (JOIN channel, GROUP BY family, stimulus_type over P50
        rows): n and distinct publications per cell —
        K2P/PC 3/1, K2P/SUCTION 12/4, MSCL/PC 19/7, MSCL/SUCTION 23/6,
        OSCA/PC 36/7, PIEZO/PP 5/2, PIEZO/PC 45/9, PIEZO/SUCTION 6/2,
        TMC/PC 2/1, TRP/PC 1/1."""
        cells: dict[tuple[str, str | None], tuple[int, int]] = {}
        for r in records:
            key = (r.family, r.stimulus_type)
            n, pubs = cells.get(key, (0, 0))
            cells[key] = (n + 1, pubs)  # pubs filled below
        pubs_map: dict[tuple[str, str | None], set[int]] = {}
        for r in records:
            pubs_map.setdefault((r.family, r.stimulus_type), set()).add(
                r.publication_id
            )
        for key, pubset in pubs_map.items():
            n, _ = cells[key]
            cells[key] = (n, len(pubset))
        assert cells == {
            ("K2P", "PRESSURE_CLAMP"): (3, 1),
            ("K2P", "SUCTION"): (12, 4),
            ("MSCL_MSCS", "PRESSURE_CLAMP"): (19, 7),
            ("MSCL_MSCS", "SUCTION"): (23, 6),
            ("OSCA_TMEM63", "PRESSURE_CLAMP"): (36, 7),
            ("PIEZO", "POSITIVE_PRESSURE"): (5, 2),
            ("PIEZO", "PRESSURE_CLAMP"): (45, 9),
            ("PIEZO", "SUCTION"): (6, 2),
            ("TMC", "PRESSURE_CLAMP"): (2, 1),
            ("TRP", "PRESSURE_CLAMP"): (1, 1),
        }


class TestThresholdMeta:
    @pytest.fixture(scope="class")
    def cells(self, records):
        return {(c.family, c.stimulus_type): c for c in threshold_meta(records)}

    def test_ten_cells_dual_report(self, cells):
        """Module-output determinism; inputs pinned above. Pooled |P50|
        geometric means, dual-reported (kPa = mmHg × 0.133322387415
        exactly — one identity pinned numerically)."""
        assert len(cells) == 10
        pz = cells[("PIEZO", "PRESSURE_CLAMP")]
        assert pz.k == 9 and pz.n == 45
        assert pz.pooled_mmhg == pytest.approx(35.1375, abs=1e-4)
        assert pz.pooled_kpa == pytest.approx(
            pz.pooled_mmhg * KPA_PER_MMHG, abs=1e-12
        )
        assert pz.pooled_kpa == pytest.approx(4.6846, abs=1e-4)

    def test_heterogeneity_is_real(self, cells):
        """Module-output determinism: I² spans 0.61–0.97 across the
        identifiable cells — high between-paper heterogeneity, the
        honest Track-B result. Anchors: PIEZO/PC 0.9419, OSCA/PC
        0.9686, K2P/SUCTION 0.6111."""
        assert cells[("PIEZO", "PRESSURE_CLAMP")].i2 == pytest.approx(
            0.9419, abs=1e-4
        )
        assert cells[("OSCA_TMEM63", "PRESSURE_CLAMP")].i2 == pytest.approx(
            0.9686, abs=1e-4
        )
        assert cells[("K2P", "SUCTION")].i2 == pytest.approx(0.6111, abs=1e-4)

    def test_identifiability_gate(self, cells):
        """TRP/PC (1 pub, 1 record — census above) stays descriptive:
        identifiable False, CI/PI/τ²/Q/I² None, pooled still reported.
        TMC/PC (1 pub, 2 records) has an identifiable s²_w but k=1 →
        inferential fields None; K2P/PC (1 pub, 3 records) same."""
        trp = cells[("TRP", "PRESSURE_CLAMP")]
        assert trp.identifiable is False
        assert trp.ci_mmhg is None and trp.pi_mmhg is None and trp.i2 is None
        assert trp.pooled_mmhg == pytest.approx(18.0, abs=1e-12)
        for key in (("TMC", "PRESSURE_CLAMP"), ("K2P", "PRESSURE_CLAMP")):
            c = cells[key]
            assert c.identifiable is True and c.k == 1
            assert c.ci_mmhg is None and c.pi_mmhg is None

    def test_sign_split_disclosed(self, cells):
        """Census (SUM(p50_value < 0) per cell): negative counts —
        PIEZO/PC 23, OSCA/PC 29, MSCL/PC 14, MSCL/SUCTION 2, K2P/PC 3,
        PIEZO/PP 0, TRP/PC 0; mixed signs INSIDE cells (e.g. PIEZO/PC)
        is the disclosed sign-convention finding."""
        assert cells[("PIEZO", "PRESSURE_CLAMP")].negative_n == 23
        assert cells[("OSCA_TMEM63", "PRESSURE_CLAMP")].negative_n == 29
        assert cells[("MSCL_MSCS", "PRESSURE_CLAMP")].negative_n == 14
        assert cells[("MSCL_MSCS", "SUCTION")].negative_n == 2
        assert cells[("K2P", "PRESSURE_CLAMP")].negative_n == 3
        assert cells[("PIEZO", "POSITIVE_PRESSURE")].negative_n == 0
        assert cells[("TRP", "PRESSURE_CLAMP")].negative_n == 0

    def test_ci_pi_brackets(self, cells):
        """Structural check on the determinism outputs: every
        identifiable cell's CI brackets its pooled mean; the k=2
        PIEZO/PP cell's Higgins PI is (deliberately) enormous — tau²
        with 2 papers — disclosed here so the width never surprises."""
        for c in cells.values():
            if c.ci_mmhg is not None:
                lo, hi = c.ci_mmhg
                assert lo < c.pooled_mmhg < hi
        pp = cells[("PIEZO", "POSITIVE_PRESSURE")]
        assert pp.pi_mmhg is not None
        assert pp.pi_mmhg[0] < 1.0  # wider than the data range: k=2 tau²


class TestKineticsAtlas:
    def test_cells_and_totals(self, engine):
        """Census: tau_act 45, tau_inact 93, tau_deact 40 (COUNT per
        column); module cells = 23 (gene × kind); genes = the 10
        channel genes with tau data. No non-positive tau exists
        (census: SUM(col <= 0) = 0 per column)."""
        ka = kinetics_atlas(engine)
        assert len(ka) == 23
        totals = {"tau_act": 0, "tau_inact": 0, "tau_deact": 0}
        genes: set[str] = set()
        for c in ka:
            totals[c.kind] += c.k
            genes.add(c.gene_symbol)
        assert totals == {"tau_act": 45, "tau_inact": 93, "tau_deact": 40}
        assert genes == {
            "ASIC", "MscL", "MscS", "OSCA", "PIEZO1", "PIEZO2",
            "TMC", "TRAAK", "TREK-1", "TRPV4",
        }

    def test_anchor(self, engine):
        """Module-output determinism: ASIC tau_inact — k 14, 5 pubs,
        geo mean 437.692 ms, median 513.809 ms (inputs census-pinned:
        COUNT(tau_inact_ms JOIN gene ASIC) → 14)."""
        ka = kinetics_atlas(engine)
        anchor = next(c for c in ka if c.gene_symbol == "ASIC"
                      and c.kind == "tau_inact")
        assert anchor.k == 14 and anchor.n_pubs == 5
        assert anchor.geo_mean_ms == pytest.approx(437.692, abs=1e-3)
        assert anchor.median_ms == pytest.approx(513.809, abs=1e-3)
        assert anchor.min_ms > 0
        assert anchor.min_ms <= anchor.median_ms <= anchor.max_ms


class TestLabSpread:
    def test_nine_cells_with_anchors(self, records):
        """Module-output determinism; gate = ≥2 distinct publications
        per (gene, stimulus). 9 cells. Anchors: PIEZO1/PC k 9 n 45 geo
        35.14 sd 0.199; MscL/SUCTION k 4 n 17 geo 83.76 sd 0.1431.
        Signed range kept as-reported: MscL/PC spans −163.0..255.0 —
        the sign-convention inconsistency made visible per gene."""
        ls = lab_spread(records)
        assert len(ls) == 9
        by_key = {(c.gene_symbol, c.stimulus_type): c for c in ls}
        pz = by_key[("PIEZO1", "PRESSURE_CLAMP")]
        assert (pz.k, pz.n) == (9, 45)
        assert pz.geo_mean_mmhg == pytest.approx(35.14, abs=1e-2)
        assert pz.geo_sd_log10 == pytest.approx(0.199, abs=1e-3)
        ms = by_key[("MscL", "SUCTION")]
        assert (ms.k, ms.n) == (4, 17)
        assert ms.geo_mean_mmhg == pytest.approx(83.76, abs=1e-2)
        assert ms.geo_sd_log10 == pytest.approx(0.1431, abs=1e-3)
        mpc = by_key[("MscL", "PRESSURE_CLAMP")]
        assert (mpc.min_mmhg, mpc.max_mmhg) == (-163.0, 255.0)


class TestBoltzmannDemo:
    def test_four_p50_pairs_methods_demo(self, engine):
        """Consumes P1's join (6 narrowed pairs; the p50-kind subset is
        4 — 00110→00109 and 00793→00792 are T50-kind, P1's digest pins
        the full 6). Determinism pins for one pair: 00197→00190,
        token overlap 13, P50 76.3 mmHg, slope 5.0, ΔG 15.26 (kBT,
        pressure-Boltzmann reading — METHODS DEMO, n forbids claims;
        the negative-P50 pairs yield negative ΔG, the same sign-
        convention artifact disclosed module-wide)."""
        with engine.connect() as conn:
            ck = {
                str(r["maicdb_id"]): (r["condition_key"] or "")
                for r in conn.execute(
                    text("SELECT maicdb_id, condition_key FROM "
                         "biophysics_experiment")
                ).mappings()
            }
        demo = boltzmann_demo(engine, ck)
        assert len(demo) == 4
        ids = [(d["slope_maicdb_id"], d["threshold_maicdb_id"]) for d in demo]
        assert ids == [
            ("MAIC:BX:00197", "MAIC:BX:00190"),
            ("MAIC:BX:00749", "MAIC:BX:00748"),
            ("MAIC:BX:00785", "MAIC:BX:00784"),
            ("MAIC:BX:00806", "MAIC:BX:00799"),
        ]
        top = demo[0]
        assert top["token_overlap"] == 13
        assert top["p50_mmhg"] == pytest.approx(76.3, abs=1e-9)
        assert top["slope"] == 5.0
        assert top["delta_g_kbt"] == pytest.approx(15.26, abs=1e-2)
        neg = demo[1]
        assert neg["delta_g_kbt"] == pytest.approx(-8.025, abs=1e-2)

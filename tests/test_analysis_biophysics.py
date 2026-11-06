"""Pure P4 tests for maicdb.analysis.biophysics (no artifact).

The D–L cases are HAND-COMPUTED exact arithmetic (documented inline) —
no canned meta-analysis library output is available to pin against, so
the expected values are derived symbolically here and every scipy call
in the implementation (chi2.sf / norm.ppf / t.ppf) is re-invoked in the
assertions to pin the ARGUMENTS, not the library itself.
Live behavior is pinned separately in
``tests/test_analysis_biophysics_artifact.py``.
"""

from __future__ import annotations

import pytest
from scipy import stats as sps

from maicdb.analysis.biophysics import (
    KPA_PER_MMHG,
    cluster_log_means,
    dersimonian_laird,
    lab_spread,
    threshold_meta,
)
from maicdb.analysis.biophysics import P50Record


def _rec(
    mid: str,
    mmhg: float,
    pub: int,
    family: str = "PIEZO",
    stim: str | None = "PRESSURE_CLAMP",
    gene: str = "PIEZO1",
) -> P50Record:
    return P50Record(
        maicdb_id=mid,
        channel_id=1,
        gene_symbol=gene,
        family=family,
        stimulus_type=stim,
        publication_id=pub,
        condition_key=None,
        p50_mmhg=mmhg,
        p50_unit="mmHg",
        p50_value=mmhg,
        n=1,
    )


class TestDLExact:
    """Hand-computed D–L arithmetic on symmetric cases."""

    def test_two_clusters_homogeneous(self):
        # θ = (2.0, 2.1), v = (0.01, 0.01): w = (100, 100)
        # θ_FE = 2.05; Q = 100*0.0025*2 = 0.5; df = 1
        # tau² = max(0, (0.5-1)/(200 - 20000/200)) = max(0, -0.005) = 0
        # w* = w → pooled = 2.05; SE = sqrt(1/200)
        clusters = [(1, 2.0, 0.01, 5), (2, 2.1, 0.01, 5)]
        r = dersimonian_laird(clusters)
        assert r.identifiable is True
        assert r.k == 2 and r.n == 10
        assert r.q == pytest.approx(0.5, abs=1e-12)
        assert r.q_df == 1
        assert r.tau2 == 0.0
        assert r.pooled_log10 == pytest.approx(2.05, abs=1e-12)
        assert r.se == pytest.approx(0.07071067811865477, abs=1e-12)
        z = float(sps.norm.ppf(0.975))  # pins the z-call, not scipy itself
        assert r.ci_low_log10 == pytest.approx(2.05 - z * r.se, abs=1e-12)
        assert r.ci_high_log10 == pytest.approx(2.05 + z * r.se, abs=1e-12)
        assert r.i2 == 0.0  # Q < df → truncated to 0
        assert r.q_p == pytest.approx(float(sps.chi2.sf(0.5, 1)), abs=1e-15)
        t1 = float(sps.t.ppf(0.975, 1))
        assert r.pi_low_log10 == pytest.approx(2.05 - t1 * r.se, abs=1e-12)
        assert r.pi_high_log10 == pytest.approx(2.05 + t1 * r.se, abs=1e-12)
        # dual-report identities (ADR-0005)
        assert r.pooled_mmhg() == pytest.approx(10.0**2.05, abs=1e-12)
        assert r.pooled_kpa() == pytest.approx(10.0**2.05 * KPA_PER_MMHG, abs=1e-15)

    def test_three_clusters_heterogeneous(self):
        # θ = (2.0, 2.1, 2.3), v = 0.01 each: θ_FE = 2.1333… (13/6)
        # Q = 100*(0.133333² + 0.033333² + 0.166667²) = 100*(14/300)
        #    = 14/3 ≈ 4.666667; df = 2 → Q > df
        # tau² = (14/3 - 2) / (300 - 30000/300) = (8/3)/200 = 1/75
        # w* = 1/(0.01 + 1/75) = 300/7 ≈ 42.8571 each (symmetric → pooled
        #      stays 32/15 = 2.133333…; NOTE 32/15, not 13/6 = 2.16667 —
        #      gate round 1 corrected the comment's fraction, gate PR #75
        #      MINOR-1); SE = sqrt(7/900) = 0.0881917
        # I² = (14/3 - 2)/(14/3) = (8/3)/(14/3) = 4/7 ≈ 0.5714286
        clusters = [(1, 2.0, 0.01, 4), (2, 2.1, 0.01, 4), (3, 2.3, 0.01, 4)]
        r = dersimonian_laird(clusters)
        assert r.tau2 == pytest.approx(1 / 75, abs=1e-12)
        assert r.q == pytest.approx(14 / 3, abs=1e-12)
        assert r.pooled_log10 == pytest.approx(2.1333333, abs=1e-6)
        assert r.se == pytest.approx(0.0881917, abs=1e-6)
        assert r.i2 == pytest.approx(0.5714286, abs=1e-6)
        t2 = float(sps.t.ppf(0.975, 2))
        half = t2 * (r.se**2 + r.tau2) ** 0.5
        assert r.pi_low_log10 == pytest.approx(r.pooled_log10 - half, abs=1e-12)
        assert r.pi_high_log10 == pytest.approx(r.pooled_log10 + half, abs=1e-12)

    def test_non_identifiable_flagged(self):
        # every cluster a single record: the variance placeholder (1.0)
        # is arbitrary — the flag must say so and the PI must be None
        clusters = [(1, 2.0, 1.0, 1), (2, 2.1, 1.0, 1)]
        r = dersimonian_laird(clusters)
        assert r.identifiable is False
        assert r.pi_low_log10 is None and r.pi_high_log10 is None

    def test_single_cluster_gives_df_zero(self):
        r = dersimonian_laird([(1, 2.0, 0.01, 3)])
        assert r.k == 1 and r.q_df == 0
        assert r.q_p == 1.0  # df=0 → p set to 1
        assert r.pi_low_log10 is None

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            dersimonian_laird([])


class TestClusterLogMeans:
    def test_magnitude_domain_and_negative_support(self):
        # negative P50s enter as |P50| (sign conventions vary by paper)
        recs = [_rec("A", -100.0, pub=1), _rec("B", 100.0, pub=1)]
        out = cluster_log_means(recs)
        assert len(out) == 1
        key, mean, var, n = out[0]
        assert key == 1 and n == 2
        assert mean == pytest.approx(2.0, abs=1e-12)  # log10(100)
        assert var == pytest.approx(0.0, abs=1e-12)

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            cluster_log_means([_rec("A", 0.0, pub=1)])

    def test_pooled_within_variance_math(self):
        # pub1: [2.0, 3.0] (var 0.5, n=2); pub2: [1.0] (n=1)
        # s²_w = 0.5*(2-1) / (2-1) = 0.5
        # pub1: var = 0.5/2 = 0.25; pub2: var = 0.5/1 = 0.5
        recs = [
            _rec("A", 100.0, pub=1),   # log 2
            _rec("B", 1000.0, pub=1),  # log 3
            _rec("C", 10.0, pub=2),    # log 1
        ]
        out = cluster_log_means(recs)
        by_key = {k: (m, v, n) for k, m, v, n in out}
        assert by_key[1][0] == pytest.approx(2.5, abs=1e-12)
        assert by_key[1][1] == pytest.approx(0.25, abs=1e-12)
        assert by_key[1][2] == 2
        assert by_key[2][0] == pytest.approx(1.0, abs=1e-12)
        assert by_key[2][1] == pytest.approx(0.5, abs=1e-12)
        assert by_key[2][2] == 1


class TestThresholdMeta:
    def test_modality_split_never_pools(self):
        # same family, two stimuli → two cells even for one gene
        recs = [
            _rec("A", -30.0, pub=1, stim="SUCTION"),
            _rec("B", 30.0, pub=2, stim="PRESSURE_CLAMP"),
        ]
        cells = threshold_meta(recs)
        assert len(cells) == 2
        assert {(c.family, c.stimulus_type) for c in cells} == {
            ("PIEZO", "SUCTION"),
            ("PIEZO", "PRESSURE_CLAMP"),
        }
        for c in cells:
            assert c.pooled_mmhg == pytest.approx(30.0, abs=1e-9)

    def test_sign_split_disclosed(self):
        recs = [
            _rec("A", -30.0, pub=1),
            _rec("B", -40.0, pub=2),
            _rec("C", 50.0, pub=3),
        ]
        (cell,) = threshold_meta(recs)
        assert cell.negative_n == 2 and cell.positive_n == 1
        assert cell.pooled_mmhg == pytest.approx(
            (30.0 * 40.0 * 50.0) ** (1 / 3), abs=1e-9
        )

    def test_identifiability_gate(self):
        # all singletons: pooled |P50| still reported, inferential None
        recs = [
            _rec("A", -30.0, pub=1),
            _rec("B", 40.0, pub=2),
            _rec("C", 50.0, pub=3),
        ]
        (cell,) = threshold_meta(recs)
        assert cell.identifiable is False
        assert cell.ci_mmhg is None and cell.pi_mmhg is None
        assert cell.tau2_log10 is None and cell.i2 is None and cell.q is None
        assert cell.q_p is None
        assert cell.pooled_mmhg > 0

    def test_sorted_cells_and_multi_record_inference(self):
        recs = [
            _rec("A", 20.0, pub=1, family="K2P"),
            _rec("B", 30.0, pub=1, family="K2P"),  # pub 1 has 2 rows
            _rec("C", 40.0, pub=2, family="K2P"),
        ]
        (cell,) = threshold_meta(recs)
        assert cell.k == 2 and cell.n == 3
        assert cell.identifiable is True
        assert cell.ci_mmhg is not None
        lo, hi = cell.ci_mmhg
        assert lo < cell.pooled_mmhg < hi


class TestLabSpread:
    def test_gene_pubs_gate_and_signed_range(self):
        recs = [
            _rec("A", -30.0, pub=1, gene="PIEZO1"),
            _rec("B", 60.0, pub=2, gene="PIEZO1"),
            _rec("C", 70.0, pub=2, gene="PIEZO1"),
            _rec("D", 40.0, pub=1, gene="TMC"),   # TMC: one pub only
            _rec("E", 50.0, pub=9, gene="TMC"),   # second pub, 1 row each
        ]
        cells = lab_spread(recs)
        # the view's gate is ≥2 distinct publications: PIEZO1 (pubs 1+2)
        # and TMC (pubs 1+9, one record each) both enter
        assert {(c.gene_symbol, c.k) for c in cells} == {
            ("PIEZO1", 2),
            ("TMC", 2),
        }
        pz = next(c for c in cells if c.gene_symbol == "PIEZO1")
        assert pz.n == 3
        assert pz.min_mmhg == -30.0 and pz.max_mmhg == 70.0  # as-reported
        # geo_mean is the D–L pooled |P50| over CLUSTER means (pub1's
        # cluster mean is 30; pub2's is mean(60,70)=65) — NOT the
        # record-level geometric mean. The D–L arithmetic itself is
        # exactly pinned in TestDLExact; here we pin the structural
        # property (pooled lies within the cluster-mean bounds) and the
        # spread, whose formula is a direct ddof=1 std of cluster means.
        import math

        import numpy as np

        # cluster means live in the LOG domain: pub2's is
        # mean(log10 60, log10 70) = log10(geo-mean 64.81…), NOT log10(65)
        cluster_logs = [
            math.log10(30.0),
            (math.log10(60.0) + math.log10(70.0)) / 2,
        ]
        assert 30.0 < pz.geo_mean_mmhg < 65.0
        assert pz.geo_mean_mmhg != pytest.approx(
            float(10.0 ** np.mean(cluster_logs)), abs=1e-3
        )  # D–L weights differ from the equal-weight mean here
        expected_sd = float(np.std(cluster_logs, ddof=1))
        assert pz.geo_sd_log10 == pytest.approx(expected_sd, abs=1e-12)

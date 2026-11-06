"""Cross-family biophysics meta-analyses (P4, Track B).

Authority: spec §5.2 on top of P1's harmonization (``units``,
``replicates``) and the same-fit row join (``joins``). Guardrails
(spec §6): log scale throughout, geometric means with n and k, no
pooling across stimulus modalities, k/n on every output, and the
Boltzmann demo stays a methods demo (0 of 948 rows carry P50 and slope
together — census-pinned; n forbids claims).

First consumer of numpy/scipy — spec §4 names THIS phase as the
dependency entry point (user decision 2026-11-06: numpy + scipy, with
the spec as justification; matplotlib stays out until P7 renders).

Statistical core — DerSimonian–Laird (D–L) random effects on log10
threshold magnitudes, clustered at the PUBLICATION level:

* Spec §5.2 names ``publication × condition_key`` as the study unit;
  at data-v1.0 that unit degenerates (condition_key is unique per P50
  row — 152 rows / 152 distinct keys, artifact-census-pinned), so the
  cluster falls back to the publication, the spec's
  dependence-respecting intent. The fallback and census are pinned in
  the artifact tests.
* cluster effect θ_i = mean of the paper's log10 |P50| values;
* within-cluster variance v_i = s²_w / n_i where s²_w is the pooled
  within-cluster variance (papers with ≥2 rows contribute). Cells
  where s²_w is NOT identifiable (no paper carries ≥2 rows) get NO
  inferential statistics — ``threshold_meta`` gates them to
  descriptive (pooled |P50| + k/n only); CI/PI/τ²/Q/I² from a
  placeholder variance would be fabricated uncertainty;
* heterogeneity: Q with df = k−1 (p-value via
  ``scipy.stats.chi2.sf``), tau² by the D–L moment estimator
  (truncated at 0), I² = max(0, (Q − df)/Q);
* pooled estimate θ = Σw*θ/Σw* with w* = 1/(v_i + tau²), SE =
  sqrt(1/Σw*), 95% CI = θ ± z_0.975 · SE (z from
  ``scipy.stats.norm.ppf``);
* prediction interval (Higgins): θ ± t_{k−1, 0.975} · sqrt(SE² + tau²)
  (``scipy.stats.t.ppf``); defined for identifiable cells with k ≥ 2.

Threshold cells split by stimulus modality (spec: pressure never pools
with indentation or stretch — at data-v1.0 every P50 row is a pressure
stimulus, census-pinned). Dual reporting per ADR-0005: pooled
geometric means in mmHg AND kPa (kPa = mmHg × 0.133322387415, the
exact mmHg→kPa identity through the Pa pivot of P1's ``units``).

Sign conventions are a corpus finding, disclosed not silently
normalized: 88 of 152 P50 values are NEGATIVE, and signs are mixed
INSIDE single family × stimulus cells (e.g. PIEZO pressure-clamp spans
−63.0 to 76.9 mmHg) — papers report suction/pressure-clamp activation
thresholds under inconsistent sign conventions. The pooled statistic is
|P50| on log10; every cell carries the negative/positive split, and
``lab_spread`` keeps the as-reported signed range per gene (the
inconsistency is itself a MIMIC-relevant reporting-standard
observation).

Temperature (9% populated) is a listed covariate with a missing-data
flag — no Q10 at v1 (spec).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats as sps
from sqlalchemy import text as sql_text
from sqlalchemy.engine import Engine

from maicdb.analysis.units import pressure_to_mmhg

__all__ = [
    "KPA_PER_MMHG",
    "P50Record",
    "DLResult",
    "MetaCell",
    "KineticsCell",
    "SpreadCell",
    "load_p50_records",
    "cluster_log_means",
    "dersimonian_laird",
    "threshold_meta",
    "kinetics_atlas",
    "lab_spread",
]

# Exact mmHg -> kPa (through P1's Pa pivot: 1 mmHg = 133.322387415 Pa).
KPA_PER_MMHG = 0.133322387415

_P50_SQL = sql_text(
    "SELECT e.maicdb_id AS maicdb_id, e.p50_value AS p50_value,"
    " e.p50_unit AS p50_unit, e.stimulus_type AS stimulus_type,"
    " e.publication_id AS publication_id, e.condition_key AS condition_key,"
    " e.n AS n, e.n_cells AS n_cells,"
    " c.id AS channel_id, c.gene_symbol AS gene_symbol, c.family AS family"
    " FROM biophysics_experiment e"
    " JOIN channel c ON e.channel_id = c.id"
    " WHERE e.p50_value IS NOT NULL"
    " ORDER BY e.maicdb_id"
)

_TAU_SQL = sql_text(
    "SELECT e.maicdb_id AS maicdb_id, e.publication_id AS publication_id,"
    " c.gene_symbol AS gene_symbol, c.family AS family,"
    " e.tau_act_ms AS tau_act_ms, e.tau_inact_ms AS tau_inact_ms,"
    " e.tau_deact_ms AS tau_deact_ms"
    " FROM biophysics_experiment e"
    " JOIN channel c ON e.channel_id = c.id"
    " WHERE e.tau_act_ms IS NOT NULL OR e.tau_inact_ms IS NOT NULL"
    " OR e.tau_deact_ms IS NOT NULL"
    " ORDER BY e.maicdb_id"
)


@dataclass(frozen=True)
class P50Record:
    """One P50-bearing record, harmonized to canonical mmHg."""

    maicdb_id: str
    channel_id: int
    gene_symbol: str
    family: str
    stimulus_type: str | None
    publication_id: int
    condition_key: str | None
    p50_mmhg: float
    p50_unit: str  # as reported (ADR-0005 keeps the reported pair)
    p50_value: float  # as reported
    n: int  # coalesced replicate count of the record (n_cells wins over
    # the legacy text n); the meta-analysis clusters at PUBLICATION
    # level and counts records — see cluster_key/cluster_log_means


def load_p50_records(engine: Engine) -> list[P50Record]:
    """Load every P50-bearing record, harmonized; deterministic order."""
    from maicdb.analysis.replicates import coalesce_replicates

    out: list[P50Record] = []
    with engine.connect() as conn:
        for row in conn.execute(_P50_SQL).mappings():
            unit = row["p50_unit"] or ""
            converted = pressure_to_mmhg(float(row["p50_value"]), unit)
            rep = coalesce_replicates(row["n_cells"], row["n"])
            n_i = rep.value if rep.value is not None else 1
            out.append(
                P50Record(
                    maicdb_id=str(row["maicdb_id"]),
                    channel_id=int(row["channel_id"]),
                    gene_symbol=str(row["gene_symbol"]),
                    family=str(row["family"]),
                    stimulus_type=row["stimulus_type"],
                    publication_id=int(row["publication_id"]),
                    condition_key=row["condition_key"],
                    p50_mmhg=converted.value,
                    p50_unit=unit,
                    p50_value=float(row["p50_value"]),
                    n=int(n_i or 1),
                )
            )
    return out


def cluster_key(record: P50Record) -> int:
    """The meta-analysis study unit: the publication.

    Spec §5.2 names ``publication × condition_key``; at data-v1.0 that
    unit DEGENERATES — condition_key is unique per row (152 P50 rows /
    152 distinct keys, artifact-census-pinned), so pub×condition equals
    record level and no within-cluster variance is ever identifiable
    (every cluster would be a single record and the D–L variances would
    be arbitrary placeholders). This module therefore clusters at the
    publication level — the spec's dependence-respecting INTENT — and
    the identifiability gate in ``threshold_meta`` keeps cells without
    at least one multi-record publication descriptive (no CI/PI/I²).
    The degeneration census and the fallback are disclosed in the PR
    and artifact tests.
    """
    return record.publication_id


def cluster_log_means(
    records: Sequence[P50Record],
) -> list[tuple[int, float, float, int]]:
    """Per-cluster (publication_id, log10 |P50| mean, within-cluster
    variance, n).

    The log domain is the threshold MAGNITUDE: 88 of 152 data-v1.0 P50
    values are negative (suction/pressure-clamp papers report the
    activation threshold under sign conventions that vary BY PAPER —
    mixed signs occur inside single family × stimulus cells), so the
    pooled statistic is |P50| on log10, and every consuming view
    discloses the per-cell sign split. Zero cannot enter the log
    domain — raises loudly (no zeros in the corpus, census-pinned).

    Clusters with a single record get the pooled within-cluster
    variance s²_w; if no cluster has n ≥ 2, s²_w is undefined and every
    variance is 1.0 — callers must treat such cells as non-identifiable
    (``threshold_meta``'s gate) and keep them descriptive.
    """
    groups: dict[int, list[float]] = {}
    for r in records:
        if r.p50_mmhg == 0:
            raise ValueError(
                f"{r.maicdb_id}: P50 of exactly 0 cannot enter the log domain"
            )
        groups.setdefault(cluster_key(r), []).append(np.log10(abs(r.p50_mmhg)))
    multi_pairs = [
        (vals, float(np.var(vals, ddof=1)))
        for vals in groups.values()
        if len(vals) >= 2
    ]
    if multi_pairs:
        n_w = sum(len(vals) for vals, _ in multi_pairs) - len(multi_pairs)
        s2_w = float(
            sum(var * (len(vals) - 1) for vals, var in multi_pairs) / n_w
        )
    else:
        s2_w = 1.0
    out: list[tuple[int, float, float, int]] = []
    for key, vals in sorted(groups.items()):
        n_i = len(vals)
        var_i = float(np.var(vals, ddof=1)) / n_i if n_i >= 2 else s2_w / n_i
        out.append((key, float(np.mean(vals)), var_i, n_i))
    return out


@dataclass(frozen=True)
class DLResult:
    """DerSimonian–Laird random-effects summary of log10 values.

    ``identifiable`` is False when no cluster carries ≥2 records (the
    within-cluster variance placeholder is then arbitrary) — consumers
    must NOT publish CI/PI/I² from a non-identifiable result.
    """

    k: int  # clusters
    n: int  # records
    identifiable: bool  # ≥1 cluster with n ≥ 2 (s²_w data-driven)
    pooled_log10: float  # θ (log10 domain)
    se: float
    ci_low_log10: float
    ci_high_log10: float
    tau2: float
    q: float
    q_df: int
    q_p: float
    i2: float  # fraction 0..1 (truncated at 0)
    pi_low_log10: float | None  # prediction interval (identifiable, k ≥ 2)
    pi_high_log10: float | None

    def pooled_mmhg(self) -> float:
        return 10.0 ** self.pooled_log10

    def pooled_kpa(self) -> float:
        return 10.0 ** self.pooled_log10 * KPA_PER_MMHG

    def ci_mmhg(self) -> tuple[float, float]:
        return 10.0 ** self.ci_low_log10, 10.0 ** self.ci_high_log10

    def pi_mmhg(self) -> tuple[float, float] | None:
        if self.pi_low_log10 is None or self.pi_high_log10 is None:
            return None
        return 10.0 ** self.pi_low_log10, 10.0 ** self.pi_high_log10


def dersimonian_laird(
    clusters: Sequence[tuple[int, float, float, int]],
) -> DLResult:
    """D–L random effects over (key, log10 mean, variance, n) tuples.

    The result is flagged non-identifiable when no cluster carries ≥2
    records (within-cluster variances are then the arbitrary 1.0
    placeholder of ``cluster_log_means``); consumers gate on it.
    """
    k = len(clusters)
    n_total = sum(c[3] for c in clusters)
    theta = np.array([c[1] for c in clusters], dtype=float)
    v = np.array([c[2] for c in clusters], dtype=float)
    if k == 0:
        raise ValueError("no clusters to meta-analyze")
    identifiable = any(c[3] >= 2 for c in clusters)
    w = 1.0 / v
    theta_fe = float(np.sum(w * theta) / np.sum(w))
    q = float(np.sum(w * (theta - theta_fe) ** 2))
    df = k - 1
    q_p = float(sps.chi2.sf(q, df)) if df > 0 else 1.0
    if k >= 2:
        w_sum = float(np.sum(w))
        w2_sum = float(np.sum(w**2))
        tau2 = max(0.0, (q - df) / (w_sum - w2_sum / w_sum))
    else:
        tau2 = 0.0
    w_star = 1.0 / (v + tau2)
    pooled = float(np.sum(w_star * theta) / np.sum(w_star))
    se = float(np.sqrt(1.0 / np.sum(w_star)))
    z = float(sps.norm.ppf(0.975))
    i2 = max(0.0, (q - df) / q) if q > 0 else 0.0
    if identifiable and k >= 2:
        t_crit = float(sps.t.ppf(0.975, df))
        half_pi = t_crit * np.sqrt(se**2 + tau2)
        pi_low, pi_high = pooled - float(half_pi), pooled + float(half_pi)
    else:
        pi_low = pi_high = None
    return DLResult(
        k=k,
        n=n_total,
        identifiable=identifiable,
        pooled_log10=pooled,
        se=se,
        ci_low_log10=pooled - z * se,
        ci_high_log10=pooled + z * se,
        tau2=tau2,
        q=q,
        q_df=df,
        q_p=q_p,
        i2=i2,
        pi_low_log10=pi_low,
        pi_high_log10=pi_high,
    )


# --- views ---------------------------------------------------------------


@dataclass(frozen=True)
class MetaCell:
    """One (family, stimulus modality) threshold cell, dual-reported.

    Pooled statistics are |P50| on log10 — the sign split
    (``negative_n``/``positive_n``) discloses the papers' sign
    conventions, which are NOT uniform (mixed signs occur within single
    cells at data-v1.0; the module docstring carries the full story).
    """

    family: str
    stimulus_type: str | None
    k: int  # clusters (publications)
    n: int  # records
    identifiable: bool  # False → CI/PI/I²/τ² are None (descriptive cell)
    negative_n: int  # records reported with a negative sign
    positive_n: int  # records reported with a positive sign
    pooled_mmhg: float  # geometric mean of |P50|
    pooled_kpa: float
    ci_mmhg: tuple[float, float] | None  # None when not identifiable
    pi_mmhg: tuple[float, float] | None
    tau2_log10: float | None
    q: float | None
    q_p: float | None
    i2: float | None


def threshold_meta(records: Sequence[P50Record]) -> list[MetaCell]:
    """Per (family, stimulus_type) D–L cells on |P50|; cells whose
    within-paper variance is not identifiable (no multi-record
    publication, or a single cluster) stay descriptive — CI/PI/τ²/Q/I²
    all None, the pooled |P50| geometric mean remains. Sorted by family
    then modality (None last). Never pools across modalities (spec
    §5.2/§6)."""
    cells: dict[tuple[str, str | None], list[P50Record]] = {}
    for r in records:
        cells.setdefault((r.family, r.stimulus_type), []).append(r)
    out: list[MetaCell] = []
    for (family, stim), recs in sorted(
        cells.items(), key=lambda kv: (kv[0][0], kv[0][1] is not None, kv[0][1] or "")
    ):
        clusters = cluster_log_means(recs)
        result = dersimonian_laird(clusters)
        inferential = result.identifiable and result.k >= 2
        neg = sum(1 for r in recs if r.p50_mmhg < 0)
        out.append(
            MetaCell(
                family=family,
                stimulus_type=stim,
                k=result.k,
                n=result.n,
                identifiable=result.identifiable,
                negative_n=neg,
                positive_n=result.n - neg,
                pooled_mmhg=result.pooled_mmhg(),
                pooled_kpa=result.pooled_kpa(),
                ci_mmhg=result.ci_mmhg() if inferential else None,
                pi_mmhg=result.pi_mmhg() if inferential else None,
                tau2_log10=result.tau2 if inferential else None,
                q=result.q if inferential else None,
                q_p=result.q_p if inferential else None,
                i2=result.i2 if inferential else None,
            )
        )
    return out


@dataclass(frozen=True)
class KineticsCell:
    """One (gene, tau kind) descriptive cell (log-scale distribution)."""

    gene_symbol: str
    kind: str  # "tau_act" | "tau_inact" | "tau_deact"
    k: int  # records
    n_pubs: int  # distinct publications
    geo_mean_ms: float
    q1_ms: float
    median_ms: float
    q3_ms: float
    min_ms: float
    max_ms: float


_TAU_COLUMNS = (
    ("tau_act_ms", "tau_act"),
    ("tau_inact_ms", "tau_inact"),
    ("tau_deact_ms", "tau_deact"),
)


def kinetics_atlas(engine: Engine) -> list[KineticsCell]:
    """Per (gene, tau kind) log-scale descriptive distributions.

    No pooling statistic across families (spec); quartiles in the ms
    domain (back-transformed from log10). Deterministic order.
    """
    groups: dict[tuple[str, str], list[tuple[float, int]]] = {}
    with engine.connect() as conn:
        for row in conn.execute(_TAU_SQL).mappings():
            for col, kind in _TAU_COLUMNS:
                value = row[col]
                if value is None:
                    continue
                if value <= 0:
                    raise ValueError(
                        f"{row['maicdb_id']}: non-positive {col} {value} "
                        "cannot enter the log domain"
                    )
                groups.setdefault((str(row["gene_symbol"]), kind), []).append(
                    (float(value), int(row["publication_id"]))
                )
    out: list[KineticsCell] = []
    for (gene, kind), pairs in sorted(groups.items()):
        values = np.array([v for v, _ in pairs], dtype=float)
        logs = np.log10(values)
        q1, med, q3 = np.percentile(logs, [25.0, 50.0, 75.0])
        out.append(
            KineticsCell(
                gene_symbol=gene,
                kind=kind,
                k=len(values),
                n_pubs=len({p for _, p in pairs}),
                geo_mean_ms=float(10.0 ** logs.mean()),
                q1_ms=float(10.0**q1),
                median_ms=float(10.0**med),
                q3_ms=float(10.0**q3),
                min_ms=float(values.min()),
                max_ms=float(values.max()),
            )
        )
    return out


@dataclass(frozen=True)
class SpreadCell:
    """One (gene, stimulus modality) between-lab spread cell.

    Reproducibility view (spec §5.2): same channel × same stimulus
    across labs — descriptive, k (studies) and n (records) cited.
    ``geo_mean_mmhg`` is the |P50| geometric mean (sign conventions
    vary by paper — see the module docstring); ``min_mmhg``/
    ``max_mmhg`` keep the AS-REPORTED signed range, which makes the
    sign-convention inconsistency visible per gene.
    Only genes with ≥2 distinct publications enter.
    """

    gene_symbol: str
    stimulus_type: str | None
    k: int  # distinct publications ("labs")
    n: int  # records
    geo_mean_mmhg: float
    geo_sd_log10: float  # SD of cluster log10 means (between-lab spread)
    min_mmhg: float  # as-reported signed
    max_mmhg: float  # as-reported signed


def lab_spread(records: Sequence[P50Record]) -> list[SpreadCell]:
    """Between-lab spread per (gene, stimulus modality); ≥2 labs only."""
    cells: dict[tuple[str, str | None], list[P50Record]] = {}
    for r in records:
        cells.setdefault((r.gene_symbol, r.stimulus_type), []).append(r)
    out: list[SpreadCell] = []
    for (gene, stim), recs in sorted(
        cells.items(), key=lambda kv: (kv[0][0], kv[0][1] is not None, kv[0][1] or "")
    ):
        pubs = {r.publication_id for r in recs}
        if len(pubs) < 2:
            continue
        clusters = cluster_log_means(recs)
        logs = np.array([c[1] for c in clusters], dtype=float)
        result = dersimonian_laird(clusters)
        out.append(
            SpreadCell(
                gene_symbol=gene,
                stimulus_type=stim,
                k=len(pubs),
                n=result.n,
                geo_mean_mmhg=result.pooled_mmhg(),
                geo_sd_log10=float(logs.std(ddof=1)),
                min_mmhg=float(min(r.p50_mmhg for r in recs)),
                max_mmhg=float(max(r.p50_mmhg for r in recs)),
            )
        )
    return out


# --- Boltzmann ΔG methods demo (spec: n forbids claims) -----------------


def boltzmann_demo(
    engine: Engine,
    condition_key_of: Mapping[str, str],
) -> list[dict[str, object]]:
    """The same-fit Boltzmann demo, consuming P1's join.

    Census caveat (spec §5.2, verified at data-v1.0): P50 and slope
    never co-occur on one row (0 of 948); same-fit pairs are split
    across rows, linked only by ``condition_key`` prose, and narrowed
    by P1's token-overlap heuristic (a disclosed number, not truth).
    ΔG/kBT = P50_mmhg / slope per joined pair (pressure-Boltzmann
    reading; slope dimensionless). Note 3 of the 4 data-v1.0 rows have
    NEGATIVE ΔG — the negative-P50 pairs carry the paper's sign
    convention into the quotient (the same corpus-wide sign-convention
    artifact disclosed module-wide). METHODS DEMO — the output exists
    to show the join works; n forbids any claim.
    """
    from maicdb.analysis.joins import narrow_by_condition_key, same_fit_candidates

    with engine.connect() as conn:
        p50_of = {
            str(r["maicdb_id"]): (float(r["p50_value"]), r["p50_unit"])
            for r in conn.execute(
                sql_text("SELECT maicdb_id, p50_value, p50_unit FROM "
                         "biophysics_experiment WHERE p50_value IS NOT NULL")
            ).mappings()
        }
        slope_of = {
            str(r["maicdb_id"]): float(r["slope"])
            for r in conn.execute(
                sql_text("SELECT maicdb_id, slope FROM biophysics_experiment "
                         "WHERE slope IS NOT NULL")
            ).mappings()
        }
    joined = narrow_by_condition_key(same_fit_candidates(engine), condition_key_of)
    demo: list[dict[str, object]] = []
    for cand in joined:
        if cand.kind != "p50":
            continue
        threshold = p50_of.get(cand.threshold_maicdb_id)
        slope = slope_of.get(cand.slope_maicdb_id)
        if threshold is None or slope is None or slope == 0:
            continue
        converted = pressure_to_mmhg(*threshold)
        demo.append(
            {
                "slope_maicdb_id": cand.slope_maicdb_id,
                "threshold_maicdb_id": cand.threshold_maicdb_id,
                "marker": cand.marker,
                "token_overlap": cand.token_overlap,
                "p50_mmhg": converted.value,
                "slope": slope,
                "delta_g_kbt": converted.value / slope,
            }
        )
    demo.sort(key=lambda d: (str(d["slope_maicdb_id"]), str(d["threshold_maicdb_id"])))
    return demo

"""Artifact-gated pins for the P3 MIMIC compliance audit (Track A).

Two pin kinds, disclosed per test (same convention as the P2 file):

* raw-SQL-re-derivable pins cite the census SQL that recomputes the
  number directly from ``db/maicdb.sqlite``;
* module-output determinism pins (era/breakdown/weighted means, heatmap
  compliance ratios) cannot be re-derived by trivial SQL without
  reimplementing the scorer — their role is regression detection; their
  INPUTS (join coverage, era sizes, group k, applicable counts) are
  pinned by the raw-SQL censuses alongside.

Enforcement caveat worth its own note: the ADR-aware any-field failure
count (899) is pinned against the NULL-safe CASE-form census. The naive
``NOT (stimulus_type = 'INDENTATION' AND probe_geometry IS NULL)``
complement form is NULL-poisoned — UNKNOWN rows drop out of the clean
set and it returns 24 instead of the true 49 (live witness 2026-11-06:
both forms ran on data-v1.0 during derivation; the module follows
ADR-0005, a NULL stimulus excludes the dependent fields).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from maicdb.analysis.audit import (
    breakdown,
    category_weighted_mean,
    compliance_by_year,
    field_totals,
    four_field_audit,
    heatmap,
    load_families,
    load_meta,
)
from maicdb.analysis.mimic import score_all
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
def scores(engine):
    return score_all(engine)


@pytest.fixture(scope="module")
def meta(engine):
    return load_meta(engine)


@pytest.fixture(scope="module")
def records(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM biophysics_experiment ORDER BY maicdb_id")
        ).mappings()
        return [dict(r) for r in rows]


class TestLoaderCensuses:
    def test_full_coverage(self, scores, meta, engine):
        """Census: 948 experiments (spec §3), every row joins to a
        channel family and a publication year (``SELECT COUNT(*) FROM
        biophysics_experiment e LEFT JOIN channel c ... LEFT JOIN
        publication p ... WHERE c.family IS NULL OR p.year IS NULL`` →
        0)."""
        assert len(scores) == 948
        assert len(meta) == 948
        assert all(m.family is not None for m in meta.values())
        assert all(m.year is not None for m in meta.values())
        assert all(m.journal is not None for m in meta.values())

    def test_family_slices(self, engine, scores):
        """Census: 12 channels; experiments per family — DEG/ENaC/ASIC
        108, K2P 145, MscL/MscS 192, OSCA/TMEM63 92, PIEZO 188, TMC 153,
        TRP 70 (GROUP BY c.family over the experiment join)."""
        families = load_families(engine)
        assert len(families) == 12
        counts: dict[str, int] = {}
        for s in scores:
            counts[families[s.channel_id]] = (
                counts.get(families[s.channel_id], 0) + 1
            )
        assert counts == {
            "DEG_ENaC_ASIC": 108,
            "K2P": 145,
            "MSCL_MSCS": 192,
            "OSCA_TMEM63": 92,
            "PIEZO": 188,
            "TMC": 153,
            "TRP": 70,
        }

    def test_era_coverage(self, scores, meta):
        """Census: publication year present on all 948 (1986–2026);
        pre-2010 = 239 rows, post = 709 (``WHERE p.year < 2010`` /
        ``>= 2010``)."""
        era = compliance_by_year(scores, {k: m.year for k, m in meta.items()})
        assert era.pre_k == 239
        assert era.post_k == 709
        assert era.unassigned_k == 0


class TestFieldTotals:
    """The family-axis-collapsed totals; always-applicable fields must
    reproduce spec §3's populated census exactly."""

    def test_environment_fields(self, scores):
        """Census: temperature_c COUNT → 85 (9% — the spec's headline);
        ph → 547; recording_mode non-null/non-empty → 909 (96%;
        NULLIF form)."""
        totals = field_totals(scores)
        temp = totals["temperature_c"]
        assert (temp.reported, temp.not_extracted, temp.applicable) == (85, 863, 948)
        assert temp.compliance == pytest.approx(85 / 948, abs=1e-9)
        ph = totals["ph"]
        assert (ph.reported, ph.applicable) == (547, 948)
        rec = totals["recording_mode"]
        assert (rec.reported, rec.not_extracted, rec.applicable) == (909, 39, 948)

    def test_conditional_velocity_denominator(self, scores):
        """Census: stimulus_type IN (INDENTATION, TOUCH, SHEAR_STRESS) →
        129 applicable; stimulus_velocity populated → 0 (spec §3) — so
        ADR-aware velocity compliance is exactly 0.0 on data-v1.0."""
        totals = field_totals(scores)
        vel = totals["stimulus_velocity"]
        assert (vel.reported, vel.applicable) == (0, 129)
        assert vel.compliance == 0.0

    def test_cell_type(self, scores):
        """Census: NULLIF(cell_type,'') IS NULL → 167 (82% populated —
        spec §3)."""
        cell = field_totals(scores)["cell_type"]
        assert (cell.reported, cell.not_extracted, cell.applicable) == (781, 167, 948)


class TestHeatmap:
    def test_temperature_by_family_cells(self, engine, scores):
        """Census: temperature_c reported per family — DEG/ENaC/ASIC 10,
        K2P 34, MscL/MscS 0, OSCA/TMEM63 10, PIEZO 4, TMC 0, TRP 27
        (sums to 85; JOIN channel GROUP BY family)."""
        hm = heatmap(scores, load_families(engine))
        assert set(hm) == {
            "DEG_ENaC_ASIC", "K2P", "MSCL_MSCS", "OSCA_TMEM63",
            "PIEZO", "TMC", "TRP",
        }
        per_family = {f: hm[f]["temperature_c"].reported for f in hm}
        assert per_family == {
            "DEG_ENaC_ASIC": 10, "K2P": 34, "MSCL_MSCS": 0,
            "OSCA_TMEM63": 10, "PIEZO": 4, "TMC": 0, "TRP": 27,
        }
        # determinism pin: PIEZO temperature compliance 4/188
        assert hm["PIEZO"]["temperature_c"].compliance == pytest.approx(
            4 / 188, abs=1e-9
        )
        assert hm["MSCL_MSCS"]["temperature_c"].compliance == 0.0


class TestEnforcement:
    """The vault §9 four-field headline under both readings."""

    def test_as_written_row_counts(self, scores, records):
        """Census (applicability ignored, vault §9's own reading):
        stimulus_velocity IS NULL → 948; probe_geometry IS NULL → 948;
        NULLIF(recording_mode,'') IS NULL → 39; context (NULLIF
        cell_type OR temperature_c IS NULL) → 882 (joint presence 66);
        any-field OR-form → 948 of 948 — the 100% motivation number."""
        audit = four_field_audit(records)
        rows = audit.fields
        assert rows["stimulus_velocity"].missing_as_written == 948
        assert rows["probe_geometry"].missing_as_written == 948
        assert rows["recording_mode"].missing_as_written == 39
        assert rows["experimental_context"].missing_as_written == 882
        assert audit.failing_any_as_written == (948, 948)
        assert rows["stimulus_velocity"].as_written_fail_rate == 1.0
        assert rows["experimental_context"].as_written_fail_rate == (
            pytest.approx(882 / 948, abs=1e-9)
        )

    def test_adr_aware_row_counts(self, scores, records):
        """Census (ADR-0005 applicability): velocity applicable (moving
        probe IN-list) 129, missing 129; geometry applicable
        (INDENTATION) 95, missing 95; recording_mode ALWAYS applicable
        (one of ADR-0005's 12 unconditional fields — applicable 948;
        the 909 figure is its POPULATED count, not its applicable set),
        missing (NULL/empty) 39; context applicable 948, incomplete
        882."""
        audit = four_field_audit(records)
        rows = audit.fields
        vel = rows["stimulus_velocity"]
        assert (vel.applicable, vel.missing_when_applicable) == (129, 129)
        assert vel.adr_fail_rate == 1.0
        geo = rows["probe_geometry"]
        assert (geo.applicable, geo.missing_when_applicable) == (95, 95)
        rec = rows["recording_mode"]
        assert (rec.applicable, rec.missing_when_applicable) == (948, 39)
        assert rec.adr_fail_rate == pytest.approx(39 / 948, abs=1e-9)
        ctx = rows["experimental_context"]
        assert (ctx.applicable, ctx.missing_when_applicable) == (948, 882)

    def test_adr_aware_any_field_null_safe(self, scores, records):
        """Census (NULL-safe CASE form — see module docstring for the
        NULL-poisoned NOT-form trap): any-field ADR-aware failures →
        899; clean set → 49 (899 + 49 = 948)."""
        audit = four_field_audit(records)
        assert audit.failing_any_adr == (899, 948)
        # clean set cross-foot
        clean = 948 - audit.failing_any_adr[0]
        assert clean == 49

    def test_the_pair_is_the_headline(self, scores, records):
        """Spec §5.1: as-written 100% fail vs ADR-aware 899/948 — both
        numbers stated, the tri-state defense visible in the gap."""
        audit = four_field_audit(records)
        assert audit.failing_any_as_written[0] == 948  # 100% as written
        assert 0 < audit.failing_any_adr[0] < 948
        # ...and the ADR-aware rate is still damning (~94.8%)
        assert audit.failing_any_adr[0] / 948 == pytest.approx(
            899 / 948, abs=1e-9
        )


class TestViews:
    def test_era_contrast_determinism(self, scores, meta):
        """Module-output determinism pins; inputs pinned by the era
        census above (239/709, span 1986–2026). Mean per-record
        compliance: pre-PIEZO 0.347260, post-PIEZO 0.446977 — the
        corpus's metadata reporting improved after 2010."""
        era = compliance_by_year(scores, {k: m.year for k, m in meta.items()})
        assert len(era.years) == 33
        assert era.years[0].year == 1986 and era.years[-1].year == 2026
        assert era.pre_mean == pytest.approx(0.347260, abs=1e-6)
        assert era.post_mean == pytest.approx(0.446977, abs=1e-6)
        # boundary rows (determinism: first/last year)
        assert (era.years[0].k, era.years[0].mean) == (
            3, pytest.approx(0.270833, abs=1e-6),
        )
        assert (era.years[-1].k, era.years[-1].mean) == (
            8, pytest.approx(0.332237, abs=1e-6),
        )

    def test_breakdown_crossfoot_and_groups(self, scores, meta):
        """Group k cross-foots against coverage censuses: recording_mode
        groups sum to 909 (39 NULL dropped — census above); family to
        948; journal to 948 across 58 distinct journals (COUNT
        DISTINCT). Determinism pins: the largest recording_mode group
        CELL_ATTACHED (k 222 — census per-mode counts in the P2 file)
        mean 0.480011; MSCL/MscS family (k 192) mean 0.438570."""
        by_mode = breakdown(scores, meta, "recording_mode")
        assert sum(g.k for g in by_mode) == 909
        ca = next(g for g in by_mode if g.group == "CELL_ATTACHED")
        assert ca.k == 222
        assert ca.mean == pytest.approx(0.480011, abs=1e-6)
        by_family = breakdown(scores, meta, "family")
        assert len(by_family) == 7 and sum(g.k for g in by_family) == 948
        mscl = next(g for g in by_family if g.group == "MSCL_MSCS")
        assert (mscl.k, mscl.mean) == (192, pytest.approx(0.438570, abs=1e-6))
        by_journal = breakdown(scores, meta, "journal")
        assert len(by_journal) == 58 and sum(g.k for g in by_journal) == 948

    def test_weighted_sensitivity(self, scores):
        """Module-output determinism pin: environment-weighted (×2,
        others 1) mean = 0.442246, ABOVE the unweighted corpus mean
        0.421838 (P2 artifact pin) — environmental fields are reported
        comparatively well, so weighting them up lifts the score. The
        direction is the sensitivity result; the magnitudes are the
        pins."""
        weights = {"environment": 2.0, "stimulus": 1.0, "recording": 1.0,
                   "cell_context": 1.0, "analysis": 1.0}
        wmean = category_weighted_mean(scores, weights)
        assert wmean == pytest.approx(0.442246, abs=1e-6)
        unweighted = sum(s.score for s in scores) / len(scores)
        assert unweighted == pytest.approx(0.421838, abs=1e-6)
        assert wmean > unweighted

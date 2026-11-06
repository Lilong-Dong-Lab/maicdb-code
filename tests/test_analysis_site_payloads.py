"""Pure tests for the P7 site-payload layer (no artifact).

Two seams:

* ``mimic_blocks_from_scores`` — the channel-badge aggregation rule,
  exercised on synthetic ``MIMICScore`` objects from ``score_record``
  (the same constructor the P3 tests use). Score-census context for the
  synthetic counts below (live-checked 2026-11-06): a v1.0 record
  without a stimulus carries 12 applicable fields; ``INDENTATION``
  adds the three probe-geometry fields (15 total).
* ``figures.render_all`` — the determinism contract (same payloads +
  same code → byte-identical PNGs), run twice on the site fixture
  payloads (``SYNTH_ANALYSIS`` from ``test_site_pages``).

Live behavior is pinned separately in
``tests/test_analysis_site_payloads_artifact.py``.
"""

from __future__ import annotations

import pytest

from maicdb.analysis.figures import FIGURES, render_all
from maicdb.analysis.mimic import MIMICScore, score_record
from maicdb.analysis.site_payloads import mimic_blocks_from_scores
from tests.test_site_pages import SYNTH_ANALYSIS


def _rec(**over: object) -> dict[str, object]:
    base: dict[str, object] = {"maicdb_id": "MAIC:BX:TEST", "channel_id": 7}
    base.update(over)
    return base


class TestMimicBlocks:
    """The channel-badge aggregation rule (spec §5.1 consumer)."""

    def test_badge_blocks_are_per_channel_sums(self):
        # A reports temperature + ph (2/12); C adds INDENTATION so the
        # probe fields turn applicable (1/15); D is a second channel —
        # blocks never mix channels
        scores = [
            score_record(_rec(maicdb_id="A", temperature_c=25.0, ph=7.4)),
            score_record(_rec(maicdb_id="C", stimulus_type="INDENTATION")),
            score_record(
                _rec(maicdb_id="D", channel_id=8, temperature_c=30.0)
            ),
        ]
        blocks = mimic_blocks_from_scores(scores)
        assert set(blocks) == {7, 8}
        b = blocks[7]
        assert b["n_records"] == 2
        # the Σ rule: block counts are sums of per-record counts
        ch7 = [s for s in scores if s.channel_id == 7]
        assert b["reported"] == sum(s.reported for s in ch7) == 3
        assert b["applicable"] == sum(s.applicable for s in ch7) == 27
        assert b["score"] == pytest.approx(3 / 27)
        # per-field Σ: temperature reported by A only, applicable on both
        assert b["fields"]["temperature_c"] == {"reported": 1, "applicable": 2}
        # velocity: applicable only on C (INDENTATION), reported by neither
        assert b["fields"]["stimulus_velocity"] == {
            "reported": 0,
            "applicable": 1,
        }
        # stimulus_type: applicable on both, reported by C only
        assert b["fields"]["stimulus_type"] == {"reported": 1, "applicable": 2}

    def test_field_level_rule_differs_from_mean_of_means(self):
        # A reports 2/12, C reports 1/15: the field-level ratio weights
        # by applicable counts (3/27 ≈ 0.1111), a mean of per-record
        # scores does not (≈ 0.1167) — the badge follows the field-level
        # reading (P3 field_totals' convention) so a small-n channel
        # cannot inflate a mean of means
        scores = [
            score_record(_rec(maicdb_id="A", temperature_c=25.0, ph=7.4)),
            score_record(_rec(maicdb_id="C", stimulus_type="INDENTATION")),
        ]
        b = mimic_blocks_from_scores(scores)[7]
        assert b["score"] == pytest.approx(3 / 27)
        assert b["score"] != pytest.approx(
            sum(s.score for s in scores) / len(scores)
        )

    def test_zero_applicable_channel_scores_none(self):
        # a record set with no applicable field scores None — the badge
        # renders "no reading", never a 0% compliance lie
        scores = [
            MIMICScore(
                maicdb_id="X",
                channel_id=9,
                score=0.0,
                reported=0,
                applicable=0,
                fields={},
            )
        ]
        b = mimic_blocks_from_scores(scores)[9]
        assert b["score"] is None
        assert b["fields"] == {}
        assert b["n_records"] == 1


class TestFigureDeterminism:
    """Same payloads + same code → byte-identical PNGs (the site's
    byte-stability rule, locked at the figure module's own seam; the
    real-build byte-stability test in test_site_build covers the whole
    tree including figures end to end)."""

    def test_render_all_is_byte_identical_across_runs(self, tmp_path):
        first = render_all(SYNTH_ANALYSIS, tmp_path / "run-a")
        second = render_all(SYNTH_ANALYSIS, tmp_path / "run-b")
        assert [p.name for p in first] == [f"{name}.png" for name in FIGURES]
        for a, b in zip(first, second):
            assert a.read_bytes() == b.read_bytes(), a.name
            assert a.read_bytes().startswith(b"\x89PNG"), a.name

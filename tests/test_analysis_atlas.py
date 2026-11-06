"""Pure atlas tests for maicdb.analysis.atlas (no artifact).

Synthetic fixtures for the range parser and the selectivity rule —
format tests, not data claims. Live behavior is pinned separately in
``tests/test_analysis_atlas_artifact.py``.
"""

from __future__ import annotations

import pytest

from maicdb.analysis.atlas import (
    MatrixCell,
    _in_covered_range,
    selectivity_index,
)


class TestCoveredRange:
    def test_inclusive_bounds(self):
        assert _in_covered_range(1, "1-2547")
        assert _in_covered_range(2547, "1-2547")
        assert _in_covered_range(1200, "1-2547")
        assert not _in_covered_range(2548, "1-2547")
        assert not _in_covered_range(0, "1-2547")

    def test_multi_range_and_bare(self):
        assert _in_covered_range(150, "1-200, 300-500")
        assert _in_covered_range(400, "1-200, 300-500")
        assert not _in_covered_range(250, "1-200, 300-500")
        assert _in_covered_range(42, "42")
        assert not _in_covered_range(43, "42")

    def test_malformed_segments_skipped(self):
        assert not _in_covered_range(10, "")
        assert not _in_covered_range(10, "  ")
        assert not _in_covered_range(10, "abc, foo-bar")
        assert _in_covered_range(10, "junk, 5-20")  # good segment survives


def _cell(
    compound: str,
    gene: str,
    pactivity: float | None,
) -> MatrixCell:
    return MatrixCell(
        compound_name=compound,
        gene_symbol=gene,
        family="PIEZO",
        k=1,
        pactivity=pactivity,
        basis_counts=(("molar", 1),),
    )


class TestSelectivityIndex:
    def test_gap_is_best_minus_second_best(self):
        cells = [
            _cell("Gd", "TRAAK", 5.301),
            _cell("Gd", "TMC", 4.180),
            _cell("Gd", "PIEZO1", 2.0),
        ]
        rows = selectivity_index(cells)
        assert len(rows) == 1
        row = rows[0]
        assert row.best_channel == "TRAAK"
        assert row.best_pactivity == pytest.approx(5.301, abs=1e-12)
        assert row.best_off_target_channel == "TMC"
        assert row.selectivity_gap == pytest.approx(1.121, abs=1e-12)
        assert row.channels_with_value == 3

    def test_single_channel_compound_has_no_gap(self):
        rows = selectivity_index([_cell("Solo", "PIEZO1", 6.0)])
        assert rows[0].selectivity_gap is None
        assert rows[0].best_off_target_channel is None
        assert rows[0].channels_with_value == 1

    def test_unresolved_cells_excluded(self):
        cells = [
            _cell("Gd", "TRAAK", 5.0),
            _cell("Gd", "TMC", None),  # mass_no_mw-style pair: no value
        ]
        (row,) = selectivity_index(cells)
        assert row.channels_with_value == 1
        assert row.selectivity_gap is None

    def test_deterministic_tie_break(self):
        # the artifact never ties (pinned there); the RULE is pinned here:
        # equal best values → the lower gene symbol wins the best slot,
        # and the gap is best minus SECOND-BEST = 0.0 on a tie (the
        # runner-up shares the best value — a genuine property of the
        # definition, not a defect)
        cells = [
            _cell("X", "TREK-1", 5.0),
            _cell("X", "ASIC", 5.0),
            _cell("X", "PIEZO1", 3.0),
        ]
        (row,) = selectivity_index(cells)
        assert row.best_channel == "ASIC"  # gene-symbol order
        assert row.best_off_target_channel == "TREK-1"
        assert row.selectivity_gap == pytest.approx(0.0, abs=1e-12)
        assert row.channels_with_value == 3

    def test_sorted_output_and_valueless_only_compound_dropped(self):
        cells = [
            _cell("B", "TMC", None),
            _cell("A", "PIEZO1", 6.0),
            _cell("C", "ASIC", 4.0),
            _cell("C", "K2P", 5.0),
        ]
        rows = selectivity_index(cells)
        assert [r.compound_name for r in rows] == ["A", "C"]
        # B has only an unresolved cell → dropped entirely (no rows lie)
        assert all(r.compound_name != "B" for r in rows)
        c = rows[1]
        assert (c.best_channel, c.selectivity_gap) == ("K2P", pytest.approx(1.0, abs=1e-12))

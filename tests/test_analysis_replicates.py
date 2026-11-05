"""Pure coalescing tests for maicdb.analysis.replicates (no artifact).

Fixtures are format examples of the legacy ``n`` text column's observed
forms (integers and integer ranges, e.g. "5-9", "3-6" — census in
``tests/test_analysis_artifact.py``); they are format checks, not data
claims.
"""

from __future__ import annotations

from maicdb.analysis.replicates import coalesce_replicates, parse_n


class TestParseN:
    def test_single_integer(self):
        rep = parse_n("12")
        assert rep.value == 12
        assert rep.source == "n_int"
        assert rep.raw == "12"

    def test_integer_with_spaces(self):
        assert parse_n(" 7 ").value == 7

    def test_range(self):
        rep = parse_n("5-9")
        assert (rep.value, rep.low, rep.high) == (None, 5, 9)
        assert rep.source == "n_range"

    def test_range_with_spaces(self):
        assert (parse_n("3 - 6").low, parse_n("3 - 6").high) == (3, 6)

    def test_censored_bound_unparsed(self):
        # observed live as MAIC:BX:00850 — kept raw, never guessed
        rep = parse_n(">4")
        assert rep.value is None and rep.low is None
        assert rep.source == "n_unparsed"
        assert rep.raw == ">4"

    def test_prose_unparsed(self):
        assert parse_n("n = 3").source == "n_unparsed"

    def test_empty_and_none(self):
        assert parse_n("").source == "none"
        assert parse_n(None).source == "none"
        assert parse_n(None).raw is None


class TestCoalesce:
    def test_n_cells_wins(self):
        rep = coalesce_replicates(9, "5-9")
        assert (rep.value, rep.source) == (9, "n_cells")
        assert rep.raw is None

    def test_fallback_to_n(self):
        rep = coalesce_replicates(None, "5-9")
        assert (rep.low, rep.high, rep.source) == (5, 9, "n_range")

    def test_both_absent(self):
        rep = coalesce_replicates(None, None)
        assert rep.source == "none"

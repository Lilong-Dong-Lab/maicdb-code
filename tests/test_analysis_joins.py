"""Pure narrowing tests for maicdb.analysis.joins (no artifact).

Regression tests for the tie contract: all siblings sharing a slope row's
top token-overlap score are kept (gate finding M1 on PR #68 — the suite
could not see this via the artifact because data-v1.0 contains no ties,
so these are synthetic format tests, not data claims).
"""

from __future__ import annotations

from maicdb.analysis.joins import (
    SameFitCandidate,
    _classify_marker,
    narrow_by_condition_key,
)


def _cand(slope: str, sib: str, kind: str = "p50") -> SameFitCandidate:
    return SameFitCandidate(
        slope_maicdb_id=slope,
        threshold_maicdb_id=sib,
        kind=kind,
        marker="same fit",
        channel_id=1,
        publication_id=1,
        token_overlap=None,
    )


class TestNarrowing:
    def test_ties_all_kept_sorted_by_threshold_id(self):
        # gate M1 regression: two siblings with the SAME top score —
        # both must survive, ordered by threshold maicdb_id
        cands = [_cand("S1", "B"), _cand("S1", "A")]
        keys = {"S1": "wild type bath ph 7", "A": "wild type bath ph 7", "B": "wild type bath ph 7"}
        out = narrow_by_condition_key(cands, keys)
        assert [(c.threshold_maicdb_id, c.token_overlap) for c in out] == [
            ("A", 5),
            ("B", 5),
        ]

    def test_strict_best_wins(self):
        cands = [_cand("S1", "A"), _cand("S1", "B")]
        keys = {
            "S1": "rkkee bath ph 7",
            "A": "rkkee bath ph 7",
            "B": "eekkr bath ph 5",
        }
        out = narrow_by_condition_key(cands, keys)
        assert len(out) == 1
        assert out[0].threshold_maicdb_id == "A"

    def test_score_zero_dropped(self):
        cands = [_cand("S1", "A")]
        keys = {"S1": "alpha beta", "A": "gamma delta"}
        assert narrow_by_condition_key(cands, keys) == []

    def test_independent_slopes_both_kept(self):
        cands = [_cand("S1", "A"), _cand("S2", "B")]
        keys = {
            "S1": "aa bb",
            "A": "aa bb",
            "S2": "cc dd",
            "B": "cc dd",
        }
        out = narrow_by_condition_key(cands, keys)
        assert {c.slope_maicdb_id for c in out} == {"S1", "S2"}


class TestSentenceClassifier:
    def test_hint_in_marker_sentence(self):
        assert (
            _classify_marker(
                "bath ph 7 (same fit as the p50 row); other stuff", 10, 34
            )
            == "p50"
        )

    def test_next_sentence_hint_does_not_leak(self):
        # gate n3 regression: ASCII "." bounds the window — a T1/2 hint in
        # the FOLLOWING sentence must not classify this marker sentence
        haystack = "(same fit as the row). The T1/2 was 11 dyn/cm."
        kind = _classify_marker(haystack, 1, 20)
        assert kind == "ambiguous"

    def test_t50_hint(self):
        assert (
            _classify_marker(
                "proteoliposome (same group fit as T1/2 row)", 15, 33
            )
            == "t50"
        )

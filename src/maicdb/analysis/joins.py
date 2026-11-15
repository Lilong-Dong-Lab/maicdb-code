"""Same-fit row join for the analysis layer (P1).

Spec §5.2 (``docs/analytics-pipeline-spec.md``): P50 and slope never
co-occur on one row of the published artifact (census-pinned as
``joins.slope_only_rows`` / ``joins.marker_hit_count``); same-fit pairs
are split across rows, linked only by ``condition_key`` prose. P1
defines the join in two honest steps:

1. Discovery — slope-only rows whose ``condition_key`` or
   ``extractor_note`` carries a same-fit marker (English "same … fit" or
   Chinese "同一拟合") are paired with every sibling row of the same
   channel and publication that has the marker's target parameter.
   Every candidate carries its marker — nothing is silently joined.
   Discovery lives in the harmonization corpus (:attr:`HarmonizedCorpus.same_fit`
   / :attr:`HarmonizedCorpus.same_fit_hits`); the functions here are
   thin delegates over the corpus.
2. :func:`narrow_by_condition_key` — deterministic narrowing. Each slope
   row keeps every sibling sharing the highest lowercase condition-key
   token overlap — ties included (the caller sees all of them, sorted by
   threshold id). Narrowing is a heuristic with disclosed scores, not
   ground truth; the Boltzmann ΔG demo (P4) consumes confirmed pairs
   only.

Data-v1.2 census (marker-bearing slope rows and candidate counts) is
pinned in ``tests/test_analysis_artifact.py`` with the census SQL that
re-derives it; the harmonization corpus test re-pins both.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from sqlalchemy.engine import Engine

from maicdb.analysis.harmonization import (
    MarkerHit,
    SameFitCandidate,
    _classify_marker,  # noqa: F401  (re-exported: unit tests pin the classifier here)
    harmonize,
)

__all__ = [
    "SameFitCandidate",
    "MarkerHit",
    "same_fit_marker_hits",
    "same_fit_candidates",
    "narrow_by_condition_key",
]


def same_fit_marker_hits(engine: Engine) -> list[MarkerHit]:
    """Find slope-only rows whose prose carries a same-fit marker."""
    return list(harmonize(engine).same_fit_hits)


def same_fit_candidates(engine: Engine) -> list[SameFitCandidate]:
    """Enumerate every (slope, threshold) candidate pair, evidence attached."""
    return list(harmonize(engine).same_fit)


def _tokens(condition_key: str) -> set[str]:
    return set(re.split(r"[^a-z0-9.]+", condition_key.lower())) - {""}


def narrow_by_condition_key(
    candidates: Iterable[SameFitCandidate],
    condition_key_of: Mapping[str, str],
) -> list[SameFitCandidate]:
    """Return the top-scoring sibling(s) per slope row by condition-key
    token overlap.

    ``condition_key_of`` maps maicdb_id → condition_key for every row in
    the candidate set (both sides). Score = |token overlap| of the two
    lowercase condition keys; all siblings sharing a slope row's top score
    are kept — ties included, sorted by threshold ``maicdb_id`` so the
    caller can apply its own tie-break — and score-0 siblings are dropped.
    Scores are written into ``token_overlap`` — a heuristic with a
    disclosed number, not truth.
    """
    scored: dict[str, list[tuple[int, str, SameFitCandidate]]] = {}
    for cand in candidates:
        slope_key = condition_key_of.get(cand.slope_maicdb_id, "")
        sib_key = condition_key_of.get(cand.threshold_maicdb_id, "")
        score = len(_tokens(slope_key) & _tokens(sib_key))
        if score <= 0:
            continue
        scored.setdefault(cand.slope_maicdb_id, []).append(
            (score, cand.threshold_maicdb_id, _with_overlap(cand, score))
        )
    out: list[SameFitCandidate] = []
    for entries in scored.values():
        top = max(e[0] for e in entries)
        out.extend(cand for score, _, cand in sorted(entries, key=lambda e: e[1]) if score == top)
    return out


def _with_overlap(cand: SameFitCandidate, score: int) -> SameFitCandidate:
    return SameFitCandidate(
        slope_maicdb_id=cand.slope_maicdb_id,
        threshold_maicdb_id=cand.threshold_maicdb_id,
        kind=cand.kind,
        marker=cand.marker,
        channel_id=cand.channel_id,
        publication_id=cand.publication_id,
        token_overlap=score,
    )

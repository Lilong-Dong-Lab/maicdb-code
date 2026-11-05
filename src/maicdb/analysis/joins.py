"""Same-fit row join for the analysis layer (P1).

ADR-0005 / spec §5.2: P50 and slope never co-occur on one row of
data-v1.0 (0 of 948); same-fit pairs are split across rows, linked only
by ``condition_key`` prose. P1 defines the join in two honest steps:

1. :func:`same_fit_candidates` — discovery. Slope-only rows (``slope``
   populated, every threshold NULL) whose ``condition_key`` or
   ``extractor_note`` carries a same-fit marker (English "same … fit" or
   Chinese "同一拟合") are paired with every sibling row of the same
   channel and publication that has the marker's target parameter
   (P50-mentioning markers → ``p50_value``; T50/T1/2-mentioning →
   ``t50_value``). Every candidate carries its marker — nothing is
   silently joined.
2. :func:`narrow_by_condition_key` — deterministic narrowing. Each slope
   row keeps the sibling with the highest lowercase condition-key token
   overlap; ties are kept (the caller sees all of them). Narrowing is a
   heuristic with disclosed scores, not ground truth; the Boltzmann ΔG
   demo (P4) consumes confirmed pairs only.

Data-v1.0 census (marker-bearing slope rows and candidate counts) is
pinned in ``tests/test_analysis_artifact.py`` with the census SQL that
re-derives it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import text as sql_text
from sqlalchemy.engine import Engine

__all__ = [
    "SameFitCandidate",
    "MarkerHit",
    "same_fit_marker_hits",
    "same_fit_candidates",
    "narrow_by_condition_key",
]

# "same fit as the p50 row", "same group fit as T1/2 row",
# "same fitted gradient", "same Fig 5A fit as WT p50 row", "同一拟合".
MARKER_RE = re.compile(r"same(?:\s+\S+){0,3}?\s+fit|同一拟合", re.IGNORECASE)

# Marker text that names the target parameter. "P1/2" is how several
# condition_keys abbreviate the P50 midpoint; "T1/2" the T50 midpoint.
_P50_HINT_RE = re.compile(r"p50|p1/2", re.IGNORECASE)
_T50_HINT_RE = re.compile(r"t50|t1/2", re.IGNORECASE)

_SLOPE_ONLY_SQL = sql_text(
    "SELECT maicdb_id, channel_id, publication_id, condition_key, "
    "extractor_note, slope FROM biophysics_experiment "
    "WHERE slope IS NOT NULL AND p50_value IS NULL "
    "AND t50_value IS NULL AND x50_value IS NULL"
)

_SIBLING_SQL = sql_text(
    "SELECT maicdb_id, condition_key, p50_value, t50_value "
    "FROM biophysics_experiment WHERE channel_id = :channel_id "
    "AND publication_id = :publication_id AND maicdb_id != :maicdb_id"
)


@dataclass(frozen=True)
class MarkerHit:
    """A slope-only row whose prose carries a same-fit marker."""

    maicdb_id: str
    channel_id: int
    publication_id: int
    condition_key: str
    marker: str  # the exact matched fragment
    kind: str  # "p50" | "t50" | "ambiguous"


@dataclass(frozen=True)
class SameFitCandidate:
    """One (slope row, threshold row) candidate pair with its evidence."""

    slope_maicdb_id: str
    threshold_maicdb_id: str
    kind: str  # "p50" | "t50"
    marker: str
    channel_id: int
    publication_id: int
    token_overlap: int | None  # set by narrow_by_condition_key; None when raw


def _classify_marker(haystack: str, marker_start: int, marker_end: int) -> str:
    """Classify by the parameter hints in the marker's own sentence.

    The marker fragment alone is too short ("same fit") — the target is
    named in its tail ("same fit as the p50 row", "与 P1/2 同一拟合").
    The sentence is the marker's surrounding text bounded by CJK/ASCII
    sentence punctuation and newlines.
    """
    start = max(
        (haystack.rfind(sep, 0, marker_start) + 1 for sep in _SENTENCE_SEPS),
        default=0,
    )
    ends = [i for sep in _SENTENCE_SEPS if (i := haystack.find(sep, marker_end)) != -1]
    end = min(ends) if ends else len(haystack)
    sentence = haystack[start:end]
    hits_p50 = _P50_HINT_RE.search(sentence) is not None
    hits_t50 = _T50_HINT_RE.search(sentence) is not None
    if hits_p50 and not hits_t50:
        return "p50"
    if hits_t50 and not hits_p50:
        return "t50"
    return "ambiguous"


_SENTENCE_SEPS = ("；", ";", "。", "！", "？", "\n")


def same_fit_marker_hits(engine: Engine) -> list[MarkerHit]:
    """Find slope-only rows whose prose carries a same-fit marker."""
    hits: list[MarkerHit] = []
    with engine.connect() as conn:
        for row in conn.execute(_SLOPE_ONLY_SQL).mappings():
            haystack = " ".join(
                (row["condition_key"] or "", row["extractor_note"] or "")
            )
            m = MARKER_RE.search(haystack)
            if m:
                hits.append(
                    MarkerHit(
                        maicdb_id=row["maicdb_id"],
                        channel_id=row["channel_id"],
                        publication_id=row["publication_id"],
                        condition_key=row["condition_key"] or "",
                        marker=m.group(0),
                        kind=_classify_marker(haystack, m.start(), m.end()),
                    )
                )
    return hits


def same_fit_candidates(engine: Engine) -> list[SameFitCandidate]:
    """Enumerate every (slope, threshold) candidate pair, evidence attached."""
    candidates: list[SameFitCandidate] = []
    with engine.connect() as conn:
        for hit in same_fit_marker_hits(engine):
            if hit.kind == "ambiguous":
                continue
            for sib in conn.execute(
                _SIBLING_SQL,
                {
                    "channel_id": hit.channel_id,
                    "publication_id": hit.publication_id,
                    "maicdb_id": hit.maicdb_id,
                },
            ).mappings():
                target = sib["p50_value"] if hit.kind == "p50" else sib["t50_value"]
                if target is None:
                    continue
                candidates.append(
                    SameFitCandidate(
                        slope_maicdb_id=hit.maicdb_id,
                        threshold_maicdb_id=sib["maicdb_id"],
                        kind=hit.kind,
                        marker=hit.marker,
                        channel_id=hit.channel_id,
                        publication_id=hit.publication_id,
                        token_overlap=None,
                    )
                )
    return candidates


def _tokens(condition_key: str) -> set[str]:
    return set(re.split(r"[^a-z0-9.]+", condition_key.lower())) - {""}


def narrow_by_condition_key(
    candidates: Iterable[SameFitCandidate],
    condition_key_of: dict[str, str],
) -> list[SameFitCandidate]:
    """Return the best sibling per slope row by condition-key token overlap.

    ``condition_key_of`` maps maicdb_id → condition_key for every row in
    the candidate set (both sides). Score = |token overlap| of the two
    lowercase condition keys; the highest-scoring sibling per slope row
    wins, ties are all kept, score 0 is dropped. Scores are written into
    ``token_overlap`` — a heuristic with a disclosed number, not truth.
    """
    best: dict[str, tuple[int, SameFitCandidate]] = {}
    for cand in candidates:
        slope_key = condition_key_of.get(cand.slope_maicdb_id, "")
        sib_key = condition_key_of.get(cand.threshold_maicdb_id, "")
        score = len(_tokens(slope_key) & _tokens(sib_key))
        if score <= 0:
            continue
        prev = best.get(cand.slope_maicdb_id)
        if prev is None or score > prev[0]:
            best[cand.slope_maicdb_id] = (score, _with_overlap(cand, score))
    return [pair for _, pair in best.values()]


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

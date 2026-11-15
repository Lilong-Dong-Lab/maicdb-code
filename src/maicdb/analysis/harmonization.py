"""The P1 harmonization deep module — one read of the frozen artifact
per :func:`harmonize` call.

This module is the single owner of value-row reads + conversions for
the analysis layer (spec §4's P1 list: units, coalesce(n, n_cells),
pActivity, ΔP50 values, same-fit row join). The P4 biophysics and P5
atlas tracks consume :func:`harmonize` and keep only their
aggregation/statistics — neither opens the artifact for a value row or
applies a conversion inline. (P2 mimic and P6 trends keep their own
reads by design — spec §4/§5: mimic is the per-record seam; trends
counts publications, not values.)

Authority chain: ``docs/analytics-pipeline-spec.md`` (scope) →
``docs/adr/0005-mimic-tri-state-hybrid.md`` (unit policy) → the leaf
modules (:mod:`~maicdb.analysis.units`, :mod:`~maicdb.analysis.replicates`,
:mod:`~maicdb.analysis.activity`, :mod:`~maicdb.analysis.joins`) →
this module. The leaf modules stay public (their arithmetic is pinned
by their own tests); this module composes them behind one interface.

Design rules inherited from spec §4: reads the frozen artifact only,
read-only; deterministic — same artifact, byte-identical outputs; the
as-reported pair is preserved beside every converted value (ADR-0005).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text as sql_text
from sqlalchemy.engine import Engine

from maicdb.analysis.activity import PActivity, p_activity
from maicdb.analysis.replicates import coalesce_replicates
from maicdb.analysis.units import pressure_to_mmhg

__all__ = [
    "ActivityRecord",
    "DeltaP50Record",
    "HarmonizedCorpus",
    "MarkerHit",
    "P50Record",
    "SameFitCandidate",
    "SlopeRecord",
    "TauRecord",
    "harmonize",
    "in_covered_range",
]

_P50_SQL = sql_text(
    "SELECT e.maicdb_id AS maicdb_id, e.p50_value AS p50_value,"
    " e.p50_unit AS p50_unit, e.n_cells AS n_cells, e.n AS n,"
    " e.stimulus_type AS stimulus_type, e.publication_id AS publication_id,"
    " e.condition_key AS condition_key, e.channel_id AS channel_id,"
    " c.gene_symbol AS gene_symbol, c.family AS family"
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

_BIOACTIVITY_SQL = sql_text(
    "SELECT b.maicdb_id AS maicdb_id, cp.name AS compound_name,"
    " c.gene_symbol AS gene_symbol, c.family AS family,"
    " b.activity_value AS activity_value, b.activity_units AS activity_units"
    " FROM bioactivity b"
    " JOIN compound cp ON b.compound_id = cp.id"
    " JOIN channel c ON b.channel_id = c.id"
    " ORDER BY b.maicdb_id"
)

_DP50_SQL = sql_text(
    "SELECT e.maicdb_id AS maicdb_id, e.channel_id AS channel_id,"
    " c.gene_symbol AS gene_symbol,"
    " c.family AS family, e.delta_p50_value AS delta_p50_value,"
    " e.delta_p50_unit AS delta_p50_unit, e.publication_id AS publication_id,"
    " e.variant_id AS variant_id, v.hgvs_protein AS hgvs_protein,"
    " v.position AS position, v.functional_effect AS functional_effect"
    " FROM biophysics_experiment e"
    " JOIN channel c ON e.channel_id = c.id"
    " LEFT JOIN variant v ON e.variant_id = v.id"
    " WHERE e.delta_p50_value IS NOT NULL"
    " ORDER BY e.maicdb_id"
)

_COVERED_SQL = sql_text(
    "SELECT s.id AS structure_id, s.pdb_id AS pdb_id,"
    " s.channel_id AS channel_id, s.residues_covered AS residues_covered"
    " FROM structure s WHERE s.residues_covered IS NOT NULL"
)

_SLOPE_SQL = sql_text(
    "SELECT maicdb_id, channel_id, publication_id, condition_key,"
    " extractor_note, slope,"
    " (p50_value IS NULL AND t50_value IS NULL AND x50_value IS NULL)"
    " AS slope_only"
    " FROM biophysics_experiment WHERE slope IS NOT NULL"
    " ORDER BY maicdb_id"
)

_SIBLING_SQL = sql_text(
    "SELECT maicdb_id, condition_key, p50_value, t50_value "
    "FROM biophysics_experiment WHERE channel_id = :channel_id "
    "AND publication_id = :publication_id AND maicdb_id != :maicdb_id"
)

# "same fit as the p50 row", "same group fit as T1/2 row",
# "same fitted gradient", "same Fig 5A fit as WT p50 row", "同一拟合".
MARKER_RE = re.compile(r"same(?:\s+\S+){0,3}?\s+fit|同一拟合", re.IGNORECASE)

# Marker text that names the target parameter. "P1/2" is how several
# condition_keys abbreviate the P50 midpoint; "T1/2" the T50 midpoint.
_P50_HINT_RE = re.compile(r"p50|p1/2", re.IGNORECASE)
_T50_HINT_RE = re.compile(r"t50|t1/2", re.IGNORECASE)

_SENTENCE_SEPS = ("；", ";", "。", "！", "？", "\n", ".")


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


def in_covered_range(position: int, residues_covered: str) -> bool:
    """True when ``position`` falls inside a coverage spec like
    ``"1-2547"`` or ``"1-200, 300-500"`` (ranges inclusive; bare
    numbers treated as single residues). Malformed segments are
    skipped — coverage text is curated free text."""
    for segment in residues_covered.split(","):
        part = segment.strip()
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-", 1)
            try:
                lo, hi = int(bounds[0]), int(bounds[1])
            except ValueError:
                continue
            if lo <= position <= hi:
                return True
        else:
            try:
                if int(part) == position:
                    return True
            except ValueError:
                continue
    return False


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
    # level and counts records — see consumers' cluster_key docs


@dataclass(frozen=True)
class TauRecord:
    """One tau-bearing record, column-native ms (no conversion —
    ADR-0005 unit policy: kinetics stay ms)."""

    maicdb_id: str
    publication_id: int
    gene_symbol: str
    family: str
    tau_act_ms: float | None
    tau_inact_ms: float | None
    tau_deact_ms: float | None


@dataclass(frozen=True)
class ActivityRecord:
    """One bioactivity row with its resolved pActivity.

    ``pa`` carries the as-reported pair (ADR-0005). A NULL unit reaches
    ``p_activity`` as None — basis ``missing_value`` — never coerced to
    "" (which would mislabel it ``unknown_unit``).
    """

    maicdb_id: str
    compound_name: str
    gene_symbol: str
    family: str
    activity_value: float  # as reported
    activity_units: str | None  # as reported (NULL preserved)
    pa: PActivity


@dataclass(frozen=True)
class DeltaP50Record:
    """One ΔP50 effect-size row (spec: no inferential statistics).

    Structural domains are resolved at read time: every structure
    whose covered range contains the variant position is listed.
    """

    maicdb_id: str
    gene_symbol: str
    family: str
    delta_p50: float  # as reported (all data-v1.0 rows are mmHg)
    unit: str  # as reported
    variant_linked: bool  # the row cites a variant (at data-v1.0 the
    # linked rows carry NULL hgvs_protein — linkage without notation)
    variant: str | None  # hgvs_protein (None on all data-v1.0 rows)
    functional_effect: str | None
    variant_position: int | None
    domains: tuple[str, ...]  # structures covering the variant position


@dataclass(frozen=True)
class SlopeRecord:
    """One slope-bearing row (``slope`` IS NOT NULL). ``slope_only``
    marks the discovery subset (every threshold column NULL) that
    same-fit marker scanning runs on."""

    maicdb_id: str
    channel_id: int
    publication_id: int
    condition_key: str
    extractor_note: str | None
    slope: float  # dimensionless (pressure-Boltzmann reading, spec §5.2)
    slope_only: bool


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


@dataclass(frozen=True)
class HarmonizedCorpus:
    """Every value-bearing row of the frozen artifact, harmonized.

    Built only by :func:`harmonize`; deterministic order per collection
    (``ORDER BY maicdb_id``), with one disclosed exception: ``same_fit``
    sorts by ``(slope_maicdb_id, threshold_maicdb_id)`` — the pairing
    order the ΔG demo and its census pin read.
    """

    p50: tuple[P50Record, ...]
    tau: tuple[TauRecord, ...]
    bioactivity: tuple[ActivityRecord, ...]
    delta_p50: tuple[DeltaP50Record, ...]
    slope_rows: tuple[SlopeRecord, ...]
    same_fit_hits: tuple[MarkerHit, ...]
    same_fit: tuple[SameFitCandidate, ...]


def harmonize(engine: Engine) -> HarmonizedCorpus:
    """Read the frozen artifact once and harmonize every value row."""
    p50: list[P50Record] = []
    tau: list[TauRecord] = []
    bioactivity: list[ActivityRecord] = []
    delta_p50: list[DeltaP50Record] = []
    covered: dict[int, list] = {}
    with engine.connect() as conn:
        for row in conn.execute(_P50_SQL).mappings():
            unit = row["p50_unit"] or ""
            converted = pressure_to_mmhg(float(row["p50_value"]), unit)
            rep = coalesce_replicates(row["n_cells"], row["n"])
            n_i = rep.value if rep.value is not None else 1
            p50.append(
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
        for row in conn.execute(_TAU_SQL).mappings():
            tau.append(
                TauRecord(
                    maicdb_id=str(row["maicdb_id"]),
                    publication_id=int(row["publication_id"]),
                    gene_symbol=str(row["gene_symbol"]),
                    family=str(row["family"]),
                    tau_act_ms=(
                        float(row["tau_act_ms"])
                        if row["tau_act_ms"] is not None
                        else None
                    ),
                    tau_inact_ms=(
                        float(row["tau_inact_ms"])
                        if row["tau_inact_ms"] is not None
                        else None
                    ),
                    tau_deact_ms=(
                        float(row["tau_deact_ms"])
                        if row["tau_deact_ms"] is not None
                        else None
                    ),
                )
            )
        for row in conn.execute(_BIOACTIVITY_SQL).mappings():
            value = float(row["activity_value"])
            units = row["activity_units"]
            bioactivity.append(
                ActivityRecord(
                    maicdb_id=str(row["maicdb_id"]),
                    compound_name=str(row["compound_name"]),
                    gene_symbol=str(row["gene_symbol"]),
                    family=str(row["family"]),
                    activity_value=value,
                    activity_units=units,
                    pa=p_activity(value, units),
                )
            )
        for row in conn.execute(_COVERED_SQL).mappings():
            covered.setdefault(int(row["channel_id"]), []).append(row)
        for row in conn.execute(_DP50_SQL).mappings():
            position = row["position"]
            domains: list[str] = []
            if position is not None:
                channel_id = row["channel_id"]
                for s in covered.get(int(channel_id) if channel_id is not None else -1, []):
                    if in_covered_range(int(position), s["residues_covered"] or ""):
                        domains.append(str(s["pdb_id"] or s["structure_id"]))
            delta_p50.append(
                DeltaP50Record(
                    maicdb_id=str(row["maicdb_id"]),
                    gene_symbol=str(row["gene_symbol"]),
                    family=str(row["family"]),
                    delta_p50=float(row["delta_p50_value"]),
                    unit=row["delta_p50_unit"] or "",
                    variant_linked=row["variant_id"] is not None,
                    variant=row["hgvs_protein"],
                    functional_effect=row["functional_effect"],
                    variant_position=position,
                    domains=tuple(domains),
                )
            )
        slope_rows: list[SlopeRecord] = []
        for row in conn.execute(_SLOPE_SQL).mappings():
            slope_rows.append(
                SlopeRecord(
                    maicdb_id=str(row["maicdb_id"]),
                    channel_id=int(row["channel_id"]),
                    publication_id=int(row["publication_id"]),
                    condition_key=row["condition_key"] or "",
                    extractor_note=row["extractor_note"],
                    slope=float(row["slope"]),
                    slope_only=bool(row["slope_only"]),
                )
            )
        # Same-fit discovery (spec §5.2 step 1): scan the slope-only
        # subset's prose for a same-fit marker; pair each classified hit
        # with sibling rows of the same channel + publication that hold
        # the marker's target parameter. Nothing is silently joined.
        hits: list[MarkerHit] = []
        candidates: list[SameFitCandidate] = []
        for r in slope_rows:
            if not r.slope_only:
                continue
            haystack = " ".join((r.condition_key or "", r.extractor_note or ""))
            m = MARKER_RE.search(haystack)
            if m:
                hits.append(
                    MarkerHit(
                        maicdb_id=r.maicdb_id,
                        channel_id=r.channel_id,
                        publication_id=r.publication_id,
                        condition_key=r.condition_key or "",
                        marker=m.group(0),
                        kind=_classify_marker(haystack, m.start(), m.end()),
                    )
                )
        for hit in hits:
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
        candidates.sort(key=lambda c: (c.slope_maicdb_id, c.threshold_maicdb_id))
    return HarmonizedCorpus(
        p50=tuple(p50),
        tau=tuple(tau),
        bioactivity=tuple(bioactivity),
        delta_p50=tuple(delta_p50),
        slope_rows=tuple(slope_rows),
        same_fit_hits=tuple(hits),
        same_fit=tuple(candidates),
    )

"""Replicate-count coalescing for the analysis layer (P1).

The published artifact carries replicate counts in two places:
``biophysics_experiment.n_cells`` (INTEGER, 0% populated at data-v1.0) and
the legacy text column ``n`` (53% populated — spec §3, census SQL there).
The legacy column is free text whose observed forms are clean integers
("12") and integer ranges ("5-9"); anything else is kept as
``source="n_unparsed"`` with the raw text preserved — never guessed
(vault extraction rule: "Do not guess").

Authority: ADR-0005 — the audit reads the harmonized coalesce of the two
columns; ``n_cells`` wins when present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Replicates", "coalesce_replicates", "parse_n"]

_INT_RE = re.compile(r"^(\d+)$")
_RANGE_RE = re.compile(r"^(\d+)\s*-\s*(\d+)$")


@dataclass(frozen=True)
class Replicates:
    """A harmonized replicate count; ``value`` for single integers,
    ``low``/``high`` for ranges, both None when absent or unparseable."""

    value: int | None
    low: int | None
    high: int | None
    source: str  # "n_cells" | "n_int" | "n_range" | "n_unparsed" | "none"
    raw: str | None  # the legacy ``n`` text when it was the source


def parse_n(text: str | None) -> Replicates:
    """Parse the legacy ``n`` text column into a :class:`Replicates`.

    Recognized forms: ``"12"`` (single) and ``"5-9"`` (range, ASCII hyphen,
    optional surrounding spaces). Everything else — empty, None, prose —
    yields ``source="n_unparsed"`` (raw kept) or ``source="none"``.
    """
    if text is None:
        return Replicates(None, None, None, "none", None)
    stripped = text.strip()
    if not stripped:
        return Replicates(None, None, None, "none", None)
    m = _INT_RE.match(stripped)
    if m:
        return Replicates(int(m.group(1)), None, None, "n_int", text)
    m = _RANGE_RE.match(stripped)
    if m:
        low, high = int(m.group(1)), int(m.group(2))
        return Replicates(None, low, high, "n_range", text)
    return Replicates(None, None, None, "n_unparsed", text)


def coalesce_replicates(n_cells: int | None, n_text: str | None) -> Replicates:
    """Harmonized replicate count: ``n_cells`` wins; the legacy ``n`` text
    is the fallback (parsed by :func:`parse_n`)."""
    if n_cells is not None:
        return Replicates(n_cells, None, None, "n_cells", None)
    return parse_n(n_text)

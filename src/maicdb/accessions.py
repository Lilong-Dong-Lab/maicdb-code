"""Stable accession (``maicdb_id``) generation for FAIR findability.

Every row in MAIC-DB carries a human-readable, stable accession of the form::

    MAIC:<PREFIX>:<NNNNN>

for example ``MAIC:CH:00001`` for the first channel, ``MAIC:BX:00042`` for the
42nd biophysics experiment. Accessions are intentionally separate from the
surrogate primary key so they remain citable even if rows are re-imported.

The accession is formatted deterministically from an entity prefix and an
integer. During bulk loading use :class:`AccessionGenerator`, which hands out
monotonically increasing numbers per entity type and is the single source of
truth to avoid collisions within a load.
"""

from __future__ import annotations

import threading
from enum import Enum

__all__ = [
    "AccessionPrefix",
    "ACCESSION_WIDTH",
    "format_accession",
    "AccessionGenerator",
]


class AccessionPrefix(str, Enum):
    """Two-letter prefix identifying the entity type in a ``maicdb_id``."""

    CHANNEL = "CH"
    STRUCTURE = "ST"
    BIOPHYSICS_EXPERIMENT = "BX"
    COMPOUND = "CP"
    BIOACTIVITY = "BA"
    VARIANT = "VR"
    UNMAPPED_MEASUREMENT = "UM"   # schema v0.2: adjudicated-kept gap archive rows


#: Zero-padding width of the numeric segment. 5 digits → 99,999 per entity,
#: ample for a curated research database; widen if ever exceeded.
ACCESSION_WIDTH = 5


def format_accession(prefix: AccessionPrefix | str, number: int) -> str:
    """Format a stable accession string.

    Parameters
    ----------
    prefix:
        Entity prefix (an :class:`AccessionPrefix` member or its string value).
    number:
        Positive integer sequence number (>= 1).

    Returns
    -------
    str
        e.g. ``"MAIC:CH:00001"``.
    """
    if isinstance(prefix, AccessionPrefix):
        prefix = prefix.value
    if not isinstance(number, int) or number < 1:
        raise ValueError(f"accession number must be a positive int, got {number!r}")
    return f"MAIC:{prefix}:{number:0{ACCESSION_WIDTH}d}"


class AccessionGenerator:
    """Thread-safe, monotonically-increasing accession issuer per entity type.

    Example
    -------
    >>> gen = AccessionGenerator()
    >>> gen.next(AccessionPrefix.CHANNEL)
    'MAIC:CH:00001'
    >>> gen.next(AccessionPrefix.CHANNEL)
    'MAIC:CH:00002'
    >>> gen.next(AccessionPrefix.COMPOUND)
    'MAIC:CP:00001'

    Counters can be seeded (e.g. from the max existing accession in the DB) via
    the ``start`` argument to avoid collisions when resuming an interrupted load.
    """

    def __init__(self, start: dict[AccessionPrefix, int] | None = None) -> None:
        # Per-prefix counters; default each to 0 so the first issue is number 1.
        self._counters: dict[AccessionPrefix, int] = {
            p: (start.get(p, 0) if start else 0) for p in AccessionPrefix
        }
        self._lock = threading.Lock()

    def next(self, prefix: AccessionPrefix) -> str:
        """Issue and return the next accession for *prefix*."""
        with self._lock:
            self._counters[prefix] += 1
            return format_accession(prefix, self._counters[prefix])

    def current(self, prefix: AccessionPrefix) -> int:
        """Return the most recently issued number for *prefix* (0 if none)."""
        return self._counters[prefix]

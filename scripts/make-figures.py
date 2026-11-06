"""Render the P7 figure set into dist/analysis/<data-tag>/figures/.

Spec §8's release-facing figure home (``dist/`` is gitignored; the SITE
render regenerates its own copies into each locale tree, so this script
exists for the release bundle / Zenodo staging path, not the site).

Usage:  PYTHONPATH=src uv run python scripts/make-figures.py

Deterministic: same artifact + same code → byte-identical PNGs (the
figure module strips Software/Date metadata; the byte-stability test
locks the rule).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from maicdb.analysis.figures import render_all
from maicdb.analysis.site_payloads import analysis_payloads
from maicdb.query import open_readonly


def main() -> int:
    engine = open_readonly(ROOT / "db" / "maicdb.sqlite")
    payloads = analysis_payloads(engine)
    engine.dispose()
    tag = payloads["audit"]["data_freeze_tag"]
    out = ROOT / "dist" / "analysis" / tag / "figures"
    for path in render_all(payloads, out):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

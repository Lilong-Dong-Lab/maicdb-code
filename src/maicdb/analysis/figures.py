"""Publication-grade figure set (P7, spec §8).

Five deterministic PNGs rendered from the analysis payloads (the SAME
serialized dicts ``site/_data/analysis/*.json`` carry — a figure and
its page table cannot disagree):

* ``compliance-by-year`` — mean MIMIC compliance per publication year
  (audit payload; era boundary marked, not fitted).
* ``p50-forest`` — pooled |P50| per (family, stimulus) cell with the
  confidence/prediction interval where identifiable (biophysics
  payload; descriptive cells show the pooled mean as an open marker).
* ``pubs-per-year`` — distinct publications per year (trends payload).
* ``parameter-adoption`` — records per (year, parameter) full grid
  (trends payload; sequential single-hue ramp).
* ``matrix-heatmap`` — compound × channel pActivity cells (atlas
  payload; three visual states: absent = white, unresolved = gray,
  value = the ramp — "no data" is never drawn as zero).

Determinism contract (the site's byte-stability rule extends here):
same payload + same code → byte-identical PNGs. Agg renderer, fixed
figure geometry, metadata stripped (``Software``/``Date`` set to None
so no timestamp enters the file). Colors follow the reference dataviz
palette: single-series forms wear one categorical hue; the two
heatmaps use one hue light→dark (sequential = magnitude); grids and
axes stay recessive; text wears text colors, never series color.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import matplotlib

matplotlib.use("Agg")  # headless, deterministic
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

if TYPE_CHECKING:
    from os import PathLike

__all__ = ["FIGURES", "render_all"]

#: Reference palette (dataviz skill instance) — the five roles the
#: figures use. Light-surface render (PNGs carry one fixed surface).
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#d9d8d4"
SERIES1 = "#2a78d6"
#: Sequential one-hue ramp (light→dark blue) for magnitude heatmaps.
RAMP = LinearSegmentedColormap.from_list(
    "seq_blue", ["#f3f6fb", "#2a78d6", "#123c74"]
)
#: Unresolved-value cells (measurements exist, value does not resolve).
UNRESOLVED = "#d9d8d4"

_RC = {
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.size": 9,
    "text.color": TEXT,
    "axes.edgecolor": GRID,
    "axes.labelcolor": TEXT2,
    "axes.titlecolor": TEXT,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "axes.axisbelow": True,
    "xtick.color": TEXT2,
    "ytick.color": TEXT2,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "legend.frameon": False,
}


def _fig(w: float, h: float) -> tuple:
    plt.rcdefaults()
    plt.rcParams.update(_RC)
    return plt.subplots(figsize=(w, h), dpi=160)


def _save(fig, ax, out: Path, title: str) -> Path:
    ax.set_title(title, loc="left", fontsize=10.5, pad=10)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    # metadata=None-values: no Software/Date tEXt chunk → byte-stable
    fig.savefig(
        out, format="png", metadata={"Software": None, "Date": None}
    )
    plt.close(fig)
    return out


def _compliance_by_year(audit: dict, out: Path) -> Path:
    fig, ax = _fig(8.0, 4.2)
    years = [r["year"] for r in audit["compliance_by_year"]["years"]]
    means = [r["mean"] for r in audit["compliance_by_year"]["years"]]
    ks = [r["k"] for r in audit["compliance_by_year"]["years"]]
    ax.axvline(
        audit["compliance_by_year"]["piezo_year"],
        color=GRID, linestyle="--", linewidth=1.0, zorder=0,
    )
    ax.plot(years, means, color=SERIES1, linewidth=2.0, zorder=2)
    ax.scatter(years, means, s=22, color=SERIES1, zorder=3)
    # selective direct labels: the era endpoints carry their k, the
    # reader's anchor points; no number on every marker
    for i in (0, len(years) - 1):
        ax.annotate(
            f"k={ks[i]}", (years[i], means[i]),
            textcoords="offset points", xytext=(0, 7),
            ha="center", fontsize=8, color=TEXT2,
        )
    ax.set_ylim(0, max(1.0, max(means) * 1.15))
    ax.set_xlabel("")
    ax.set_ylabel("mean compliance")
    return _save(fig, ax, out, "Mean MIMIC compliance by publication year")


def _p50_forest(bio: dict, out: Path) -> Path:
    cells = bio["threshold_meta"]
    cells = sorted(
        cells, key=lambda c: (c["family"], c["stimulus_type"] or "")
    )
    labels = [
        f"{c['family']} · {(c['stimulus_type'] or '?').lower()}"
        for c in cells
    ]
    fig, ax = _fig(8.0, 4.8)
    ys = range(len(cells))
    for y, c in zip(ys, cells):
        if c["ci_mmhg"] is not None:
            ax.plot(
                [c["ci_mmhg"][0], c["ci_mmhg"][1]], [y, y],
                color=SERIES1, linewidth=2.0, zorder=2,
            )
            ax.scatter(
                [c["pooled_mmhg"]], [y], s=36, color=SERIES1, zorder=3,
            )
        else:
            # descriptive cell: pooled mean only, open marker — no
            # interval is drawn because none is identifiable
            ax.scatter(
                [c["pooled_mmhg"]], [y], s=36, facecolors="none",
                edgecolors=SERIES1, linewidths=1.6, zorder=3,
            )
    ax.set_yticks(list(ys), labels, fontsize=8.5)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("pooled |P50| (mmHg) — bars: 95% CI (identifiable cells)")
    ax.set_xlim(0, None)
    return _save(
        fig, ax, out,
        "Pooled activation thresholds per (family, stimulus)",
    )


def _pubs_per_year(trends: dict, out: Path) -> Path:
    rows = trends["pubs_per_year_total"]
    years = [r["year"] for r in rows]
    ks = [r["k"] for r in rows]
    fig, ax = _fig(8.0, 4.2)
    ax.bar(years, ks, width=0.72, color=SERIES1, zorder=2)
    ax.set_ylabel("distinct publications")
    ax.set_xticks(
        [years[0], years[len(years) // 2], years[-1]],
        [str(years[0]), str(years[len(years) // 2]), str(years[-1])],
    )
    return _save(fig, ax, out, "Publications per year")


def _parameter_adoption(trends: dict, out: Path) -> Path:
    rows = trends["parameter_adoption"]
    years = sorted({r["year"] for r in rows})
    labels = list(dict.fromkeys(r["parameter"] for r in rows))
    grid = [[None] * len(years) for _ in labels]
    for r in rows:
        grid[labels.index(r["parameter"])][years.index(r["year"])] = r["k"]
    max_k = max(v for row in grid for v in row if v is not None)
    fig, ax = _fig(9.0, 5.2)
    im = ax.imshow(
        [[(v if v is not None else 0) for v in row] for row in grid],
        aspect="auto", cmap=RAMP, vmin=0, vmax=max_k, interpolation="nearest",
    )
    ax.set_yticks(range(len(labels)), labels, fontsize=8)
    ax.set_xticks(
        range(0, len(years), max(1, len(years) // 12)),
        [str(years[i]) for i in range(0, len(years), max(1, len(years) // 12))],
    )
    ax.grid(visible=False)
    cb = fig.colorbar(im, ax=ax, shrink=0.85, pad=0.02)
    cb.set_label("records with the parameter that year")
    cb.outline.set_visible(False)
    return _save(
        fig, ax, out,
        "Parameter adoption by year (records carrying a value)",
    )


def _matrix_heatmap(atlas: dict, out: Path) -> Path:
    compounds = list(dict.fromkeys(c["compound_name"] for c in atlas["matrix"]))
    genes = sorted({c["gene_symbol"] for c in atlas["matrix"]})
    grid = [[None] * len(genes) for _ in compounds]
    unresolved = [[False] * len(genes) for _ in compounds]
    for c in atlas["matrix"]:
        ci, gi = compounds.index(c["compound_name"]), genes.index(c["gene_symbol"])
        grid[ci][gi] = c["pactivity"]
        if c["pactivity"] is None:
            unresolved[ci][gi] = True  # cell exists, value does not resolve
    fig, ax = _fig(7.2, 9.6)
    # base layer: unresolved cells light gray; ABSENT cells stay
    # surface-white — "no data" is never drawn as zero
    base = [[0.12 if u else 0.0 for u in row] for row in unresolved]
    ax.imshow(
        base, aspect="auto", cmap="Greys", vmin=0, vmax=1,
        interpolation="nearest",
    )
    vals = [v for row in grid for v in row if v is not None]
    if vals:
        masked = [
            [float("nan") if v is None else v for v in row] for row in grid
        ]
        im = ax.imshow(
            masked, aspect="auto", cmap=RAMP,
            vmin=min(vals), vmax=max(vals), interpolation="nearest",
        )
        cb = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
        cb.set_label("pActivity (−log10 M)")
        cb.outline.set_visible(False)
    ax.set_yticks(range(len(compounds)), compounds, fontsize=6.5)
    ax.set_xticks(range(len(genes)), genes, fontsize=7, rotation=30, ha="right")
    ax.grid(visible=False)
    fig.text(
        0.01, 0.005,
        "white: no measurements · gray: measurements without a resolvable "
        "value · blue: mean pActivity",
        fontsize=7, color=TEXT2,
    )
    return _save(
        fig, ax, out,
        "Compound × channel activity matrix",
    )


#: name → renderer(payload dict, output path); ``render_all`` feeds the
#: right payload to each.
FIGURES: dict[str, Callable[[dict, Path], Path]] = {
    "compliance-by-year": lambda p, out: _compliance_by_year(p["audit"], out),
    "p50-forest": lambda p, out: _p50_forest(p["biophysics"], out),
    "pubs-per-year": lambda p, out: _pubs_per_year(p["trends"], out),
    "parameter-adoption": lambda p, out: _parameter_adoption(p["trends"], out),
    "matrix-heatmap": lambda p, out: _matrix_heatmap(p["atlas"], out),
}


def render_all(payloads: dict[str, dict], out_dir: PathLike) -> list[Path]:
    """Render the whole set into *out_dir*; returns the written paths.

    Payload keys are the four track names (``analysis_payloads``). The
    loop is registry-driven — adding a figure is one entry, no call-site
    edit.
    """
    out = Path(out_dir)
    return [fn(payloads, out / f"{name}.png") for name, fn in FIGURES.items()]

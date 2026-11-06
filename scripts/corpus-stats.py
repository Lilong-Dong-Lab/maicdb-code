#!/usr/bin/env python3
"""Corpus statistics for MAIC-DB (read-only).

Reads ``db/maicdb.sqlite`` through SQLite's read-only URI mode and prints a
deterministic Markdown report in eleven sections: corpus scale, publication
bibliometrics (year, journal, rows), channels, the per-channel parameter
matrix, unit spellings, confidence (corpus-wide and by family), the
evidence-location taxonomy, environment reporting, the bioactivity block,
MIMIC-field coverage and the condition-key dialects.

The numbers are derived, never transcribed: every section is a SQL query in
this file. Ordering is fixed (sorted keys, no clock) so two runs against the
same artifact are byte-identical — the same determinism contract the loader
and the site build hold.

Journal names are normalised through JOURNAL_ALIASES; raw variants that map
to one canonical name are reported as a data-quality list (the vault owns the
canonical spelling).

Usage:
    uv run scripts/corpus-stats.py [--db db/maicdb.sqlite] [--json OUT.json]

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

#: Abbreviated / variant journal names → one canonical spelling. Keys are
#: lowercased, punctuation-stripped, leading "the " removed. Values are the
#: spelling the report prints (Title Case, project convention).
JOURNAL_ALIASES: dict[str, str] = {
    "j biol chem": "Journal of Biological Chemistry",
    "journal of biological chemistry": "Journal of Biological Chemistry",
    "pnas": "Proceedings of the National Academy of Sciences",
    "proc natl acad sci usa": "Proceedings of the National Academy of Sciences",
    "proceedings of the national academy of sciences": (
        "Proceedings of the National Academy of Sciences"
    ),
    "proceedings of the national academy of sciences usa": (
        "Proceedings of the National Academy of Sciences"
    ),
    "proc natl acad sci": "Proceedings of the National Academy of Sciences",
    "proc natl acad sci u s a": "Proceedings of the National Academy of Sciences",
    "nat commun": "Nature Communications",
    "nature communications": "Nature Communications",
    "elife": "eLife",
    "journal of general physiology": "The Journal of General Physiology",
    "j gen physiol": "The Journal of General Physiology",
    "biophys j": "Biophysical Journal",
    "biophysical journal": "Biophysical Journal",
    "embo j": "The EMBO Journal",
    "embo journal": "The EMBO Journal",
    "nat struct mol biol": "Nature Structural & Molecular Biology",
    "nat neurosci": "Nature Neuroscience",
    "j neurosci": "The Journal of Neuroscience",
    "journal of neuroscience": "The Journal of Neuroscience",
    "plos one": "PLOS ONE",
    "sci rep": "Scientific Reports",
    "scientific reports": "Scientific Reports",
}

#: Evidence-location buckets, matched against the start of the lowercased
#: value in this order (Results first: many rows read "Results, ... Fig. 3").
_LOCATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("results and discussion", re.compile(r"^results and discussion")),
    ("results", re.compile(r"^results")),
    ("figure legend", re.compile(r"^(fig(ure)?|supplementary fig)")),
    ("table", re.compile(r"^(supp(lementary)? )?table")),
    ("abstract", re.compile(r"^abstract")),
    ("methods", re.compile(r"^(methods?|materials)")),
    ("discussion", re.compile(r"^discussion")),
    ("other", re.compile(r".*")),
)

#: The MIMIC-design columns, by README category (stimulus / recording /
#: cell context / environment / analysis). Coverage of each is printed as a
#: percentage of the 948 biophysics rows — the baseline the MIMIC draft
#: (docs/mimic/) will be written against.
MIMIC_COLUMNS: dict[str, tuple[str, ...]] = {
    "stimulus": (
        "stimulus_type",
        "stimulus_waveform",
        "stimulus_velocity",
        "stimulus_duration_ms",
        "probe_geometry",
        "probe_diameter_um",
    ),
    "recording": (
        "recording_mode",
        "sampling_rate_khz",
        "filter_khz",
        "holding_potential_mv",
        "analysis_method",
    ),
    "cell_context": ("expression_system", "cell_type"),
    "environment": ("temperature_c", "ph", "bath_solution", "pipette_solution"),
    "analysis": ("n", "n_cells"),
    "provenance": (
        "measurement_id",
        "evidence_quote",
        "evidence_location",
        "confidence",
        "condition_key",
    ),
}


def _norm_journal(name: str | None) -> tuple[str | None, str | None]:
    """(canonical, raw) for one journal string."""
    if not name:
        return None, None
    raw = name.strip()
    key = re.sub(r"[^a-z0-9 ]", "", raw.lower()).strip()
    if key.startswith("the "):
        key = key[4:]
    return JOURNAL_ALIASES.get(key, raw), raw


def _bucket_location(value: str | None) -> str:
    if not value:
        return "(null)"
    text = value.strip().lower()
    for label, pattern in _LOCATION_PATTERNS:
        if pattern.match(text):
            return label
    return "other"


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    values = sorted(values)
    mid = len(values) // 2
    if len(values) % 2:
        return round(values[mid], 2)
    return round((values[mid - 1] + values[mid]) / 2, 2)


def _q(cur: sqlite3.Cursor, sql: str) -> list[tuple]:
    return cur.execute(sql).fetchall()


def collect(db_path: Path) -> dict:
    """Every reported number, as plain JSON-able data."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = con.cursor()
    stats: dict = {}

    counts = {
        table: _q(cur, f"select count(*) from {table}")[0][0]
        for table in (
            "channel",
            "publication",
            "biophysics_experiment",
            "bioactivity",
            "unmapped_measurement",
            "compound",
            "variant",
            "external_reference",
        )
    }
    stats["counts"] = counts

    # --- publications -----------------------------------------------------
    years = _q(cur, "select year, count(*) from publication group by 1 order by 1")
    stats["publications_by_year"] = [[int(y) if y else None, n] for y, n in years]
    stats["year_range"] = _q(cur, "select min(year), max(year) from publication")[0]

    raw_journals = Counter()
    canonical = Counter()
    variants: dict[str, set[str]] = defaultdict(set)
    for (journal,) in _q(cur, "select journal from publication"):
        canon, raw = _norm_journal(journal)
        if raw is None:
            raw_journals["(null)"] += 1
            canonical["(null)"] += 1
            continue
        raw_journals[raw] += 1
        canonical[canon] += 1
        variants[canon].add(raw)
    stats["journals_raw_distinct"] = len(raw_journals)
    stats["journals_canonical_distinct"] = len(canonical)
    stats["top_journals"] = [
        [name, n] for name, n in sorted(canonical.items(), key=lambda kv: (-kv[1], kv[0]))[:15]
    ]
    stats["journal_variant_groups"] = [
        [canon, sorted(vs)]
        for canon, vs in sorted(variants.items())
        if len(vs) > 1
    ]

    # rows per publication (biophysics + bioactivity); scalar subqueries,
    # not a join — a publication with both kinds would be over-counted by a
    # cross product
    per_pub = _q(
        cur,
        """
        select p.id,
               (select count(*) from biophysics_experiment e where e.publication_id = p.id)
             + (select count(*) from bioactivity b where b.publication_id = p.id)
          from publication p
        """,
    )
    row_counts = [n for _, n in per_pub]
    stats["rows_per_publication"] = {
        "publications": len(row_counts),
        "with_zero_rows": sum(1 for n in row_counts if n == 0),
        "total_rows": sum(row_counts),
        "max": max(row_counts) if row_counts else 0,
        "median": _median([float(n) for n in row_counts]),
    }

    # --- channels ---------------------------------------------------------
    channels = _q(
        cur,
        """
        select c.gene_symbol, c.family,
               (select count(*) from biophysics_experiment e where e.channel_id = c.id),
               (select count(*) from bioactivity b where b.channel_id = c.id),
               (select count(distinct e.publication_id)
                  from biophysics_experiment e where e.channel_id = c.id)
          from channel c
         order by 3 desc, 1
        """,
    )
    stats["channels"] = [
        {
            "gene": g,
            "family": fam,
            "biophysics_rows": n,
            "bioactivity_rows": b,
            "publications": pubs,
        }
        for g, fam, n, b, pubs in channels
    ]

    # --- parameter coverage matrix ---------------------------------------
    params = [
        "p50", "t50", "x50", "slope", "tau_act", "tau_inact", "tau_deact",
        "conductance", "reversal_potential", "delta_p50", "ion_selectivity_ratio",
        "ca_permeability", "threshold_fold_shift", "macroscopic_rise_time",
        "thermal_threshold", "osmotic_threshold",
    ]
    columns = {
        "p50": "p50_value", "t50": "t50_value", "x50": "x50_value",
        "slope": "slope", "tau_act": "tau_act_ms", "tau_inact": "tau_inact_ms",
        "tau_deact": "tau_deact_ms", "conductance": "conductance_ps",
        "reversal_potential": "reversal_potential_mv", "delta_p50": "delta_p50_value",
        "ion_selectivity_ratio": "ion_selectivity_ratio",
        "ca_permeability": "ca_permeability",
        "threshold_fold_shift": "threshold_fold_shift_value",
        "macroscopic_rise_time": "macroscopic_rise_time_ms",
        "thermal_threshold": "thermal_threshold_c",
        "osmotic_threshold": "osmotic_threshold_value",
    }
    matrix: dict[str, dict[str, int]] = {}
    for gene, in _q(cur, "select gene_symbol from channel order by gene_symbol"):
        matrix[gene] = {}
        for p in params:
            col = columns[p]
            n = cur.execute(
                f"select count(*) from biophysics_experiment e join channel c "
                f"on e.channel_id = c.id where c.gene_symbol = ? and e.{col} is not null",
                (gene,),
            ).fetchone()[0]
            matrix[gene][p] = n
    stats["parameter_matrix"] = matrix
    stats["parameters"] = params

    # --- units ------------------------------------------------------------
    units: dict[str, list[list[str | int]]] = {}
    for label, col in (
        ("p50", "p50_unit"),
        ("t50", "t50_unit"),
        ("x50", "x50_unit"),
        ("osmotic_threshold", "osmotic_threshold_unit"),
        ("delta_p50", "delta_p50_unit"),
        ("threshold_fold_shift", "threshold_fold_shift_unit"),
    ):
        rows = _q(
            cur,
            f"select {col}, count(*) from biophysics_experiment "
            f"where {col} is not null group by 1 order by 2 desc, 1",
        )
        units[label] = [[u, n] for u, n in rows]
    stats["units"] = units

    # --- confidence -------------------------------------------------------
    stats["confidence"] = [
        [c, n]
        for c, n in _q(
            cur,
            "select confidence, count(*) from biophysics_experiment "
            "group by 1 order by 2 desc, 1",
        )
    ]
    stats["confidence_by_family"] = [
        [fam, conf, n]
        for fam, conf, n in _q(
            cur,
            """
            select c.family, e.confidence, count(*)
              from biophysics_experiment e join channel c on e.channel_id = c.id
             group by 1, 2 order by 1, 2
            """,
        )
    ]

    # --- evidence locations ----------------------------------------------
    loc = Counter()
    for table in ("biophysics_experiment", "bioactivity"):
        for (value,) in _q(cur, f"select evidence_location from {table}"):
            loc[_bucket_location(value)] += 1
    stats["evidence_locations"] = [
        [k, n] for k, n in sorted(loc.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    # --- environment ------------------------------------------------------
    env = {}
    for label, col in (("temperature_c", "temperature_c"), ("ph", "ph")):
        vals = [
            float(v)
            for (v,) in _q(
                cur, f"select {col} from biophysics_experiment where {col} is not null"
            )
        ]
        env[label] = {
            "rows": len(vals),
            "min": min(vals) if vals else None,
            "median": _median(vals),
            "max": max(vals) if vals else None,
        }
    stats["environment"] = env

    # --- bioactivity ------------------------------------------------------
    stats["bioactivity"] = {
        "rows": counts["bioactivity"],
        "compounds": _q(cur, "select count(distinct compound_id) from bioactivity")[0][0],
        "channels": _q(cur, "select count(distinct channel_id) from bioactivity")[0][0],
        "activity_types": [
            [t, n]
            for t, n in _q(
                cur,
                "select activity_type, count(*) from bioactivity "
                "group by 1 order by 2 desc, 1",
            )
        ],
    }

    # --- MIMIC coverage snapshot -----------------------------------------
    mimic: dict[str, list[list[str | int | float]]] = {}
    for category, cols in MIMIC_COLUMNS.items():
        rows = []
        for col in cols:
            n = _q(cur, f"select count({col}) from biophysics_experiment")[0][0]
            rows.append([col, n, round(100.0 * n / counts["biophysics_experiment"], 1)])
        mimic[category] = rows
    stats["mimic_coverage"] = mimic

    # --- condition keys ---------------------------------------------------
    keys = [k for (k,) in _q(cur, "select condition_key from biophysics_experiment")]
    stats["condition_keys"] = {
        "rows": len(keys),
        "unique": len(set(keys)),
        "underscore_style": sum(1 for k in keys if k and "_" in k and " " not in k),
        "prose_style": sum(1 for k in keys if k and " " in k),
    }

    con.close()
    return stats


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #
def _table(headers: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |"]
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return out


def render_markdown(stats: dict, db_label: str) -> str:
    total = stats["counts"]["biophysics_experiment"]
    lines: list[str] = []
    add = lines.append

    add("# MAIC-DB corpus baseline")
    add("")
    add(f"Derived by `scripts/corpus-stats.py` from `{db_label}` (read-only).")
    add("Every number is a query result; no value is transcribed by hand.")
    add("")

    add("## 1. Corpus scale")
    add("")
    add(
        "\n".join(
            _table(
                ["Table", "Rows"],
                [[k, v] for k, v in sorted(stats["counts"].items())],
            )
        )
    )
    add("")

    add("## 2. Publication bibliometrics")
    add("")
    lo, hi = stats["year_range"]
    add(f"- Year range: **{lo}–{hi}**")
    add(f"- Distinct journal strings (raw): **{stats['journals_raw_distinct']}**")
    add(f"- Distinct journals after normalisation: **{stats['journals_canonical_distinct']}**")
    rp = stats["rows_per_publication"]
    add(
        f"- Rows per publication: total {rp['total_rows']} across "
        f"{rp['publications']} papers (median {rp['median']}, max {rp['max']}, "
        f"{rp['with_zero_rows']} with no rows)"
    )
    add("")
    add("### Publications per year")
    add("")
    add("\n".join(_table(["Year", "Publications"], stats["publications_by_year"])))
    add("")
    add("### Top journals (normalised)")
    add("")
    add("\n".join(_table(["Journal", "Publications"], stats["top_journals"])))
    add("")
    if stats["journal_variant_groups"]:
        add("### Journal spelling variants (data-quality list)")
        add("")
        for canon, variants in stats["journal_variant_groups"]:
            add(f"- **{canon}** ← " + ", ".join(f"`{v}`" for v in variants))
        add("")

    add("## 3. Channels")
    add("")
    add(
        "\n".join(
            _table(
                ["Channel", "Family", "Biophysics rows", "Bioactivity rows", "Publications"],
                [
                    [c["gene"], c["family"], c["biophysics_rows"],
                     c["bioactivity_rows"], c["publications"]]
                    for c in stats["channels"]
                ],
            )
        )
    )
    add("")

    add("## 4. Parameter coverage (rows with a value, per channel)")
    add("")
    params = stats["parameters"]
    rows = []
    for gene, per in stats["parameter_matrix"].items():
        rows.append([gene] + [per[p] for p in params])
    add("\n".join(_table(["Channel"] + params, rows)))
    add("")
    totals = [
        [p, sum(per[p] for per in stats["parameter_matrix"].values())]
        for p in params
    ]
    add("\n".join(_table(["Parameter", "Rows"], totals)))
    add("")

    add("## 5. Unit spellings per parameter")
    add("")
    for param, values in stats["units"].items():
        add(f"- **{param}**: " + ", ".join(f"`{u}` ×{n}" for u, n in values))
    add("")

    add("## 6. Confidence")
    add("")
    add("\n".join(_table(["Confidence", "Rows"], stats["confidence"])))
    add("")
    add("### Confidence by family")
    add("")
    add(
        "\n".join(
            _table(
                ["Family", "Confidence", "Rows"],
                stats["confidence_by_family"],
            )
        )
    )
    add("")

    add("## 7. Evidence-location taxonomy")
    add("")
    add("\n".join(_table(["Bucket", "Rows"], stats["evidence_locations"])))
    add("")

    add("## 8. Environment reporting")
    add("")
    add(
        "\n".join(
            _table(
                ["Field", "Rows", "Min", "Median", "Max"],
                [
                    [k, v["rows"], v["min"], v["median"], v["max"]]
                    for k, v in sorted(stats["environment"].items())
                ],
            )
        )
    )
    add("")

    add("## 9. Bioactivity block")
    add("")
    ba = stats["bioactivity"]
    add(f"- Rows: **{ba['rows']}**, compounds: **{ba['compounds']}**, channels: **{ba['channels']}**")
    add("- Activity types: " + ", ".join(f"`{t}` ×{n}" for t, n in ba["activity_types"]))
    add("")

    add("## 10. MIMIC field coverage snapshot")
    add("")
    for category, cols in stats["mimic_coverage"].items():
        add(f"### {category}")
        add("")
        add(
            "\n".join(
                _table(
                    ["Field", "Rows", "% of biophysics rows"],
                    [[c, n, f"{pct}%"] for c, n, pct in cols],
                )
            )
        )
        add("")

    ck = stats["condition_keys"]
    add("## 11. Condition keys")
    add("")
    add(f"- Rows: **{ck['rows']}**, unique: **{ck['unique']}**")
    add(
        f"- Structured (underscore, no spaces): **{ck['underscore_style']}**; "
        f"prose-style (contains spaces): **{ck['prose_style']}**"
    )
    add("")
    add(f"Corpus size used for every percentage above: {total} biophysics rows.")
    add("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="db/maicdb.sqlite")
    parser.add_argument("--json", default=None, help="also write the raw stats JSON here")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 2
    stats = collect(db_path)
    if args.json:
        Path(args.json).write_text(
            json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    sys.stdout.write(render_markdown(stats, str(db_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

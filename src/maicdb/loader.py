"""Loader: map the vault's frozen curation corpus onto the formal schema.

Implements ``docs/loader-mapping.md`` (spec v0.2, all decisions DECIDED
2026-09-01/02; re-targeted to the vault ``data-v1.1`` freeze 2026-11-08,
then to ``data-v1.2`` 2026-11-08 — a zero-row retarget: identical 1125-row
corpus, delta = additive piezo1/piezo2 corroboration artifacts only):
produces ``maicdb.sqlite`` + a byte-stable ``maicdb.sql`` dump + a load
manifest with conservation asserts.

Ports, verbatim where possible, the staging loader's proven transforms
(vault ``tools/db-load/build_staging_db.py``): the 105 pre-authorized unit
conversions, the three-way row routing (960 biophysics / 137 bioactivity /
28 unmapped, incl. the 131 gap-adjudicated migrations), and the
modulator-role dedup with majority-frequency resolution.

Determinism: every row's ``created_at`` is pinned to :data:`FREEZE_EPOCH`
(the data-freeze date, not wall-clock) and insert order follows sorted keys,
so the SQL dump is byte-stable for a given vault state. The ``server_default``
timestamps remain for interactive/ORM use; the loader overrides them.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from maicdb.accessions import AccessionGenerator, AccessionPrefix
from maicdb.enums import (
    ActivityType,
    CompoundType,
    EntityType,
    Family,
    IndentationUnit,
    PressureUnit,
    SourceDb,
    StructureSource,
    TensionUnit,
)
from maicdb.models import (
    Bioactivity,
    BiophysicsExperiment,
    Channel,
    Compound,
    DbMeta,
    ExternalReference,
    Publication,
    Structure,
    UnmappedMeasurement,
    Variant,
)
from maicdb.database import make_engine, create_all

__all__ = ["load_vault", "main"]

#: The data-freeze epoch pinned into every row's created_at for determinism.
FREEZE_EPOCH = datetime(2026, 11, 8, 0, 0, 0)
FREEZE_DATE = date(2026, 11, 8)
FREEZE_TAG = "data-v1.2"
SCHEMA_VERSION = "0.2.0"

LAYERS = ["piezo1", "piezo2", "trpv4", "asic", "mscs", "mscl", "osca",
          "tmc", "tresk", "traak", "trek-1", "trek-2"]

LAYER_TO_CONFIG = {layer: layer.replace("-", "") for layer in LAYERS}

# ---- Canonical channel identity per layer (vault cross_references JSON where
# ---- available; configs otherwise). organism/taxid: the curated canonical
# ---- species per layer (human for mammalian layers, E. coli for mscl/mscs).
CHANNEL_IDENTITY: dict[str, dict] = {
    "piezo1": {"organism": "Homo sapiens", "taxid": 9606},
    "piezo2": {"organism": "Homo sapiens", "taxid": 9606},
    "trpv4": {"organism": "Homo sapiens", "taxid": 9606},
    "asic": {"organism": "Homo sapiens", "taxid": 9606},
    "mscs": {"organism": "Escherichia coli", "taxid": 562},
    "mscl": {"organism": "Escherichia coli", "taxid": 562},
    "osca": {"organism": "Arabidopsis thaliana", "taxid": 3702},
    "tmc": {"organism": "Homo sapiens", "taxid": 9606},
    "tresk": {"organism": "Homo sapiens", "taxid": 9606},
    "traak": {"organism": "Homo sapiens", "taxid": 9606},
    "trek-1": {"organism": "Homo sapiens", "taxid": 9606},
    "trek-2": {"organism": "Homo sapiens", "taxid": 9606},
}

# ---- config family string → Family enum (extraction granularity groups
# ---- MscL+MscS and expands DEG/ENaC / TRPV to the formal family names).
FAMILY_MAP = {
    "piezo": Family.PIEZO,
    "TRPV": Family.TRP,
    "K2P": Family.K2P,
    "OSCA/TMEM63": Family.OSCA_TMEM63,
    "MscL": Family.MSCL_MSCS,
    "MscS": Family.MSCL_MSCS,
    "TMC": Family.TMC,
    "DEG/ENaC": Family.DEG_ENaC_ASIC,
}

# Activation mechanism per family (vault master-summary attribution; the
# spec §3.2 config table).
ACTIVATION_MECHANISM = {
    "PIEZO": "Force-from-Lipids",
    "TRP": "Force-from-Lipids",
    "K2P": "Force-from-Lipids",
    "OSCA/TMEM63": "Force-from-Lipids",
    "MscL/MscS": "Force-from-Lipids",
    "DEG/ENaC/ASIC": "Force-from-Lipids",
    "TMC": "Force-from-Filament",
}

# ---- Pre-authorized unit conversions (vault staging loader, verbatim port).
# ---- Hook: "REPORTED UNIT IS <UNIT>" anywhere in extractor_note (mid-note
# ---- hooks legal — asic as-printed prefixes; F-042 lesson: no start anchor).
PREAUTHORIZED_CONVERSIONS = {
    "NANOSIEMENS": (1000.0, "nS→pS"),
    "S": (1000.0, "s→ms"),
    "SECONDS": (1000.0, "s→ms"),
    "MINUTES": (60000.0, "min→ms"),
    "MIN": (60000.0, "min→ms"),
    "MICROSECONDS": (0.001, "µs→ms"),
    "MILLIMOLAR": (1e6, "mM→nM"),
}
_REPORTED_UNIT_RE = re.compile(r"REPORTED UNIT IS ([A-Z]+)")

# ---- modulator_role → CompoundType (formal vocabulary; antagonist maps to
# ---- the direct enum member ANTAGONIST — exact staging parity, no deviation).
ROLE_TO_COMPOUND_TYPE = {
    "agonist": CompoundType.ACTIVATOR,
    "antagonist": CompoundType.ANTAGONIST,
    "blocker": CompoundType.INHIBITOR_BLOCKER,
    "potentiator": CompoundType.POTENTIATOR,
}
MODULATOR_ROLE_ENUM = {"agonist", "antagonist", "blocker", "potentiator",
                       "inhibitor", "activator", "potentiator"}

# ---- Normal routing: parameter_kind → (card value column, unit column).
KIND_TO_CARD = {
    "conductance": ("conductance_ps", None),
    "reversal_potential": ("reversal_potential_mv", None),
    "p50": ("p50_value", "p50_unit"),
    "t50": ("t50_value", "t50_unit"),
    "x50": ("x50_value", "x50_unit"),
    "tau_act": ("tau_act_ms", None),
    "tau_inact": ("tau_inact_ms", None),
    "tau_deact": ("tau_deact_ms", None),
    "hill_slope": ("slope", "slope_unit"),
    "delta_p50": ("delta_p50_value", "delta_p50_unit"),
    "iv_relation": ("iv_relation", None),  # value is the enum NAME string
}
UNIT_ENUMS = {
    "p50_unit": PressureUnit, "t50_unit": TensionUnit, "x50_unit": IndentationUnit,
    "delta_p50_unit": PressureUnit,
}

# ---- Gap-adjudicated migrations (vault staging GAP_MIGRATIONS, formal column
# ---- names; the 131 corpus rows the curation phase adjudicated INTO
# ---- biophysics). delta_p50-kind gap rows are TMC nm displacement drifts —
# ---- they land in the threshold-fold-shift pair, NOT the card delta columns.
GAP_MIGRATIONS = {
    "ion_selectivity_ratio": ("ion_selectivity_ratio", None),
    "ca_permeability": ("ca_permeability", None),
    "thermal_threshold": ("thermal_threshold_c", None),
    "macroscopic_rise_time": ("macroscopic_rise_time_ms", None),
    "threshold_fold_shift": ("threshold_fold_shift_value", "threshold_fold_shift_unit"),
    "delta_p50": ("threshold_fold_shift_value", "threshold_fold_shift_unit"),
    "osmotic_threshold": ("osmotic_threshold_value", "osmotic_threshold_unit"),
}

# ---- Adjudicated-kept gap rows: the KEEP rulings, verbatim from the
# ---- staging adjudication table (adjudication labels are load-bearing).
# ---- 16 rulings at data-v1.0; v1.1 adds 12 (2026-11-07 Duru proteoliposome
# ---- first-opening thresholds mmHg/mN/m + pN/nm as-printed; 2026-11-08
# ---- batch-3 open_probability Po ×5) → 28 KEEP rows at data-v1.1.
# ---- Unit strings are load-bearing keys, staging parity: "mm Hg" (spaced) =
# ---- the v1.0-era in-vivo phenotype thresholds; "mmHg"/"mN/m"/"pN/nm" (v1.1,
# ---- Duru) = proteoliposome first-opening thresholds — same kind, different
# ---- semantics; a future paper reporting liposome thresholds spaced MUST
# ---- extend this table, never reuse the in-vivo label.
GAP_KEEPS = {
    ("ion_selectivity_ratio", "mV/decade"):
        "KEEP: kind-borrowed (Erev-vs-[K+] slope in mV/decade, not a ratio)",
    ("pressure_threshold", "mm Hg"):
        "KEEP: in-vivo behavioral/neural phenotype (not a channel parameter)",
    ("pressure_threshold", "nN/um2"):
        "KEEP: in-situ stress midpoint (adjudicated 2026-08-21: "
        "reserve p50 for patch-clamp midpoints)",
    ("pressure_threshold", "µm"):
        "KEEP: first-response detection threshold (not a midpoint)",
    ("pressure_threshold", "mmHg"):
        "KEEP: proteoliposome first-opening pressure threshold "
        "(not a midpoint; p50 column owns Boltzmann midpoints)",
    ("pressure_threshold", "mN/m"):
        "KEEP: proteoliposome first-opening tension threshold "
        "(not a midpoint; t50 column owns tension midpoints)",
    ("pressure_threshold", "pN/nm"):
        "KEEP: proteoliposome first-opening tension threshold, as-printed "
        "spelling (1 pN/nm = 1 mN/m exact equivalence, no conversion; "
        "not a midpoint)",
    ("block_voltage", "mV"):
        "KEEP: niche permeation metric (blocker V50, not a reversal potential)",
    ("block_voltage", ""):
        "KEEP: Woodhull electrical distance delta (dimensionless)",
    ("open_probability", ""):
        "KEEP: channel/resting open probability Po (dimensionless 0..1 "
        "fraction, not a midpoint or threshold)",
    ("x50", "nm"):
        "KEEP: demoted-contested (combined TRPV4+PIEZO1 current, not channel-isolated)",
    ("tau_act", "ms"):
        "KEEP: demoted-contested (direct gating contested)",
}


def _f(cell: str | None) -> float | None:
    """Numeric cell: empty/range/composite text → None (original preserved
    in as-reported / experiment_label; no guessing — staging rule, verbatim)."""
    cell = (cell or "").strip()
    if not cell:
        return None
    try:
        return float(cell)
    except ValueError:
        return None


def _s(cell: str | None) -> str | None:
    return (cell or "").strip() or None


def _convert(r: dict) -> tuple[float | None, float | None, bool]:
    """Pre-authorized conversion: (value, error, converted?). value and error
    co-scale; as-reported originals are kept verbatim by the caller."""
    m = _REPORTED_UNIT_RE.search(r.get("extractor_note") or "")
    v = _f(r["value"])
    e = _f(r.get("error", ""))
    if not m or v is None:
        return v, e, False
    factor, _label = PREAUTHORIZED_CONVERSIONS[m.group(1)]
    return round(v * factor, 6), (round(e * factor, 6) if e is not None else None), True


def _parse_short_mutation(hg: str) -> tuple[int | None, str | None, str | None]:
    """'A1988V' → (1988, 'A', 'V'); anything else → (None, None, None)."""
    # strict substitution form only (single-letter AA ref/alt): 'A1988V' parses;
    # 'E756del' / complex HGVS → (None, None, None), stored verbatim regardless
    m = re.fullmatch(r"([A-Za-z])(\d+)([A-Za-z])", hg or "")
    if not m:
        return None, None, None
    return int(m.group(2)), m.group(1), m.group(3)


def _experiment_label(r: dict) -> str | None:
    """Lossless verbatim context for columns the card does not carry
    (stimulus_detail/value/unit + modulator context + unparseable temp/ph).
    No parsing, no interpretation — concatenation with | separators."""
    parts = []
    if _s(r.get("stimulus_detail")):
        parts.append(_s(r.get("stimulus_detail")))
    if _s(r.get("stimulus_value")):
        parts.append(f"STIMULUS: {r['stimulus_value'].strip()}"
                     f"{(' ' + r['stimulus_value_unit'].strip()) if _s(r.get('stimulus_value_unit')) else ''}")
    name, role = _s(r.get("modulator_name")), _s(r.get("modulator_role"))
    if name:
        conc = _s(r.get("modulator_concentration"))
        conc_u = _s(r.get("modulator_conc_unit"))
        ctx = f"MODULATOR: {name}" + (f" ({role})" if role else "")
        if conc:
            ctx += f" {conc}{(' ' + conc_u) if conc_u else ''}"
        parts.append(ctx)
    if _s(r.get("temperature_c")) and _f(r.get("temperature_c")) is None:
        parts.append(f"TEMPERATURE-AS-REPORTED: {r['temperature_c'].strip()}")
    if _s(r.get("ph")) and _f(r.get("ph")) is None:
        parts.append(f"PH-AS-REPORTED: {r['ph'].strip()}")
    return " | ".join(parts) or None


# --------------------------------------------------------------------------- #
# Vault access
# --------------------------------------------------------------------------- #
def _git(vault: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(vault), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def verify_vault(vault: Path, require_tag: str | None) -> str:
    """Vault must be a clean git checkout; with --require-tag the tag must
    point at HEAD (freeze enforcement). Returns the HEAD sha."""
    head = _git(vault, "rev-parse", "HEAD")
    # untracked files (local scratch) don't affect tracked freeze content
    status = _git(vault, "status", "--porcelain", "--untracked-files=no")
    if status:
        raise RuntimeError(f"vault tracked content modified:\n{status}")
    if require_tag:
        exists = subprocess.run(
            ["git", "-C", str(vault), "rev-parse", "--verify", f"refs/tags/{require_tag}"],
        ).returncode == 0
        if not exists:
            raise RuntimeError(f"tag {require_tag!r} not found in the vault")
        tagged = _git(vault, "rev-list", "-n", "1", require_tag)
        ancestor = subprocess.run(
            ["git", "-C", str(vault), "merge-base", "--is-ancestor", tagged, head],
        ).returncode == 0
        if not ancestor:
            raise RuntimeError(
                f"tag {require_tag} ({tagged[:7]}) is not an ancestor of HEAD "
                f"({head[:7]}) — history diverged from the freeze")
        # The frozen content (12 layer datasets — data/<ch>/** incl. per-layer
        # READMEs and data/db/ — + identity configs, configs/*.yaml) must be
        # byte-unchanged since the tag. Root-level schema docs (data/*.md —
        # extraction_schema.md's Rules/enum sections evolve with the validator;
        # CLAUDE.md: "doc side lives in the vault's data/extraction_schema.md —
        # change both together") and validator-state registries (configs/*.json
        # — composite_quote_registry, quote_landing_allowlist) are legal
        # post-freeze churn. (2026-09-03 narrowing: the previous blanket
        # `data/ + configs/` pathspec over-captured docs, blocking vault
        # skill-patch PR #66 cross-repo — user decision, Option A.)
        # The exclude globs MUST be glob-anchored (`:(exclude,glob)`) — git's
        # default pathspec mode lets `*` cross `/`, and the un-anchored form
        # silently un-froze all 47 data/**.md files (per-layer READMEs, incident
        # sidecars) instead of the 2 root docs (gate r1 MINOR, 2026-09-03;
        # anchored form re-verified against README-changing commit 8cdb764;
        # count erratum 48→47 per vault PR-#67-gate recount, same day).
        diff = subprocess.run(
            ["git", "-C", str(vault), "diff", "--stat", f"{tagged}..{head}", "--",
             "data/", "tools/literature-mining/configs/",
             ":(exclude,glob)data/*.md",
             ":(exclude,glob)tools/literature-mining/configs/*.json"],
            capture_output=True, text=True).stdout.strip()
        if diff:
            raise RuntimeError(
                f"frozen content changed since {require_tag}:\n{diff}")
    return head


def read_rows(vault: Path) -> list[dict]:
    rows = []
    for layer in LAYERS:
        path = vault / "data" / layer / "extraction" / "extracted_measurements.csv"
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                r["source_layer"] = layer
                rows.append(r)
    return rows


def read_configs(vault: Path) -> dict[str, dict]:
    import yaml  # justified dependency: vault configs are YAML
    cfgs = {}
    for layer in LAYERS:
        p = vault / "tools/literature-mining/configs" / f"{LAYER_TO_CONFIG[layer]}.yaml"
        cfgs[layer] = yaml.safe_load(p.read_text(encoding="utf-8"))
    return cfgs


def read_zotero_authors(vault: Path) -> dict[str, list[str]]:
    """DOI → full author list from the vault's Zotero export (CSL-JSON).
    'author' entries: [{'family': 'Shan', 'given': 'Yu'}, …] → ["Shan Y", …]."""
    p = vault / ".pandoc/zotero-library-1.json"
    out: dict[str, list[str]] = {}
    for item in json.loads(p.read_text(encoding="utf-8")):
        doi = (item.get("DOI") or "").strip().lower()
        if not doi:
            continue
        authors = []
        for c in item.get("author") or []:
            fam, giv = c.get("family"), c.get("given")
            if fam:
                authors.append(f"{fam} {giv[0]}".strip() if giv else fam)
        if authors:
            out.setdefault(doi, authors)
    return out


# --------------------------------------------------------------------------- #
# Load
# --------------------------------------------------------------------------- #
def load_vault(vault: Path, out_sqlite: Path, require_tag: str | None = FREEZE_TAG,
               manifest_path: Path | None = None) -> dict:
    """Load the vault corpus into the formal schema. Returns the manifest."""
    head = verify_vault(vault, require_tag)
    rows = read_rows(vault)
    cfgs = read_configs(vault)
    zotero = read_zotero_authors(vault)
    manifest: dict = {
        "vault_head": head, "freeze_tag": require_tag or "(none)",
        "schema_version": SCHEMA_VERSION, "counts": {}, "disclosures": [],
    }
    acc = AccessionGenerator()

    if out_sqlite.exists():
        out_sqlite.unlink()  # the loader owns its output — always a fresh load
    engine = make_engine(f"sqlite:///{out_sqlite}", echo=False)
    create_all(engine)
    with Session(engine) as s:
        # ---- publication (205; DOI dedup; first-seen title; Zotero authors) --
        pubs: dict[str, Publication] = {}
        title_variants: Counter = Counter()
        for r in rows:
            doi = r["doi"]
            if doi in pubs:
                if r.get("title") and r["title"] != pubs[doi].title:
                    title_variants[doi] += 1
                continue
            zot = zotero.get(doi.lower())
            if zot is None:
                authors = [r["first_author"]] if _s(r.get("first_author")) else None
            else:
                authors = zot
            pubs[doi] = Publication(
                doi=doi, pmid=int(r["pmid"]) if str(r.get("pmid") or "").isdigit() else None,
                title=_s(r.get("title")), journal=_s(r.get("journal")),
                year=int(r["publication_year"]) if str(r.get("publication_year") or "").isdigit() else None,
                authors=authors, created_at=FREEZE_EPOCH)
            s.add(pubs[doi])
        manifest["counts"]["publication"] = len(pubs)
        manifest["disclosures"].append(
            f"authors: {sum(1 for p in pubs.values() if p.authors and len(p.authors) > 1)} "
            "publications Zotero-enriched; first_author-only fallback for the rest")
        if title_variants:
            manifest["disclosures"].append(
                f"publication title variants (first-seen kept): {len(title_variants)} DOIs")

        # ---- channel (12; one row per layer; osca = one family row) ----------
        channels: dict[str, Channel] = {}
        xref_rows: list[ExternalReference] = []
        xref_json = vault / "data/piezo1/cross_references/piezo1_cross_references.json"
        piezo1_xref = json.loads(xref_json.read_text(encoding="utf-8")) if xref_json.exists() else {}
        for layer in LAYERS:
            p = cfgs[layer]["protein"]
            ident = CHANNEL_IDENTITY[layer]
            uni = (p.get("uniprot") or "").strip()
            try:
                family = FAMILY_MAP[p["family"]]
            except KeyError:
                raise ValueError(
                    f"config family {p['family']!r} ({layer}) not in FAMILY_MAP — "
                    "extend the map explicitly")
            aliases = list(p.get("aliases") or [])
            extra: dict = {}
            if layer == "piezo1" and piezo1_xref:
                # cross_references JSON is the richer identity source for piezo1
                extra = dict(ncbi_gene_id=piezo1_xref.get("ncbi_gene_id"),
                             sequence_length=piezo1_xref.get("sequence_length"),
                             summary=None)
                aliases = list(piezo1_xref.get("gene_aliases") or aliases)
            if layer == "osca":
                # DECIDED §6.2: one family row; the four accessions → xrefs.
                for a in [u for u in uni.split("/") if u]:
                    xref_rows.append(ExternalReference(
                        entity_type=EntityType.CHANNEL, entity_id=None,  # patched post-flush
                        source_db=SourceDb.UNIPROT, external_id=a,
                        created_at=FREEZE_EPOCH))
                uni = None
            ch = Channel(
                maicdb_id=acc.next(AccessionPrefix.CHANNEL),
                gene_symbol=p["gene_symbol"], gene_aliases=aliases or None,
                uniprot_accession=uni or None,
                organism=ident["organism"], organism_taxid=ident["taxid"],
                family=family,
                activation_mechanism=ACTIVATION_MECHANISM.get(p["family"]),
                ortholog_group=p["gene_symbol"].upper(),
                source_db=SourceDb.UNIPROT, collected_date=FREEZE_DATE,
                publication_id=None, created_at=FREEZE_EPOCH, **extra)
            s.add(ch)
            channels[layer] = ch
            if layer == "piezo1" and piezo1_xref:
                for key, sdb in (("chembl_target_human", SourceDb.CHEMBL_TARGET),
                                 ("chembl_target_mouse", SourceDb.CHEMBL_TARGET)):
                    if piezo1_xref.get(key):
                        xref_rows.append(ExternalReference(
                            entity_type=EntityType.CHANNEL, entity_id=None,
                            source_db=sdb, external_id=piezo1_xref[key],
                            created_at=FREEZE_EPOCH))
        s.flush()
        for x in xref_rows:  # patch entity_id now that channels have ids
            ch = channels["piezo1"] if x.source_db == SourceDb.CHEMBL_TARGET else channels["osca"]
            x.entity_id = ch.id
            s.add(x)
        manifest["counts"]["channel"] = len(channels)
        manifest["counts"]["external_reference"] = len(xref_rows)

        # ---- compound (85; modulator_name dedup; majority role; descriptors) -
        roles: dict[str, Counter] = {}
        unroled_activity_names: set[str] = set()
        for r in rows:
            name, role = _s(r.get("modulator_name")), _s(r.get("modulator_role"))
            if not name:
                continue
            if role in MODULATOR_ROLE_ENUM:
                roles.setdefault(name, Counter())[role] += 1
            elif r["db_target_table"] == "bioactivity":
                # bioactivity rows MUST link a compound (NOT NULL) — unroled
                # modulators (e.g. the silica-nanoparticle family) still get a
                # compound row, typed UNCLASSIFIED, disclosed in the manifest
                unroled_activity_names.add(name)
        for name in unroled_activity_names:
            roles.setdefault(name, Counter())
        joining = {n.lower() for n in roles}
        descriptors = _read_piezo1_compound_descriptors(vault, joining)
        compounds: dict[str, Compound] = {}
        used_inchikeys: set[str] = set()
        for name in sorted(roles):
            cnt = roles[name]
            winner = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if cnt else None
            ctype = ROLE_TO_COMPOUND_TYPE.get(winner, CompoundType.UNCLASSIFIED) if winner \
                else CompoundType.UNCLASSIFIED
            d = descriptors.get(name.lower(), {})
            if d.get("inchikey") and d["inchikey"] in used_inchikeys:
                # case-variant corpus names can share one descriptor row —
                # the UNIQUE key stays with the first (alphabetical) name
                d = {**d, "inchikey": None}
                manifest["disclosures"].append(
                    f"compound {name!r}: InChIKey already used by an earlier "
                    "case-variant name — descriptor key withheld")
            if d.get("inchikey"):
                used_inchikeys.add(d["inchikey"])
            compounds[name] = Compound(
                maicdb_id=acc.next(AccessionPrefix.COMPOUND),
                name=name, compound_type=ctype,
                smiles=d.get("smiles"), inchikey=d.get("inchikey"),
                molecular_weight=d.get("mw"), clogp=d.get("logp"),
                tpsa=d.get("tpsa"), hbd=d.get("hbd"), hba=d.get("hba"),
                rotatable_bonds=d.get("rotb"), aromatic_rings=d.get("rings"),
                heavy_atoms=d.get("heavy"), source=d.get("source"),
                lipinski_pass=d.get("lipinski"), veber_pass=d.get("veber"),
                is_duplicate=d.get("duplicate"),
                source_db=SourceDb.LITERATURE, collected_date=FREEZE_DATE,
                created_at=FREEZE_EPOCH)
            s.add(compounds[name])
        s.flush()
        manifest["counts"]["compound"] = len(compounds)
        if unroled_activity_names:
            manifest["disclosures"].append(
                f"unroled bioactivity modulators typed UNCLASSIFIED: "
                f"{sorted(unroled_activity_names)}")
        manifest["disclosures"].append(
            f"compound descriptors: {sum(1 for c in compounds.values() if c.inchikey)} / "
            f"{len(compounds)} carry InChIKey (piezo1 compounds descriptor CSV, name join; duplicate keys awarded to corpus-joining names)")

        # ---- variant (125; hgvs_short dedup) ---------------------------------
        variants: dict[str, Variant] = {}
        for r in sorted(rows, key=lambda x: x["measurement_id"]):
            hg = _s(r.get("variant_hgvs_short"))
            if hg and hg not in variants:
                pos, ref, alt = _parse_short_mutation(hg)
                variants[hg] = Variant(
                    maicdb_id=acc.next(AccessionPrefix.VARIANT),
                    channel_id=channels[r["source_layer"]].id,
                    mutation_short=hg, position=pos, ref_aa=ref, alt_aa=alt,
                    source_db=SourceDb.LITERATURE, collected_date=FREEZE_DATE,
                    created_at=FREEZE_EPOCH)
                s.add(variants[hg])
        s.flush()
        manifest["counts"]["variant"] = len(variants)

        # ---- structure (12; piezo1 only) --------------------------------------
        st_csv = vault / "data/piezo1/structures/piezo1_pdb_structures.csv"
        n_struct = 0
        if st_csv.exists():
            st_pubs: dict[str, Publication] = {}
            pending_links: list[tuple[Structure, str | None]] = []
            with st_csv.open(newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    pub_doi = None
                    raw = vault / "data/piezo1/raw/piezo1_pdb_entries_detail" / f"{r['PDB_ID']}.json"
                    if raw.exists():
                        cit = (json.loads(raw.read_text(encoding="utf-8"))
                               .get("citation") or [{}])[0]
                        doi = _s(cit.get("pdbx_database_id_DOI"))
                        if doi:
                            pub_doi = doi
                            if doi in pubs:
                                pass  # already known from extraction rows
                            elif doi not in st_pubs:
                                pmid = cit.get("pdbx_database_id_PubMed")
                                st_pubs[doi] = Publication(
                                    doi=doi,
                                    title=(_s(cit.get("title") or "") or None) and _s(cit.get("title") or "").rstrip("."),
                                    journal=_s(cit.get("journal_abbrev")),
                                    year=int(str(cit.get("year"))) if str(cit.get("year") or "").isdigit() else None,
                                    authors=[f"{a.split(',')[0]} {a.split(',')[1].strip()[0]}"
                                             .strip() if "," in a else a
                                             for a in (cit.get("rcsb_authors") or [])] or None,
                                    pmid=int(pmid) if str(pmid or "").isdigit() else None,
                                    created_at=FREEZE_EPOCH)
                                s.add(st_pubs[doi])
                    st = Structure(
                        maicdb_id=acc.next(AccessionPrefix.STRUCTURE),
                        channel_id=channels["piezo1"].id,
                        pdb_id=r["PDB_ID"], structure_source=StructureSource.PDB,
                        title=_s(r.get("Title")), method=_s(r.get("Method")),
                        resolution_a=_f(r.get("Resolution_A")),
                        organism=_s(r.get("Organism")),
                        num_chains=int(r["Num_Chains"]) if str(r.get("Num_Chains") or "").isdigit() else None,
                        has_inhibitor=r.get("Has_Inhibitor", "").strip().lower() == "true",
                        source_db=SourceDb.PDB, collected_date=FREEZE_DATE,
                        created_at=FREEZE_EPOCH)
                    s.add(st)
                    pending_links.append((st, pub_doi))
                    n_struct += 1
            # publication.id exists only after flush — patch links post-flush
            # (same pattern as the external_reference block; the r1 gate
            # caught the constructor-time-id NULL bug here)
            s.flush()
            linked = 0
            for st, doi in pending_links:
                pub = pubs.get(doi) or st_pubs.get(doi)
                if pub is not None and pub.id is not None:
                    st.publication_id = pub.id
                    linked += 1
            manifest["counts"]["structure_publication_links"] = linked
            if linked < 8:  # 10 of 12 raw citations carry a DOI
                raise AssertionError(
                    f"structure→publication linkage suspiciously low: {linked}/12")
            manifest["counts"]["publication"] += len(st_pubs) - sum(
                1 for d in st_pubs if d in pubs)  # net new structure-only pubs
            pubs.update(st_pubs)
        manifest["counts"]["structure"] = n_struct

        # ---- facts -------------------------------------------------------------
        def variant_id(r: dict) -> int | None:
            hg = _s(r.get("variant_hgvs_short"))
            return variants[hg].id if hg and hg in variants else None

        def common(r: dict, obj) -> None:
            obj.measurement_id = r["measurement_id"]
            obj.evidence_quote = r["evidence_quote"]
            obj.evidence_location = _s(r.get("evidence_location"))
            obj.confidence = _s(r.get("confidence"))
            obj.extractor_note = _s(r.get("extractor_note"))
            obj.condition_key = _s(r.get("condition_key"))
            obj.n = _s(r.get("n"))

        def mimic(r: dict, obj) -> None:
            obj.recording_mode = _s(r.get("recording_mode"))
            obj.stimulus_type = _s(r.get("stimulus_type"))
            obj.expression_system = _s(r.get("expression_system"))
            obj.cell_type = _s(r.get("cell_type"))
            obj.temperature_c = _f(r.get("temperature_c"))
            obj.ph = _f(r.get("ph"))
            obj.bath_solution = _s(r.get("bath_solution"))
            obj.pipette_solution = _s(r.get("pipette_solution"))
            obj.holding_potential_mv = _f(r.get("holding_potential_mv"))

        counts = Counter()
        for r in sorted(rows, key=lambda x: x["measurement_id"]):
            table = r["db_target_table"]
            ch = channels[r["source_layer"]]
            if table == "biophysics_experiment":
                counts["biophysics"] += 1
                bx = BiophysicsExperiment(
                    maicdb_id=acc.next(AccessionPrefix.BIOPHYSICS_EXPERIMENT),
                    channel_id=ch.id, variant_id=variant_id(r),
                    parameter_set=_s(r.get("db_parameter_set")),
                    experiment_label=_experiment_label(r),
                    source_db=SourceDb.LITERATURE, collected_date=FREEZE_DATE,
                    publication_id=pubs[r["doi"]].id, created_at=FREEZE_EPOCH)
                common(r, bx)
                mimic(r, bx)
                _route_biophysics(r, bx)
                s.add(bx)
            elif table == "bioactivity":
                counts["bioactivity"] += 1
                name = _s(r.get("modulator_name"))
                value, _e, _c = _convert(r)
                at = (r.get("activity_type") or r["parameter_kind"].upper()).strip()
                activity_type = (ActivityType[at] if at in ActivityType.__members__
                                 else ActivityType(at))  # name lookup first (KI=Ki)
                ba = Bioactivity(
                    maicdb_id=acc.next(AccessionPrefix.BIOACTIVITY),
                    compound_id=compounds[name].id if name and name in compounds else None,
                    channel_id=ch.id,
                    activity_type=activity_type,
                    activity_value=value, activity_units=_s(r.get("unit")),
                    relation=_s(r.get("value_relation")),
                    assay_description=" | ".join(filter(None, [_s(r.get("parameter_label")), _s(r.get("stimulus_detail"))])),
                    source_db=SourceDb.LITERATURE, collected_date=FREEZE_DATE,
                    publication_id=pubs[r["doi"]].id, created_at=FREEZE_EPOCH)
                common(r, ba)
                s.add(ba)
            elif table == "schema_gap":
                kind, unit = r["parameter_kind"], (r.get("unit") or "").strip()
                if (kind, unit) in GAP_KEEPS:  # exceptions FIRST — staging checks
                    # the mV/decade kind-borrowing INSIDE the migration branch
                    counts["unmapped"] += 1
                    s.add(UnmappedMeasurement(
                        maicdb_id=acc.next(AccessionPrefix.UNMAPPED_MEASUREMENT),
                        channel_id=ch.id, parameter_kind=kind,
                        value=_f(r["value"]), unit=unit or None,
                        adjudication=GAP_KEEPS[(kind, unit)],
                        source_db=SourceDb.LITERATURE, collected_date=FREEZE_DATE,
                        publication_id=pubs[r["doi"]].id, created_at=FREEZE_EPOCH,
                        **{"measurement_id": r["measurement_id"],
                           "evidence_quote": r["evidence_quote"],
                           "evidence_location": _s(r.get("evidence_location")),
                           "confidence": _s(r.get("confidence")),
                           "extractor_note": _s(r.get("extractor_note")),
                           "condition_key": _s(r.get("condition_key")),
                           "n": _s(r.get("n"))}))
                elif kind in GAP_MIGRATIONS:
                    counts["biophysics"] += 1
                    bx = BiophysicsExperiment(
                        maicdb_id=acc.next(AccessionPrefix.BIOPHYSICS_EXPERIMENT),
                        channel_id=ch.id, variant_id=variant_id(r),
                        parameter_set=_s(r.get("db_parameter_set")),
                        experiment_label=_experiment_label(r),
                        source_db=SourceDb.LITERATURE, collected_date=FREEZE_DATE,
                        publication_id=pubs[r["doi"]].id, created_at=FREEZE_EPOCH)
                    common(r, bx)
                    mimic(r, bx)
                    _route_gap_migration(r, bx)
                    s.add(bx)
                else:
                    raise ValueError(
                        f"unadjudicated gap combination: {r['measurement_id']} "
                        f"kind={kind!r} unit={unit!r}")
            else:
                raise ValueError(f"unknown db_target_table {table!r} in {r['measurement_id']}")
        for k in ("biophysics", "bioactivity", "unmapped"):
            manifest["counts"][k] = counts[k]
        manifest["disclosures"].append(
            "ratio_direction NULL this load: staging's 70 classified direction "
            "values (note/web/machine provenance) were not ported — parse "
            "deferred post-v1.0 (direction survives in the CSV parameter_label)")
        manifest["counts"]["unit_conversions"] = sum(
            1 for r in rows if _REPORTED_UNIT_RE.search(r.get("extractor_note") or ""))

        # ---- db_meta ------------------------------------------------------------
        for k, v in (("schema_version", SCHEMA_VERSION), ("license", "CC-BY-4.0"),
                     ("release_date", FREEZE_DATE.isoformat()),
                     ("mimic_standard_version", "v0.1-draft (MAICDB_Schema_Design §4.3)"),
                     ("data_freeze_tag", f"{FREEZE_TAG}@{head[:12]}"),
                     ("vault_repository", "Lilong-Dong-Lab/Project_DataBase_MAICDB")):
            s.add(DbMeta(key=k, value=v))
        s.commit()

    # ---- conservation asserts (spec §4) ------------------------------------
    # data-v1.1 calibers: 1125 rows = 960 biophysics (829 normal-route + 131
    # gap-adjudicated migrations) + 137 bioactivity + 28 unmapped (KEEP rows;
    # v1.0 was 1100 = 948 + 136 + 16).
    expected = {"publication": None, "channel": 12, "structure": 12,
                "biophysics": 960, "bioactivity": 137, "unmapped": 28}
    for table, want in expected.items():
        got = manifest["counts"][table]
        if want is not None and got != want:
            raise AssertionError(f"conservation: {table} = {got}, expected {want}")
    total = sum(manifest["counts"][t] for t in ("biophysics", "bioactivity", "unmapped"))
    if total != 1125 or len(rows) != 1125:
        raise AssertionError(
            f"conservation: facts {total} (want 1125); rows read {len(rows)} (want 1125)")

    # ---- deterministic SQL dump ---------------------------------------------
    out_sql = out_sqlite.with_suffix(".sql")
    import sqlite3
    conn = sqlite3.connect(out_sqlite)
    lines = list(conn.iterdump())
    conn.close()
    # SQLite emits the CREATE [UNIQUE] INDEX block in nondeterministic order
    # across connections — sort it for a byte-stable dump (indexes are
    # order-independent).
    idx = [i for i, ln in enumerate(lines) if ln.startswith("CREATE " ) and " INDEX " in ln]
    if idx:
        block = sorted(lines[idx[0]: idx[-1] + 1])
        lines[idx[0]: idx[-1] + 1] = block
    dump = "\n".join(lines)
    out_sql.write_text(dump + "\n", encoding="utf-8", newline="\n")
    manifest["dump"] = str(out_sql)
    if manifest_path:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    return manifest


def _route_biophysics(r: dict, bx: BiophysicsExperiment) -> None:
    """Normal routing (KIND_TO_CARD) + conversions + as-reported pair."""
    kind = r["parameter_kind"]
    col, unit_col = KIND_TO_CARD[kind]
    value, _error, converted = _convert(r)
    bx.value_as_reported = _s(r.get("value"))
    bx.unit_as_reported = _s(r.get("unit"))
    if _s(r.get("error")):
        # the formal card carries no error column — preserve the as-printed
        # precision losslessly via experiment_label (established pattern for
        # card-less columns; promotable to a typed column post-v1.0)
        lab = f"ERROR-AS-REPORTED: {r['error'].strip()}"
        etype = _s(r.get("error_type"))
        bx.experiment_label = f"{bx.experiment_label} | {lab}{f' ({etype})' if etype else ''}" if bx.experiment_label else lab
    if kind == "iv_relation":
        setattr(bx, col, r["value"].strip())  # NAME string, no numeric path
        return
    setattr(bx, col, value)
    if unit_col and _s(r.get("unit_db")):
        setattr(bx, unit_col, UNIT_ENUMS[unit_col](_s(r["unit_db"])))
    # converted error co-scale has no typed home either; the as-reported pair
    # preserves the original value and the hook in extractor_note makes the
    # conversion re-derivable. The conversion tally lands in the manifest.


def _route_gap_migration(r: dict, bx: BiophysicsExperiment) -> None:
    """Gap-adjudicated migration routing (GAP_MIGRATIONS, staging parity)."""
    kind, unit = r["parameter_kind"], (r.get("unit") or "").strip()
    val_col, unit_col = GAP_MIGRATIONS[kind]
    value = _f(r["value"])
    if kind == "macroscopic_rise_time" and unit == "s":
        value = round(value * 1000.0, 6)  # adjudicated s→ms channel
    setattr(bx, val_col, value)
    if unit_col and unit:
        setattr(bx, unit_col, unit)
    bx.value_as_reported = _s(r.get("value"))
    bx.unit_as_reported = unit or None


def _read_piezo1_compound_descriptors(vault: Path,
                                      joining_names: set[str] | None = None) -> dict[str, dict]:
    """piezo1 compounds CSV → name-normalized descriptor dict (lower-case join).

    The CSV carries duplicate InChIKeys under alias rows (CHEMBL-id names)
    that never join a corpus modulator — among rows sharing a key, the name
    that JOINS a corpus modulator keeps it (r1-gate MINOR-3: first-row-wins
    starved Yoda1/Jedi1/Jedi2 of their keys)."""
    joining = joining_names or set()
    p = vault / "data/piezo1/compounds/piezo1_compounds_properties.csv"
    raw_rows: list[tuple[str, dict]] = []
    if p.exists():
        with p.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                name = (r.get("Name") or "").strip().lower()
                if not name:
                    continue
                def _i(key): return int(r[key]) if str(r.get(key) or "").strip().lstrip("-").isdigit() else None
                raw_rows.append((name, {
                    "smiles": _s(r.get("SMILES")), "inchikey": _s(r.get("InChIKey")),
                "mw": _f(r.get("MW")), "logp": _f(r.get("LogP")), "tpsa": _f(r.get("TPSA")),
                "hbd": _i("HBD"), "hba": _i("HBA"), "rotb": _i("RotBonds"),
                "rings": _i("AromaticRings"), "heavy": _i("HeavyAtoms"),
                "source": _s(r.get("Source")) or None,
                    "lipinski": _bool(r.get("Lipinski_Pass")), "veber": _bool(r.get("Verber_Pass")) or _bool(r.get("Veber_Pass")),
                    "duplicate": _bool(r.get("Duplicate")),
                }))
    out: dict[str, dict] = {}
    # group rows sharing an InChIKey; the group's joining member (else the
    # first) keeps the UNIQUE key, the others get None
    key_groups: dict[str, list[str]] = {}
    for name, d in raw_rows:
        if d.get("inchikey"):
            key_groups.setdefault(d["inchikey"], []).append(name)
    winner_of: dict[str, str] = {}
    for key, names in key_groups.items():
        joiners = [n for n in names if n in joining]
        winner_of[key] = sorted(joiners)[0] if joiners else sorted(names)[0]
    for name, d in raw_rows:
        k = d.get("inchikey")
        if k and winner_of.get(k) != name:
            d = {**d, "inchikey": None}
        out[name] = d
    return out


def _bool(cell: str | None) -> bool | None:
    v = (cell or "").strip().lower()
    if v == "true":
        return True
    if v == "false":
        return False
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Load the vault data-v1.0 corpus into the formal schema")
    ap.add_argument("--vault", required=True, type=Path, help="vault repo checkout path")
    ap.add_argument("--require-tag", default=FREEZE_TAG,
                    help=f"freeze tag HEAD must point at (default {FREEZE_TAG}; '' disables)")
    ap.add_argument("-o", "--output", type=Path, default=Path("maicdb.sqlite"))
    ap.add_argument("--manifest", type=Path, default=None, help="write load manifest JSON here")
    args = ap.parse_args()
    manifest = load_vault(args.vault, args.output,
                          require_tag=args.require_tag or None,
                          manifest_path=args.manifest)
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    print(f"dump: {manifest['dump']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

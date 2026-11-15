"""Vault seam — the single place maicdb-code knows the vault's location,
layout, and freeze contract.

Every vault reference outside this module goes through it:

* :func:`resolve_vault` — location discovery: an explicit argument wins,
  then the ``MAICDB_VAULT`` env var, then the sibling checkout
  ``../Project_DataBase_MAICDB`` next to this repo. The sibling form is
  a property of a source checkout (editable install / ``PYTHONPATH=src``);
  a wheel install must pass an explicit path or the env var.
* :class:`FrozenVault` — one vault checkout opened for reading under the
  freeze contract: ``verify()`` (clean tracked tree, tag resolves, HEAD
  descends from the tag, frozen surface unchanged since the tag) plus
  typed accessors for everything the loader reads. The loader keeps the
  transforms; this module owns the paths.

Resolution does no I/O and never *finds* a vault implicitly for library
callers: ``load_vault`` still takes an explicit path — only the CLI
entry point (``maicdb loader.main``) applies :func:`resolve_vault` to
its optional ``--vault`` argument.

Born 2026-11-15 (architecture-review candidate 3): discovery previously
lived in ``tests/test_loader.py`` and the layout constants in
``maicdb.loader``; both moved here unchanged (pure motion — the freeze
contract itself is reworked into a hash-pinned freeze manifest in the
follow-up PR).
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
from pathlib import Path

__all__ = ["CHANNEL_DIRS", "FrozenVault", "LAYERS", "LAYER_TO_CONFIG",
           "SIBLING_NAME", "resolve_vault"]

#: Sibling checkout name used by :func:`resolve_vault`'s last resort.
SIBLING_NAME = "Project_DataBase_MAICDB"

#: The 12 corpus layers in canonical sequence. Load-bearing beyond layout:
#: first-seen publication insertion (title dedup) follows this order at
#: load time.
LAYERS = ["piezo1", "piezo2", "trpv4", "asic", "mscs", "mscl", "osca",
          "tmc", "tresk", "traak", "trek-1", "trek-2"]

#: The same layers sorted — the frozen corpus's ``data/`` directory set
#: (presence/intactness checks; census: spec §4 — ``SELECT gene_symbol
#: FROM channel`` lowercased).
CHANNEL_DIRS = sorted(LAYERS)

#: Config file stem per layer (``tools/literature-mining/configs/<stem>.yaml``
#: — channel dashes stripped).
LAYER_TO_CONFIG = {layer: layer.replace("-", "") for layer in LAYERS}


def resolve_vault(explicit: str | Path | None = None) -> Path:
    """Vault discovery: an explicit argument wins, then ``$MAICDB_VAULT``,
    then the sibling checkout next to this repo. Returns the path
    UNVERIFIED — presence and freeze state are :meth:`FrozenVault.verify`
    (and the READ-based :meth:`FrozenVault.readable` probe) business."""
    if explicit:
        return Path(explicit)
    env = os.environ.get("MAICDB_VAULT")
    if env:
        return Path(env)
    # src/maicdb/vault.py → parents: [src/maicdb, src, repo root]
    return Path(__file__).resolve().parents[2].parent / SIBLING_NAME


def _git(vault: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(vault), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


class FrozenVault:
    """One vault checkout opened for reading under the freeze contract.

    Construction does no I/O; the accessors and :meth:`verify` do.
    """

    def __init__(self, vault: Path, require_tag: str | None = None) -> None:
        self.vault = Path(vault)
        self.require_tag = require_tag

    # ------------------------------------------------------------------ #
    # Freeze contract
    # ------------------------------------------------------------------ #
    def verify(self) -> str:
        """The vault must be a clean git checkout; with a tag required the
        tag must point at HEAD's ancestry (freeze enforcement). Returns the
        HEAD sha. Fully silent (quirk 11: every git probe captures its
        stdio)."""
        head = _git(self.vault, "rev-parse", "HEAD")
        # untracked files (local scratch) don't affect tracked freeze content
        status = _git(self.vault, "status", "--porcelain", "--untracked-files=no")
        if status:
            raise RuntimeError(f"vault tracked content modified:\n{status}")
        if self.require_tag:
            exists = subprocess.run(
                ["git", "-C", str(self.vault), "rev-parse", "--verify",
                 f"refs/tags/{self.require_tag}"],
                capture_output=True, text=True,
            ).returncode == 0
            if not exists:
                raise RuntimeError(f"tag {self.require_tag!r} not found in the vault")
            tagged = _git(self.vault, "rev-list", "-n", "1", self.require_tag)
            ancestor = subprocess.run(
                ["git", "-C", str(self.vault), "merge-base", "--is-ancestor",
                 tagged, head],
                capture_output=True, text=True,
            ).returncode == 0
            if not ancestor:
                raise RuntimeError(
                    f"tag {self.require_tag} ({tagged[:7]}) is not an ancestor of HEAD "
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
                ["git", "-C", str(self.vault), "diff", "--stat",
                 f"{tagged}..{head}", "--",
                 "data/", "tools/literature-mining/configs/",
                 ":(exclude,glob)data/*.md",
                 ":(exclude,glob)tools/literature-mining/configs/*.json"],
                capture_output=True, text=True).stdout.strip()
            if diff:
                raise RuntimeError(
                    f"frozen content changed since {self.require_tag}:\n{diff}")
        return head

    def readable(self) -> bool:
        """Presence probe that READS (quirk 8): ``exists()`` and ``is_dir()``
        survive macOS TCC denial (stat succeeds, reads EPERM), so a stat-only
        probe reports a locked vault as present and the full-load tests fail
        red instead of skipping. One real open() of a tracked file settles it.
        """
        try:
            (self.vault / "README.md").open("rb").close()
            return True
        except OSError:
            return False

    def has_channel_dirs(self) -> bool:
        """All 12 frozen channel directories present under ``data/``."""
        return all((self.vault / "data" / ch).is_dir() for ch in CHANNEL_DIRS)

    # ------------------------------------------------------------------ #
    # Corpus reads
    # ------------------------------------------------------------------ #
    def measurements(self) -> list[dict]:
        rows = []
        for layer in LAYERS:
            path = (self.vault / "data" / layer / "extraction"
                    / "extracted_measurements.csv")
            with path.open(newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    r["source_layer"] = layer
                    rows.append(r)
        return rows

    def configs(self) -> dict[str, dict]:
        import yaml  # justified dependency: vault configs are YAML
        cfgs = {}
        for layer in LAYERS:
            p = (self.vault / "tools/literature-mining/configs"
                 / f"{LAYER_TO_CONFIG[layer]}.yaml")
            cfgs[layer] = yaml.safe_load(p.read_text(encoding="utf-8"))
        return cfgs

    def zotero_authors(self) -> dict[str, list[str]]:
        """DOI → full author list from the vault's Zotero export (CSL-JSON).
        'author' entries: [{'family': 'Shan', 'given': 'Yu'}, …] → ["Shan Y", …]."""
        p = self.vault / ".pandoc/zotero-library-1.json"
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

    # ------------------------------------------------------------------ #
    # piezo1 companion datasets (layout owned here; the loader transforms)
    # ------------------------------------------------------------------ #
    @property
    def piezo1_cross_references_json(self) -> Path:
        return self.vault / "data/piezo1/cross_references/piezo1_cross_references.json"

    @property
    def piezo1_structures_csv(self) -> Path:
        return self.vault / "data/piezo1/structures/piezo1_pdb_structures.csv"

    def piezo1_structure_detail(self, pdb_id: str) -> Path:
        return (self.vault / "data/piezo1/raw/piezo1_pdb_entries_detail"
                / f"{pdb_id}.json")

    @property
    def piezo1_compound_properties_csv(self) -> Path:
        return self.vault / "data/piezo1/compounds/piezo1_compounds_properties.csv"

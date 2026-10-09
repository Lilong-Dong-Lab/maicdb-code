# CLAUDE.md — maicdb-code

This file provides guidance to Claude Code when working in this repository.

## Repository Overview

**maicdb-code** is the executable-schema and tooling repo for **MAIC-DB**
(Mechanically Activated Ion Channel Database). The companion **vault repo**
`Lilong-Dong-Lab/Project_DataBase_MAICDB` is the curation/data authority;
this repo owns the formal schema (SQLAlchemy 2.0 ORM → SQLite), the loader,
and future query tooling. Data never lives here — it is loaded from the vault's
frozen corpus releases (currently tag **`data-v1.0`**, 1100 rows).

- Schema authority (doc side): vault `report/MAICDB_Schema_Design.md` (§4
  delegates column-level authority to `src/maicdb/models.py`).
- Loader mapping spec: `docs/loader-mapping.md`.
- Schema history: PR #1 (`schema-design`, merged 2026-09-01 after a retro
  independent gate — see vault `report/ReviewDigest_maicdb-code-pr1_2026-09-01_agent.md`).

## Commands

```bash
uv sync                      # install deps
uv pip install -e .          # editable install (REQUIRED before pytest in a fresh venv)
uv run pytest tests/ -q      # the test suite (64: schema + loader + query; vault/artifact-dependent tests auto-skip)
uv run maicdb-init-db --help     # create the DB from ORM metadata
uv run maicdb-dump-schema --help # render DDL
```

**Known env anomaly (root-caused 2026-09-02)**: the venv's `.pth` files can
carry the macOS BSD `hidden` flag (an external watcher re-applies it);
CPython 3.12's site.py skips UF_HIDDEN pth files → `import maicdb` fails.
Reliable heals: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth`,
or prefix commands with `PYTHONPATH=src`, or a wheel install. (`uv pip
install -e .` alone is NOT reliable — the flag comes back.)

## Git/PR workflow (same discipline as the vault)

1. `git checkout -b feat/<topic>` (or `fix/…`) from latest `main`.
2. Changes → `uv run pytest tests/ -q` green → commit → push → `gh pr create`.
3. **Independent review gate (mandatory before every merge)**: spawn a FRESH
   independent reviewer agent (no implementer context) with the PR diff, the
   reproduction commands, and the vault defect-register path
   (`report/PR10-30_Retrospective_Review_2026-08-26_agent.md` in the vault).
   - CLEAN → write the digest into the VAULT's `report/` as
     `ReviewDigest_maicdb-code-<topic>_<date>_agent.md` (the vault is the
     project's record home) via a small vault docs PR, then merge.
   - Any ≥ MINOR finding → fix on the branch, scoped re-review, then merge.
   - The digest must name the reviewed object (commits/diff range) and the
     reproduction commands, which the reviewer must have actually executed.
4. `gh pr merge --merge --delete-branch`; sync main after.
5. Stop and ask the user on: merge conflicts/failures, non-CLEAN reviews,
   anything touching data provenance semantics.

## Conventions

- stdlib + SQLAlchemy only beyond the existing dependency set; new deps need
  justification in the PR.
- Enums: `src/maicdb/enums.py` is the code-side vocabulary authority; the doc
  side lives in the vault's `data/extraction_schema.md` — change both together.
- Loader must be deterministic (byte-stable outputs given the same input tag)
  and strict where the spec says strict (unit enums, conservation asserts).
- Never fabricate test fixture values: fixtures claiming real-data provenance
  must cite the vault source in the docstring — CSV path / raw JSON for
  extracted cells, or (for pins against the published artifact) the
  data-notes section plus the census SQL that re-derives the number — the
  retro gate on PR #1 exists because of exactly this.

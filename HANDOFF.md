# HANDOFF — M1: `maicdb.query` library + CLI (2026-09-21)

> **For**: the agent implementing M1 in this repo (maicdb-code).
> **Authority**: vault `handoff.md` §4/§7 (landed 2026-09-21 via vault PR #71 —
> the strategic plan; read it first). This file translates its M1 milestone into
> an engineering brief.
> **Status when written**: this repo main `ee6ecdb` clean; `v1.0.0-data`
> artifacts published (tag `6327e50`); schema + loader complete and
> gate-verified; **no query layer exists yet — that is M1**.
>
> **M1 status: DONE (2026-10-09, branch `feat/query-library-m1`)** —
> `src/maicdb/query.py` (`open_readonly` / `channel_card` /
> `parameter_comparison` / `provenance` / `export`), CLI `maicdb-query`
> (channel / export / provenance), `tests/test_query.py` (15 tests, real-DB
> pins cited to data-notes §2/§6 and census SQL; DB-hash guard proves the
> artifact untouched). Both §2 example commands verified against
> `db/maicdb.sqlite`; `export --format csv` byte-identical across runs
> (disclosure on stderr). §5 edge cases covered: unknown gene → clean error
> listing the 12 computed genes; zero-row gene × parameter reported
> (PIEZO2/TRESK/ASIC thresholds `count=0`); PIEZO2 frozen wording asserted
> by field semantics. Transcript: README "Querying the Database".
> Post two-axis review (Standards CLEAN / Spec findings addressed):
> aggregate rows carry `measurement_ids` (rule-2 traceability), threshold
> outputs disclose the §6.1 sign convention, the no-verification walker
> asserts on the piezo cards themselves, and the channel query no longer
> emits an SAWarning (scalar_subquery).

## 1. Current state (verified 2026-09-21 — do not rebuild)

| Asset | Where | Notes |
|---|---|---|
| Published DB | `db/maicdb.sqlite` (tag `v1.0.0-data`) | schema 0.2.0 · 10 tables · 948+136+16 = **1100** rows · CC-BY-4.0 + schema_version in `db_meta` · 3,112,960 bytes |
| Byte-stable dump | `db/maicdb.sql` + `db/load-manifest.json` | reload-verified; manifest pins `vault_head 5a8ff0e` (regeneration `cmp` requires that vault state) |
| ORM | `src/maicdb/models.py` | SQLAlchemy 2.0, all 10 tables; `BiophysicsExperiment`/`Bioactivity` carry the per-row **evidence chain** (`measurement_id`, `evidence_quote`, location, `confidence`, `extractor_note`, `condition_key`, `n`) — and, on `BiophysicsExperiment` **only**, `value_as_reported`/`unit_as_reported` (`Bioactivity`'s as-recorded pair is `activity_value`/`activity_units`) |
| Engine / DDL | `src/maicdb/database.py` | `make_engine`/`create_all`/`render_ddl`; CLIs `maicdb-init-db`, `maicdb-dump-schema` |
| Loader | `src/maicdb/loader.py` | `maicdb-load` CLI; freeze contract (tag-ancestor + frozen-content diff) |
| Tests | `tests/` — **47 passed** | `PYTHONPATH=src uv run pytest tests/ -q` |
| Deps | `pyproject.toml` | `sqlalchemy>=2.0`, `pyyaml>=6`; dev `pytest`; hatchling; py ≥3.11 |

## 2. The M1 goal (vault handoff §4 + §7-M1)

**Build the query core as a library first.** `maicdb.query` — pure functions over
`db/maicdb.sqlite`. The CLI is its **first consumer, not the implementation**.
Website, API, and MCP server later wrap the same library — each interface stays
thin, zero reimplementation.

First-consumer targets (from the vault handoff, verbatim intent):

```
maicdb-query channel PIEZO1 --parameter p50
  → channel card: identity + P50 rows (as-recorded AND normalized values, units,
    sign convention) with per-row provenance (quote + location + confidence +
    extractor_note)
maicdb-query export --parameter tau_inact --format csv > out.csv
  → per-family/gene cross-comparison export (the numbers behind the A1 panels)
```

Minimum API surface (names indicative, shape is the contract):

- `channel_card(gene, parameters=None)` — identity + selected/every parameter block + evidence
- `parameter_comparison(parameter, ...)` — gene × parameter table (count/min/median/max, as-recorded preserved)
- `provenance(measurement_id)` — the full evidence row
- `export(..., format="csv"|"json")` — deterministic serialization

## 3. Binding design rules

1. **Read-only.** Open the DB with the `mode=ro` URI. The shipped artifact is
   never mutated; any derived cache is a separate file, disclosed. (A test
   asserts the DB file hash is unchanged by the whole query suite.)
2. **Evidence chain surfaced everywhere.** Every number printed must be
   traceable to its measurement row and verbatim quote — one-click provenance is
   the project's killer feature and the paper's differentiator.
3. **Frozen-layer wording rule (auto-fail elsewhere in this project):**
   PIEZO1/PIEZO2 evidence quotes are frozen-layer **unverified**. Never render
   "verified" for them; attach the §6.7 boilerplate (vault
   `MAICDB_data_notes.md`). Encode as a channel-set constant + a unit test that
   asserts the boilerplate is attached AND that no affirmative verification
   status is rendered for piezo rows (no `Verified` label, no
   `verification: verified` field — the boilerplate itself contains "not been
   re-verified", so test semantics, not substrings).
4. **No hardcoded data.** Gene lists, counts, gap disclosures — computed from
   SQL. (Drift lesson, twice-earned: the vault register's README/count-drift
   findings — F-002, F-013, F-030, F-051, F-070–F-073 — and the vault PR #69
   gate round, where hand-copied zero-gene lists were wrong in 7 panels.
   Computed lists pass gates.)
5. **Caliber discipline.** One row = one curated measurement. Aggregates =
   count/min/median/max with n printed; never inferential claims.
6. **Determinism.** Same input → byte-identical CLI output (no timestamps in
   stdout); tests assert it.
7. **Modality separation.** P50 (pressure) / T50 (tension) / X50 (indentation)
   are different physical quantities — never pooled or inter-converted;
   same-modality conversions only, disclosed and reversible (mirror the loader).

## 4. Suggested layout

- `src/maicdb/query.py` (grow into a `query/` package only when it earns it)
- CLI: `[project.scripts] maicdb-query = "maicdb.query:main"` (argparse,
  mirroring the existing three CLIs)
- `tests/test_query.py` extending the 47
- README section "Querying" with the two example commands

## 5. Acceptance criteria (M1 PR)

- Both example commands work from a clean checkout against `db/maicdb.sqlite`
- Edge cases tested: unknown gene (clean error); zero-row gene × parameter
  (**reported, not hidden** — e.g. PIEZO2 has no threshold rows of any modality);
  PIEZO2 frozen wording asserted
- `PYTHONPATH=src uv run pytest tests/ -q` green (47 + new)
- README + this HANDOFF updated ("M1 done", real command transcript)

## 6. Working discipline (this repo's CLAUDE.md — binding)

- branch → pytest green → PR → **fresh independent gate reviewer** (findings
  ≥ MINOR block; give it the diff, repro commands, and the vault defect
  register `report/PR10-30_Retrospective_Review_2026-08-26_agent.md`) →
  digest lands **in the vault** as
  `report/ReviewDigest_maicdb-code-<topic>_<date>_agent.md` via a small vault
  docs PR → **merge order: digest PR first, then this repo's PR** →
  `gh pr merge --merge --delete-branch`
- Env quirk: venv `.pth` files carry the macOS BSD `hidden` flag →
  `import maicdb` fails; heal with `chflags nohidden …site-packages/*.pth` or
  prefix `PYTHONPATH=src` (see `KNOWN-QUIRKS.md`)
- Cross-repo boundary: the vault is the curation/data authority; this repo
  never edits vault data; frozen layers `data/piezo1`, `data/piezo2` untouchable

## 7. Pointers

- **Strategic plan** (M1–M6, architecture rationale): vault `handoff.md`
- Column semantics + decided mappings: `docs/loader-mapping.md` (§6 all DECIDED)
- Data-caveats bible: vault `shared/assignments/data/MAICDB_data_notes.md`
  (§5 verification calibers · §6.3 small families · §6.7 frozen wording)
- Usage-example corpus (what users will actually ask — panels as query specs):
  vault `shared/assignments/submissions/xinfangowo/assignment-1/` (A1, PR #69;
  every panel script there is a validated SQL+presentation pattern)
- Project history: vault `record/progres_record.md` + `report/` digests

## 8. Out of scope for M1 (do not build)

Website (M3) · Zenodo DOI / public-repo + code-license decisions (M2 — user
decisions pending: MIT/Apache-2.0 vs current CC-BY-4.0) · MCP server / REST
(M4). Keep the library shaped so all of these can wrap it; build none of them.

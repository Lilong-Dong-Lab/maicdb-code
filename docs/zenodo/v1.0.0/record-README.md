# MAIC-DB — Mechanically Activated Ion Channel Database (data artifact v1.0.0)

MAIC-DB is a curated database of biophysical and bioactivity measurements on
mechanically activated ion channels, spanning **12 channel families**
(PIEZO1, PIEZO2, TRPV4, ASIC, MscS, MscL, OSCA, TMC, TRESK, TRAAK, TREK-1,
TREK-2). Every measurement row carries a full evidence chain: a verbatim
quote from its source, the location inside that source, a confidence rating,
and the extractor's note. Version 1.0.0 is the first published release
(data freeze 2026-09-01; schema 0.2.0).

## Files in this record

| File | Content |
|---|---|
| `maicdb.sqlite` | The database (schema 0.2.0, 10 tables) |
| `maicdb.sql` | Byte-stable SQL dump — two loads of the same frozen corpus are byte-identical under the pinned interpreter build (see the code repository's quirk register) |
| `load-manifest.json` | Row counts, load disclosures, source commit |
| `README.md` | This file |

## Contents

**1100 curated measurement rows** = 948 biophysics (incl. 130 gap-adjudicated
migrations; 105 pre-authorized unit conversions, as-reported originals
preserved) + 136 bioactivity + 16 unmapped (adjudicated-kept archive).
Dimensions: 211 publications, 12 channels, 12 PIEZO1 structures, 86 compounds,
125 variants, 6 external references.

## Using the data

The database is plain SQLite — no server, no install:

```bash
sqlite3 maicdb.sqlite
```

The schema, the deterministic loader, and a read-only query library (gene
cards, parameter aggregates, evidence provenance, CSV export) live in the
code repository: <https://github.com/Lilong-Dong-Lab/maicdb-code>.

## License

The data artifacts in this record are licensed **CC-BY-4.0**
([Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)),
as recorded in the artifact's `db_meta`. The code repository is licensed
separately under MIT.

## Citation

Cite this dataset with the DOI shown on this Zenodo page. Use the **version
DOI** to pin an analysis to exact data; use the **concept DOI** (always
resolving to the latest release) to cite MAIC-DB generically.

> Dong, L., & Li, T. (2026). *MAIC-DB: Mechanically Activated Ion Channel
> Database (data artifact v1.0.0)* (Version 1.0.0) [Data set]. Zenodo.

## Provenance

This artifact was built by the `maicdb-load` loader from the frozen curation
corpus (`data-v1.0`) of the MAIC-DB project. The dump is deterministic by
construction: regenerated from the same corpus state under the same pinned
interpreter build, it reproduces byte-identically. The regeneration command,
the interpreter pin, and every mapping decision are documented in the code
repository above. The loader run was verified through an independent, gated
code review.

## Contributorship & AI disclosure

MAIC-DB is a human-directed project with substantial agent-executed work.

- **Lilong Dong** — project direction and corpus curation
- **Taiheng Li** — curation and the cross-family usage example
- **Yujie Chen** — early data work, acknowledged with thanks

Much of the literature mining, code implementation, and review preparation
was executed by AI agents (Claude Code, Codex) under human direction. Every
merge passed an independent review gate: a fresh reviewer re-ran the
reproduction commands and could block the merge on any finding. Every
published number carries its per-row evidence chain, so it can be checked
against its source.

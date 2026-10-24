# Dataset DOI now via manual Zenodo upload; software DOI and public repo deferred to M3

At M2, Zenodo holds one record per **data release** containing the
byte-exact published artifact — `maicdb.sqlite`, `maicdb.sql`,
`load-manifest.json`, plus a short record README — licensed CC-BY-4.0,
with creators per ADR-0003. The record is created by **manual upload after
a sandbox.zenodo.org rehearsal**: the GitHub–Zenodo integration cannot see
this still-private repo, and an API-token path would put a live secret in
the session for no gain at a roughly annual release cadence. Zenodo record
metadata is effectively immutable once published; the rehearsal pass is
where creator name strings and the license field get verified before they
are baked into the DOI.

## Considered Options

- **Dataset DOI only, manual upload (chosen)** — the dataset is the object
  the paper cites; nothing any venue requires is missing.
- **Dataset + software DOIs at M2** — two ledgers to keep consistent from
  day one; no venue requires the software DOI.
- **One combined record** — conflates the citation targets and mixes two
  licenses inside one archive.
- **GitHub–Zenodo automation** — impossible while the repo is private; can
  be enabled at the M3 flip without cost.

## Consequences

- Zenodo version strings mirror the data tags: `v1.0.0-data` → "1.0.0";
  the next data release is `v1.1.0-data` → "1.1.0". The **concept DOI** is
  the generic citation target; the **version DOI** pins an analysis
  (GLOSSARY.md).
- `db_meta` of the published artifact is frozen — the DOI lands in the
  README, never retrofitted into `v1.0.0-data`. Future data releases record
  their DOI in `db_meta` at load time.
- The repo's public flip (and any software DOI) is an M3 gate with its own
  checklist: secret scan of full history, decision on internal docs
  (HANDOFF/CLAUDE/KNOWN-QUIRKS), visibility change.

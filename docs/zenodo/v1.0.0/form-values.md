# Zenodo record form values — MAIC-DB v1.0.0 (issue #17, ADR-0002)

Every field the Zenodo deposit form shows, with the **exact string to
enter**. Nothing is left to judgment at upload time. Field names follow the
current Zenodo deposit form (help.zenodo.org → Deposit → Describe records;
InvenioRDM). Where the sandbox form words a field differently, the *Value*
column still applies. **Any field not in this table: leave it at its
default (usually empty). Do not improvise.**

The title, creators, ORCIDs, license and version strings mirror
`CITATION.cff` (the canonical home, ADR-0003). The pins are enforced by
`tests/test_zenodo_bundle.py` — edit both files together.

## 1. Stage the bundle

```bash
bash scripts/stage-zenodo-bundle.sh
```

Extracts `maicdb.sqlite`, `maicdb.sql`, `load-manifest.json` from the
`v1.0.0-data` tag (never the working tree), adds the record README as
`README.md`, verifies every file byte-identical, and prints the checksum
table below. Upload the **four files** from `dist/zenodo-1.0.0/`.

## 2. Form values

| Field | Value | Notes |
|---|---|---|
| Resource type | `Dataset` | |
| Communities | *(leave empty)* | none curated; revisit later if wanted |
| DOI: does your upload already have a DOI? | `No` | Do **not** press "Get a DOI now" — a reserved DOI has nowhere to go (ADR-0002: the DOI never enters the frozen artifact; issue #18 captures it after publish) |
| Title | `MAIC-DB: Mechanically Activated Ion Channel Database (data artifact v1.0.0)` | mirrors `CITATION.cff` preferred-citation verbatim |
| Additional titles | *(leave empty)* | |
| Publication date | *(the publish day — keep the form default if you publish the same day you create the draft; if the draft sits for days, set the field to the actual publish day)* | The field means the day the record is first available on Zenodo. Don't backdate it to the GitHub release: data freeze 2026-09-01 (`db_meta`), GitHub release 2026-09-02, Zenodo date = Zenodo availability day |
| Creators | see table below | humans only (ADR-0003) |
| Description | see exact string below | plain text, paste as one block |
| Languages | *(leave empty)* | |
| Licenses and rights | `CC-BY-4.0` for **all four files** | data license only — no MIT anywhere in this record (code is not in the bundle; dual-license split is ADR-0001) |
| Keywords / subjects | `mechanobiology`, `ion-channels`, `bioinformatics`, `database` | mirror `CITATION.cff` keywords verbatim, hyphen included |
| Contributors | *(leave empty)* | Yujie Chen is acknowledged in the record README prose, not in metadata (ADR-0003) |
| Publisher | `Zenodo` | 2026-10-24 sandbox rehearsal: Save blocks with "Missing publisher field required for DOI registration" — and real Zenodo records render Zenodo as publisher anyway |
| Version | `1.0.0` | tag `v1.0.0-data` → version `1.0.0` (ADR-0002) |
| Related identifiers | `https://github.com/Lilong-Dong-Lab/maicdb-code` — scheme `URL` — relation `Is supplemented by` | the repo goes public at M3; the link 404s until then (expected) |
| Alternate identifiers | *(keep empty — if a row was added but left blank, delete the row; the artifact has no external identifiers yet)* | 2026-10-24 sandbox rehearsal: flagged on Save when an empty row sits in the list |
| References | *(leave empty)* | |
| Funding | *(leave empty)* | |
| Access right | `Open` | no embargo, no restrictions, no conditions of access |
| Files | `README.md`, `load-manifest.json`, `maicdb.sql`, `maicdb.sqlite` from `dist/zenodo-1.0.0/` | all Open, all CC-BY-4.0 |

### Creators (exactly two, in this order)

| # | Family name | Given name | Display | Affiliation | Identifier |
|---|---|---|---|---|---|
| 1 | `Dong` | `Lilong` | Dong, Lilong | *(none)* | ORCID `0000-0002-9519-3495` |
| 2 | `Li` | `Taiheng` | Li, Taiheng | *(none)* | ORCID `0009-0003-3806-9441` |

Enter each ORCID via the creator's identifier field (the form validates
ORCIDs and can search them). No roles. Affiliations stay empty by decision
(2026-10-24): the ORCID is the identity anchor; an affiliation inside the
immutable record would have to be defended forever.

### Description (exact string)

```
MAIC-DB (Mechanically Activated Ion Channel Database) is a curated database
of biophysical and bioactivity measurements on mechanically activated ion
channels, spanning 12 channel families (PIEZO1, PIEZO2, TRPV4, ASIC, MscS,
MscL, OSCA, TMC, TRESK, TRAAK, TREK-1, TREK-2). Version 1.0.0 contains 1100
curated measurement rows; every row carries a full evidence chain (verbatim
source quote, location, confidence rating). The database ships as a plain
SQLite file with a byte-stable SQL dump and the load manifest. Data
license: CC-BY-4.0. Schema, deterministic loader, and query tooling:
https://github.com/Lilong-Dong-Lab/maicdb-code
```

## 3. Checksums (cross-check after upload)

Regenerate with the staging script — never hand-edit. Compare against the
checksums Zenodo shows per file after upload.

| File | Bytes | SHA256 | MD5 |
|---|---|---|---|
| `README.md` | 3425 | `53f355b7fa23f00f55e14512daf40f07e6a213cd066c1fe89aba7c4a109276f9` | `f359170a5f85e30720b8a9f695b6ecc6` |
| `load-manifest.json` | 1171 | `4e441bf0aac8c46a016b3eaacb486099bf720cbf22fa44a35b78e290e87658a9` | `3600746be0ce35c2bf309650c21335c0` |
| `maicdb.sql` | 2176274 | `439841fc34b7820f6bf56eb32af1ca261e9c483c39778d5b14c9b0eb1326b712` | `51e7f1db2e12939da6672492f2d8185c` |
| `maicdb.sqlite` | 3112960 | `4bf4966e9fbf6b975a188b7e4c986d51ac2e959a246d1a4dc17027ef11521569` | `16940157c5a7b37b6d74ffbe120f056b` |

## 4. Sandbox rehearsal procedure (operator)

1. Log in at <https://sandbox.zenodo.org> (separate sandbox account; its
   contents are wiped periodically — that is the point).
2. New upload → fill the form per §2 → upload the four files from
   `dist/zenodo-1.0.0/`.
3. **Save draft**, then open the preview. Check the rendered record
   field-by-field against §5.
4. **Publish on the sandbox** (disposable) to see the final render and the
   auto-generated citation.
5. Any mismatch: write it into §6, fix the repo file, re-run the staging
   script (checksums change if the README changed), re-verify. Record
   metadata is effectively immutable once published for real (ADR-0002) —
   this pass is the safety net.

## 5. Rendered-record checklist

| # | Check | Where | Pass |
|---|---|---|---|
| 1 | Title renders exactly `MAIC-DB: Mechanically Activated Ion Channel Database (data artifact v1.0.0)` | record header | ☐ |
| 2 | Creators: `Dong, Lilong` then `Li, Taiheng`, in order | byline | ☐ |
| 3 | Each creator's ORCID shown as a validated link (`0000-0002-9519-3495`, `0009-0003-3806-9441`) | byline / creator popovers | ☐ |
| 4 | License badge `CC-BY-4.0` — may render under its full name "Creative Commons Attribution 4.0 International" (2026-10-24 rehearsal), which counts as a pass | sidebar + files list | ☐ |
| 5 | Version `1.0.0` | sidebar | ☐ |
| 6 | Resource type `Dataset` | sidebar | ☐ |
| 7 | Description renders as clean paragraphs; the repo URL is a **hyperlink** — after pasting the block, select the URL and use the editor's link (chain) button (2026-10-24 rehearsal: a pasted plain URL stays plain text) | description block | ☐ |
| 8 | Keywords: the four strings, hyphen in `ion-channels` kept | keywords | ☐ |
| 9 | Related identifier: repo URL, relation `Is supplemented by` | identifiers | ☐ |
| 10 | Four files; sizes and checksums match §3 | files | ☐ |
| 11 | Auto-citation reads `Dong, L., & Li, T. (2026). MAIC-DB: … (Version 1.0.0) [Data set]. Zenodo.` | citation box | ☐ |
| 12 | Nothing extra in the rendered record (no stray communities, contributors, funding) | whole page | ☐ |
| 13 | Publication date shows the actual publish day (not a stale draft date) | sidebar | ☐ |

## 6. Corrections found on the sandbox (fill during rehearsal)

| Field | Sandbox showed | Expected (§2) | Fix applied (file + commit) | Re-verified |
|---|---|---|---|---|
| 4. License badge CC-BY-4.0 | Creative Commons Attribution 4.0 International | CC-BY-4.0 | RESOLVED — not a defect: the badge renders the license's full name; §5 item 4 wording relaxed 2026-10-24 | ☐ |
| 7. Description renders as clean paragraphs; repo URL is a link | the repo URL is not a link | clean paragraphs + link | §2/§5 updated 2026-10-24: select the URL in the description editor and apply the link (chain) button on the real upload; plain text is the accepted fallback | ☐ |
| Publisher | sandbox Save error: "Missing publisher field required for DOI registration" | `Zenodo` | §2 Publisher row updated 2026-10-24 | ☐ |
| Alternate identifiers | sandbox Save error: "Missing data for required field (Identifier in alternate identifier)" — an added-but-empty row blocked validation | keep list empty; delete the empty row | §2 Alternate-identifiers row updated 2026-10-24 | ☐ |
| Items 1–9 (checklist A) | preview was BLOCKED by the two validation errors above — recorded as mismatches but not real field defects | — | re-verify every item after the preview renders | ☐ |
| 1. Title renders exactly: MAIC-DB: Mechanically Activated Ion Channel Database (data artifact v1.0.0) | Unable to display preview. Please correct validation issues inRecommended information 1Alternate identifiers 1 | MAIC-DB: Mechanically Activated Ion Channel Database (data artifact v1.0.0) | *(pending — fold back in a repo session)* | |
| 2. Creators 'Dong, Lilong' then 'Li, Taiheng', in order | "Missing publisher field required for DOI registration" and "Missing data for required field (Identifier in alternate identifier) | Dong, Lilong; Li, Taiheng | *(pending — fold back in a repo session)* | |
| 3. Both ORCID links shown: 0000-0002-9519-3495, 0009-0003-3806-9441 | as issues specified above, save and preview give these warnings. | two validated ORCID links | *(pending — fold back in a repo session)* | |
| 4. License badge CC-BY-4.0 | as above | CC-BY-4.0 | *(pending — fold back in a repo session)* | |
| 5. Version 1.0.0 | as Above | 1.0.0 | *(pending — fold back in a repo session)* | |
| 6. Resource type Dataset | as Above | Dataset | *(pending — fold back in a repo session)* | |
| 7. Description renders as clean paragraphs; repo URL is a link | as Above | clean paragraphs + link | *(pending — fold back in a repo session)* | |
| 8. Keywords: the four strings, hyphen in ion-channels kept | as Above | mechanobiology; ion-channels; bioinformatics; database | *(pending — fold back in a repo session)* | |
| 9. Related identifier: repo URL, relation 'Is supplemented by' | as Above | https://github.com/Lilong-Dong-Lab/maicdb-code (Is supplemented by) | *(pending — fold back in a repo session)* | |
| 10. Four files; sizes and checksums match §3 of form-values.md | can not preview in the last step | 4 files, checksums per §3 | *(pending — fold back in a repo session)* | |
| 12. Nothing extra rendered (no communities, contributors, funding) | can not preview in the last step | no extra sections | *(pending — fold back in a repo session)* | |
| 11. Auto-citation reads: Dong, L., & Li, T. (2026). MAIC-DB: … (Version 1.0.0) [Data set]. Zenodo. | stuck in the save and preview, missing key information in certain field. | Dong, L., & Li, T. (2026). MAIC-DB: … (Version 1.0.0) [Data set]. Zenodo. | *(pending — fold back in a repo session)* | |
| 13. Publication date shows the actual publish day | stuck in the save and preview, missing key information in certain field. | the publish day | *(pending — fold back in a repo session)* | |
| | | | | |

After the rehearsal is CLEAN, the real upload (zenodo.org, same values,
same bundle) is issue #18.

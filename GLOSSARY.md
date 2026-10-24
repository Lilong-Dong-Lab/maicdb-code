# MAIC-DB (maicdb-code)

The executable-schema and tooling repo for the Mechanically Activated Ion
Channel Database: formal schema, loader, query library, and the published
data artifacts. Its companion **vault** repo is the curation authority.

## Language

**Vault**:
The private companion repo (`Lilong-Dong-Lab/Project_DataBase_MAICDB`) that
is the curation and data authority: frozen corpus, scrape archives, project
records. It stays private even when this repo goes public.
_Avoid_: database repo, project repo

**Data artifact**:
The frozen, published file set built from a frozen corpus — `maicdb.sqlite`,
`maicdb.sql`, `load-manifest.json`. The citable object behind the dataset
DOI.
_Avoid_: database (ambiguous with the schema/code), dataset release

**Data release**:
A frozen corpus version published as a data artifact, named by a
`vX.Y.Z-data` tag in this repo and mirrored as a Zenodo dataset version
(e.g. `v1.0.0-data` → Zenodo version 1.0.0). The release unit of the data
axis; moves independently of the code version.
_Avoid_: release (ambiguous with code releases), drop

**Code version**:
The semver of the `maicdb` package in `pyproject.toml` — schema, loader,
query tooling. Moves independently of data releases.
_Avoid_: schema version (that is `schema_version` inside a data artifact)

**Concept DOI**:
The Zenodo DOI that always resolves to the latest data release. Cite this
for "MAIC-DB" generically.
_Avoid_: umbrella DOI, master DOI

**Version DOI**:
The Zenodo DOI pinned to one data release version. Cite this to make an
analysis reproducible against exact data.
_Avoid_: record DOI, per-release DOI

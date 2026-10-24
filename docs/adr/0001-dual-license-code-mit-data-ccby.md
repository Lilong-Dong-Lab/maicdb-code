# Dual license: MIT for code, CC-BY-4.0 for data

This repo ships two kinds of content with different reuse norms: the code
(schema, loader, query tooling) and the data artifacts in `db/`. We license
the code under **MIT** (copyright holder: Lilong-Dong-Lab) and keep the data
under **CC-BY-4.0** (recorded in `db_meta` since `v1.0.0-data`). CC licenses
are not designed for code — no source/binary distinction, discouraging to
forks — and the pre-M2 state contradicted itself three ways: an "Academic
Research" README badge (not a license), "academic research purposes" prose,
and CC-BY-4.0 in `pyproject.toml`.

## Considered Options

- **MIT (chosen)** — the permissive norm for scientific Python; one file, no
  notice machinery, zero friction for the M3 website and M4 MCP/REST
  wrappers.
- **Apache-2.0** — adds an explicit patent grant and NOTICE machinery; the
  defensive patent clause rarely matters for database tooling.
- **CC-BY-4.0 for everything** — one license, simplest story, but
  code-hostile and unconventional on PyPI.

## Consequences

- `LICENSE` file lands (MIT); `pyproject.toml` switches to MIT with the
  `License :: OSI Approved :: MIT License` classifier.
- Both READMEs (`README.md`, `README_CN.md`) carry a dual-license statement
  and an MIT badge; data files and any exported data stay CC-BY-4.0 with
  attribution.

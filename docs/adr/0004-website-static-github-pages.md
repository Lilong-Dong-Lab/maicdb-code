# M3 website: static output on GitHub Pages; no server runtime

The M3 website renders the published artifact — 1,100 rows, 3 MB of
SQLite — so the whole dataset ships to the browser and the site can be
fully static: prebuilt JSON + client-side search (vault `handoff.md` §5;
§10: "never build a hosted backend you can avoid"). The binding constraint
is the **build output: static files, no server runtime**. The build
toolchain is an implementation choice settled inside that constraint by
the M3 website spec (`docs/m3-website-spec.md` §3-Q1, PR #34: Python +
Jinja2 static build, vanilla JS, no framework, no Node toolchain) — this
ADR pins the constraint, the spec settles the implementation within it.
`maicdb.query` (Python) runs at build time in CI against the tagged
`db/maicdb.sqlite`; the website is another thin consumer of the same
library, like the CLI, with zero query reimplementation (spec §1).

Hosting on GitHub Pages follows from this repo being the public surface:
$0, deploys from GitHub Actions inside the existing PR → independent-
reviewer gate, no vendor accounts, and the site URL rides the M3 public
flip (ADR-0002, issue #19).

## Considered Options

- **Static output on GitHub Pages (chosen)** — $0; same repo, same review
  gate; Pages soft limits sit far above this site's scale.
- **Static output on Cloudflare (Pages or Workers static assets)** — the
  documented fallback host: official SSG guides exist for every candidate
  framework, and static-asset requests are free and unlimited. Loses only
  on adjacency: a vendor account, deploys outside the repo's gate. Pages
  is not deprecated — Cloudflare's record is convergence into Workers,
  with Pages maintained and no announced sunset (research note, F1.5–F1.6).
- **Server-rendered site (e.g. Next.js SSR on Vercel/Cloudflare)** — puts
  the queries at request time: either a TypeScript reimplementation of
  `maicdb.query` (two engines, drift) or an operated Python service.
  Contradicts the static-first posture, and no SSR benefit applies at
  1,100 rows: SSG covers findability, and the whole DB ships anyway.
- **Zenodo only, no website** — fails the audience matrix: the website is
  Must for the biologist/reviewer audience and carries the one-click
  provenance feature (vault `handoff.md` §6).

## Consequences

- CI regenerates the site's JSON from the tagged `db/maicdb.sqlite` —
  deterministic, PR-gated, never hand-edited (the README-transcript rule).
  The implementation is the spec's, not this ADR's: Q1 settles Python +
  Jinja2 → static HTML, vanilla JS, site code in `site/`, Jinja2 as the
  sole new (build-time) dependency. The spec's non-goals (§2: no
  server-side component; MCP/REST are M4) restate this ADR's constraint.
- Site publishing inherits the flip gate: the site renders the
  already-published artifact only, and the vault stays private
  (ADR-0002). Pre-submission publicity is intended for a resource paper,
  not incidental: the DOI is the priority stamp, and venues require a
  live public database at review time.
- **M4 REST option recorded**: FastAPI on Cloudflare Python Workers
  (GA 2026-09-21) can wrap `maicdb.query` directly — SQLAlchemy 2.0.48,
  pydantic 2.12.5, and pyyaml 6.0.3 ship in the Pyodide distribution, and
  the platform is the server (no uvicorn). Open risks before any M4 ADR:
  the 10 ms CPU/request free-plan limit against per-isolate SQLite
  loading (untested end-to-end), and no affirmative free-plan-for-Python
  statement in the docs (research note, claims 13–16).
- Evidence base: `docs/research/2026-11-02-cloudflare-ssg-and-fastapi-on-workers.md`
  — primary-source verification of Cloudflare SSG support and Python
  Workers capabilities, all sources accessed 2026-11-02.

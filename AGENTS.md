# AGENTS.md — maicdb-code

Entry point for coding agents on this repository. **CLAUDE.md is the
authority** — commands, the git/PR workflow, and the mandatory
independent review gate live there; **CODING_STANDARDS.md** carries
the four review rules every gate applies. Read both before your first
action in a session. This file stays a thin pointer plus the notes a
non-Claude harness needs most; if it ever disagrees with CLAUDE.md,
CLAUDE.md wins.

## Read order

1. `CLAUDE.md` — repo overview, commands, PR discipline, conventions
2. `CODING_STANDARDS.md` — the rules the review gate enforces
3. `docs/agents/` — issue-tracker ops, triage labels, domain docs,
   vault operations (read `docs/agents/vault-ops.md` before touching
   the vault repo)

## Harness-agnostic ground rules

- **Tests before any commit**: `PYTHONPATH=src uv run pytest tests/ -q`
  (expect `157 passed, 1 warning` locally, `150 passed, 7 skipped,
  1 warning` without the vault checkout). Suite pins in
  `.github/workflows/ci.yml` / `KNOWN-QUIRKS.md` quirk 3 are re-derived
  via `scripts/check-suite-matrix.sh`, never hand-edited.
- **Every change**: branch → suite green → PR → fresh independent
  review gate → vault digest → merge. No direct commits to `main`.
- **The repo is pre-public-flip** (issue #44 pending): development is
  private; treat everything as internal until the flip lands.

## Website (M3) specifics

- Sources: `site/templates/`, `site/assets/`,
  `site/strings.{en,zh}.json`, `site/zh-content.json`,
  `site/build.py`. Rebuild with
  `PYTHONPATH=src uv run python site/build.py`.
- **Never edit `site/_site/` or `site/_data/`** — build outputs,
  regenerated on every build, byte-stable by contract.

## Vault (data authority, private)

Checkout at `~/respository/Project_DataBase_MAICDB` (a **symlink** —
resolve it inside WSL with Linux tools; Windows-side 9P paths cannot
follow it). Data never lives in this repo. Cross-repo shell rule:
`git -C <path>`, never `;` across repo boundaries — see
`docs/agents/vault-ops.md`.

# M3 flip runbook — visibility flip pre-checklist (issue #19)

Runbook for flipping `Lilong-Dong-Lab/maicdb-code` public, executed when the
**M3 website milestone starts**. Prepared in advance per ADR-0002's
consequences ("the repo's public flip … is an M3 gate with its own
checklist"). Written 2026-10-27 as issue #19's agent-executable prep slice.

> **Gate — read first.** Sections 3–5 are **human-owned** and must NOT be
> executed before the M3 milestone starts (running the flip early would
> contradict ADR-0002). Public = cached, forked, indexed; the flip is
> effectively irreversible. Only §1 (secret scan) and the drafting of this
> document ran before the gate.

## 1. Secret scan (AC 1 — scan agent-executable; resolution needs sign-off)

Procedure, re-runnable at flip time:

```bash
uv run scripts/secret-scan.py          # exit 0 = CLEAN, exit 1 = FINDINGS
```

- Scans every unique text blob reachable from **all refs** (local +
  remote-tracking, so merged branch history is covered) plus every commit
  message. High-signal credential patterns only (AWS/GitHub/Slack/Google/HF/npm
  tokens, `sk-`-style keys, private-key blocks, JWTs, generic
  credential-assignment assignments); matched values are redacted in output.
- Binary blobs are skipped (counted and listed by path).
- Validated against a synthetic negative-control repo (2026-10-27): planted
  `ghp_…` / `AKIA…` / `api_key = "…"` / OPENSSH private-key header / `.env`
  filename — all detected, benign lines ignored.

**Scope caveat (accepted, not an omission):** binary blobs are not
content-scanned, and text blobs over 4 MiB are skipped — both are counted
and listed by path in the report. The only binary in history is
`db/maicdb.sqlite` — the published CC-BY data artifact, derived from the
vault corpus; it carries no credentials by construction. The scan also
covers only objects reachable
from refs: commits orphaned by force-push (e.g. still held on GitHub under
`refs/pull/*`) are not scanned — if history was ever force-pushed, check
those refs or accept the residual risk explicitly at flip time.

**If the flip-time run reports findings:** stop. Resolution means history
rewriting — explicit maintainer sign-off territory (issue #19 out-of-scope
line). Do not flip with unresolved findings.

**Recorded result 2026-10-27 (at main `669928e`, 80 commits, 32 refs):**
CLEAN — 186 text blobs scanned, 0 content findings, 0 filename flags,
1 binary blob skipped (`db/maicdb.sqlite`). The flip-time re-run supersedes
this record. Expected difference at flip time: the re-run will list **1
advisory filename flag — `scripts/secret-scan.py` itself** (it matches the
scanner's own `^secret` path flag; the 2026-10-27 record predates the
script). Advisory only — the gate is the exit code, which stays 0.

## 2. Internal-doc decisions (AC 2 — human)

Decision per doc: **stay tracked-and-public** (no action; the public surface
includes it) **vs relocate** to the vault (`git rm` here + one-line pointer
to the vault counterpart, via a vault docs PR — the vault is the project's
record home). Before any `git rm`: `rg '<filename>'` for inbound references
and update them in the same PR.

| Doc | Contents (facts only, no call made) | Decision |
|---|---|---|
| `HANDOFF.md` (148 lines) | Milestone engineering briefs + status narrative (M1 done); cites vault reports, PR numbers, agent digests. Scan CLEAN. | ☐ stay ☐ relocate |
| `CLAUDE.md` (95 lines) | Agent operating manual: commands, PR/review discipline, env-anomaly heal. Scan CLEAN. | ☐ stay ☐ relocate |
| `KNOWN-QUIRKS.md` (19 lines) | Env/interpreter quirk registry; references the vault sibling registry. Scan CLEAN. | ☐ stay ☐ relocate |

## 3. The flip (AC 3 — human; explicit approval required)

1. Re-run §1 → `RESULT: CLEAN` (exit 0). Stop on findings.
2. Every §2 row decided and executed; table fully checked.
3. Flip visibility: GitHub web — Settings → General → Danger Zone →
   **Change visibility** → Public (type the repo name to confirm). CLI
   alternative: `gh repo edit Lilong-Dong-Lab/maicdb-code --visibility
   public` (needs admin).
4. Post-flip spot-checks:
   - Unauthenticated: `gh api repos/Lilong-Dong-Lab/maicdb-code --jq .private`
     → `false`; README renders in an incognito browser.
   - No vault *content* leaks: the vault repo stays private; textual
     vault-path references in docs are expected and fine.
   - Actions tab: workflows run publicly; no secret-bearing logs.
   - Issues/PRs and `CITATION.cff` render as intended public surface.

## 4. GitHub–Zenodo software archive (AC 4 — human; enable or explicitly decline)

- **Enable:** zenodo.org → sign in → **GitHub** section → enable
  `maicdb-code` → each future tagged release gets a draft software-DOI
  record. Note (ADR-0002): the *dataset* citation path stays the manual
  Zenodo record (concept DOI + version DOIs, `scripts/stage-zenodo-bundle.sh`,
  `docs/zenodo/v1.0.0/`); a software DOI is additive, not a replacement.
  Possible follow-up (its own decision): backfill the software DOI into
  `CITATION.cff` at the next release.
- **Decline:** record one-line reason on issue #19 (ADR-0002 already accepted
  the manual path at the roughly annual release cadence).
- Either way: record the decision on issue #19.

## 5. Close-out

- Check off the AC boxes on issue #19 (§1→AC 1, §2→AC 2, §3→AC 3, §4→AC 4).
- If any code changed since the prep-slice PR, follow the repo's independent
  review gate before merging (CLAUDE.md workflow step 3).

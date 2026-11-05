# Review Digest template

The vault's `report/ReviewDigest_maicdb-code-<topic>_<date>_agent.md` is
the standing record of every gate (CLAUDE.md workflow step 3; land via the
digest PR recipe in `vault-ops.md`). Fill every section; delete nothing.

```markdown
# Review Digest — maicdb-code PR #<n> (<short title>)

- **Reviewed object**: PR #<n> `<title>`. Commits: `<sha>` (<one-line role>)
  · ... Final head `<sha>`; CI green (run <id>).
- **Gate**: fresh independent reviewer agent (no implementer context),
  <N> round(s). [If respawns/stalls happened: what, why, and the fix.]
- **Reproduction commands executed by the reviewer**: <the commands, not
  the ones the author ran — trimmed outputs; every pinned number the
  reviewer re-derived>

## Round 1 (head `<sha>`) — <verdict with counts>

- **<RATING>**: <finding in one sentence> — <fix commit + how>. [Repeat
  per finding. Numbers the reviewer verified exact deserve one line: the
  fidelity record is the digest's reason to exist.]

## Round 2 (delta `<sha>..<sha>`) — <verdict>

[Scoped-delta verification summary; state what was re-run vs waived and
why.]

## Pin record

[If signatures moved: old→new per state, derived by execution via
scripts/derive-pins-clean.sh, static-check OK per commit.]

## Verdict

**CLEAN** (round <N>, head `<sha>`). Merge <approved by / per policy> after
this digest lands.

## Context

[One paragraph: what this PR is in the project's arc; anything a future
reader needs that the rounds don't carry. Disclosures the PR body carried
(e.g. a process correction) repeat here for durability — PR bodies are
ephemeral surfaces.]
```

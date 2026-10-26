# CODING_STANDARDS — maicdb-code

Read by the independent review gate on every PR. Only judgement calls live
here — anything a deterministic check can enforce belongs in a script, test,
or CI job instead (born 2026-10-25, retro on PRs #21/#22; both rules below
are fixes for mistakes the gates actually caught).

## 1. Doc pins anchor to structure

Values an operator copies into an immutable surface (Zenodo form fields,
DOI backfills, release notes) are pinned in tests to their designated table
cell or field — via a cell-anchored helper — never by a bare substring
`in doc` assertion.

*Failure prevented:* a corrupted cell passes while its string survives
elsewhere in the doc. Observed 2026-10-24: corrupted §2 Version / License /
creator-name cells all passed substring assertions with the suite green;
the suite's own purpose ("nothing improvised on the form") was defeated.

*Reviewer drill:* for each new doc-pin assertion, ask which cell or field
it is bound to; a substring assertion on a tabular doc is a finding.

## 2. Fix claims diff against the change

Every "updated X" claim in a fix commit message, ledger cell, or PR body
must be locatable in that fix's diff. Write the fix description from the
diff, not from the intention.

*Failure prevented:* a §6 ledger cell claimed "§2/§5 updated" while the
diff touched only §5 — the operator's fill script stayed wrong under a
green suite (observed, PR #22 gate).

*Reviewer drill:* for each fix, list its claims, then point at the hunk
that satisfies each; an unpointed claim is a finding. Machine-output
lines in a commit message, PR body, or digest (diff stats, suite
summaries, command output) are pasted from a re-run of the command — a
retyped summary is a finding (four strikes: PR #22 ledger cell, PR #83
jq restyle, PR #24 stat glyphs, PR #26 body stat).

*Mechanical subset:* stat-shaped lines (``N files changed, X insertions(+),
Y deletions(-)`` and the compact ``N files +X/-Y``) are machine-checked in
CI — the stat-lines step re-derives the whole-diff and per-commit stats
and fails on any pasted line that matches neither. Only the PR's own
stats verify: a historical or sub-range stat line matches no re-derivation
and fails the step, so don't paste those. The reviewer drill therefore
targets every other claim shape; paste stat lines unwrapped.

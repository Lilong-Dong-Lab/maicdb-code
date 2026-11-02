# CODING_STANDARDS — maicdb-code

Read by the independent review gate on every PR. Only judgement calls live
here — anything a deterministic check can enforce belongs in a script, test,
or CI job instead (born 2026-10-25, retro on PRs #21/#22; the rules below
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
and fails the step, so don't paste those. Paste **per-commit** stats, not
the whole-diff stat: a commit is immutable so its stat re-derives forever,
while a whole-diff stat is born historical — it expires the moment the
branch gains another push (observed live, PR #48: two gate-fix pushes
after the body's whole-diff stat pasted → every later pull_request run
red on a line the CI could no longer re-derive; the merge push run was
green only because the step is pull_request-only). Exception: a
single-commit PR may paste its whole-diff stat — it equals that one
commit's stat, which re-derives forever. The reviewer drill therefore
targets every other claim shape; paste stat lines unwrapped.

## 3. Docstring/PR-body behavioral claims point into the implementation

Every behavioral claim a diff ships — a module docstring's output list, a
source citation ("taken from X, which is written in Y"), a CLI default, a
cross-file consistency statement ("matches spec §6") — is individually
pointable in the implementation of that same diff. Write the docstring
from the code, not from the plan.

*Failure prevented:* five gate findings across two PRs were all this
class, none caught by rules 1–2 — PR #34: EN wording residue the CN twin
had fixed, a column name standing in for a registry name, a false claim
about the data-notes language; PR #46: a build docstring listing files
the build never writes. A T3 consumer reading any of those claims as a
contract builds on fiction.

*Reviewer drill:* for each new/changed docstring or PR-body claim about
behavior, point at the line that makes it true — the output list entry at
its `_dump`/write site, the citation at the cited source itself, the
default at the `add_argument`. An unpointable claim, or a claim the twin
surface (EN/CN, docstring/spec) contradicts, is a finding.

## 4. Guard tests ship with escape-form self-vectors

A guard test — a scanner, a literal collector, any test whose pass
depends on NOT seeing something — lands in the same diff with self-test
vectors that go red on known escape forms. The reviewer then names one
more escape form and asks whether a vector pins it.

*Failure prevented:* the site's template-literal scan passed itself
while `{{ "…" }}` expression literals and `{%- … -%}` whitespace-control
tags both escaped it — each found only by a successive adversarial gate
round on PR #48 (2026-11-02), after the implementation-side review had
already accepted the scanner as complete. A guard with no negative
vector proves only that the guarded surface is quiet, not that the guard
bites.

*Reviewer drill:* for each new guard test, run its collector directly on
a known-escape input and watch it fail; then name a second escape form
and check whether a self-vector pins it — if none does, that is a
finding.

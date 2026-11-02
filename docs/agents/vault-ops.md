# Vault operations — clone layout, digest PRs, cross-repo shell discipline

How this machine touches the vault (`Lilong-Dong-Lab/Project_DataBase_MAICDB`) from
maicdb-code work: where the checkout lives, how review digests land as vault PRs
without disturbing it, and the shell rules that prevent multi-repo mistakes.

## Clone layout (this machine, verified 2026-11-02)

| Path | What it is |
|---|---|
| `~/Project_DataBase_MAICDB` | The user's own checkout — may sit on a **personal working branch** (e.g. `student/xinfangowo-a2`). Never switch, rebase, or otherwise move its HEAD; run `git fetch --prune` freely |
| `~/respository/Project_DataBase_MAICDB` | **Symlink** to the checkout above — the sibling path `tests/test_loader.py` and the loader expect (`parents[2]/Project_DataBase_MAICDB`). Freeze contract verified through it: `data-v1.0` (`5a8ff0e`) is an ancestor of the checked-out HEAD, so vault-dependent tests run for real (local suite = 100 passed, 0 skipped) |

If the symlink is missing, recreate it — do not re-clone (a full clone is
~58 MB and the network path to GitHub for this repo is slow; the 2026-11-02
re-clone attempt was abandoned at 55 MB when the existing checkout was found).

## Digest PR recipe (workflow step 3's "small vault docs PR")

Never commit on the user's checkout. Use a throwaway **worktree** off local
`main` (kept fast-forwarded via `git fetch . origin/main:main` when needed):

```bash
git -C ~/Project_DataBase_MAICDB worktree add -b docs/reviewdigest-maicdb-<topic> /tmp/vault-wt-<topic> main
# write report/ReviewDigest_maicdb-code-<topic>_<date>_agent.md
git -C /tmp/vault-wt-<topic> add … && git -C /tmp/vault-wt-<topic> commit -m "…"
git -C /tmp/vault-wt-<topic> push -u origin docs/reviewdigest-maicdb-<topic>
gh pr create --repo Lilong-Dong-Lab/Project_DataBase_MAICDB --base main --head docs/reviewdigest-maicdb-<topic> …
gh pr merge <n> --repo Lilong-Dong-Lab/Project_DataBase_MAICDB --merge --delete-branch
git -C ~/Project_DataBase_MAICDB worktree remove /tmp/vault-wt-<topic>
```

Merge order (binding): **digest PR first, then the maicdb-code PR**. Two
`gh` gotchas seen live: `gh pr create --repo <vault>` run from inside the
maicdb-code clone resolves the head branch from the *local* checkout — pass
`--base`/`--head` explicitly (or `cd` into the worktree); `/tmp` is not
durable — create the worktree fresh each time, never assume yesterday's
`/tmp` clone still exists.

## Cross-repo shell discipline (binding)

Commands touching the vault from a maicdb-code shell session (or vice versa):

- Prefer `git -C <path> …` over `cd`.
- If you must `cd`, chain the whole compound with `&&` so a failed `cd`
  short-circuits everything after it.
- **Never join cross-repo commands with `;`** — `;` ignores the failure and
  the tail of the command runs in the *wrong repository*. Observed
  2026-11-02: `cd /tmp/<gone-dir> && git fetch … ; git checkout -b …` created
  a stray branch in maicdb-code because the `cd` failed into the wrong cwd.

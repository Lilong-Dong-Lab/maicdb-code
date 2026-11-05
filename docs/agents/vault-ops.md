# Vault operations — clone layout, digest PRs, cross-repo shell discipline

How this machine touches the vault (`Lilong-Dong-Lab/Project_DataBase_MAICDB`) from
maicdb-code work: where the checkout lives, how review digests land as vault PRs
without disturbing it, and the shell rules that prevent multi-repo mistakes.

## Clone layout (this machine, verified 2026-11-05; supersedes the 2026-11-02 table — the `~/Project_DataBase_MAICDB` and `~/respository/` paths are gone)

| Path | What it is |
|---|---|
| `~/Documents/AcademicWorkplace/02_RESEARCH_LABORATORY/Active_Projects/Project_DataBase_MAICDB` | The user's own checkout — may sit on main or a work branch (e.g. `student/xinfangowo-a2`). Never switch, rebase, or otherwise move its HEAD; run `git fetch --prune` freely |
| `/tmp/Project_DataBase_MAICDB` | Optional **symlink** to the checkout above — the sibling path `tests/test_loader.py` resolves (`parents[2]/Project_DataBase_MAICDB`); needed only for worktree-based runs (clean-tree derives; see `scripts/derive-pins-clean.sh`, which creates it). The main checkout sits beside this repo, so in-place runs resolve the sibling naturally |

## Digest PR recipe (workflow step 3's "small vault docs PR")

Never commit on the user's checkout. Use a throwaway **worktree** off local
`main`. Set the checkout path once per shell (the clone-layout table above
is the authority):

```bash
VAULT="$HOME/Documents/AcademicWorkplace/02_RESEARCH_LABORATORY/Active_Projects/Project_DataBase_MAICDB"
```

Fast-forward main with BOTH steps — `git fetch . origin/main:main`
alone only catches up to the local `origin/main` tracking ref, which itself
stays stale until fetched from the remote (the 2026-11-02 M3-T5 digest round
built a worktree three digest PRs behind on exactly this, then paid a
rebuild + branch-name collision to recover):

```bash
git -C "$VAULT" fetch origin --prune
git -C "$VAULT" fetch . origin/main:main
```

```bash
git -C "$VAULT" worktree add -b docs/reviewdigest-maicdb-<topic> /tmp/vault-wt-<topic> main
# write report/ReviewDigest_maicdb-code-<topic>_<date>_agent.md
git -C /tmp/vault-wt-<topic> add … && git -C /tmp/vault-wt-<topic> commit -m "…"
git -C /tmp/vault-wt-<topic> push -u origin docs/reviewdigest-maicdb-<topic>
gh pr create --repo Lilong-Dong-Lab/Project_DataBase_MAICDB --base main --head docs/reviewdigest-maicdb-<topic> …
gh pr merge <n> --repo Lilong-Dong-Lab/Project_DataBase_MAICDB --merge --delete-branch
git -C "$VAULT" worktree remove /tmp/vault-wt-<topic>
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

## GUI auto-sync danger + the 2026-11-03 incident restore path

A GUI git integration (Obsidian's git plugin, VS Code's sync, any client
with auto-pull) is a bypass around the "never move its HEAD" rule above.
Observed 2026-11-03 09:46: a GUI auto-sync ran `git checkout main` +
`pull --ff-only` on the user's checkout, which sat on a work branch whose
tree TRACKS `data/` (main tracks only `report/`) — git deleted every
"tracked-in-branch, absent-in-main" file on switch, and the suite's
vault-dependent tests silently skipped behind a green suite for ~24h
(the silent-skip hole is since closed by
`tests/test_loader.py::test_vault_checkout_mangled_goes_red_not_silent_skip`).

**Prevention**: disable auto pull/checkout on the vault in every GUI git
plugin you run; treat any "sync" button over the vault as a branch switch
first, fetch second.

**Health check** (one line, run when anything feels off):

    ls "$VAULT/data/" | wc -l    # expect 15 (12 channels + db + 2 schema docs)

**Restore path** if mangled (as executed 2026-11-04):

1. `git -C "$VAULT" reflog --date=iso | head` — find the
   last pre-incident tip on your work branch (the `checkout: moving from
   <branch> to main` line names it).
2. Rebuild the branch if it was also deleted: `git branch <branch> <tip>`;
   untracked working-tree files conflicting with the checkout are the
   tag/branch-tracked copies — back them up (`tar -C … -cf /tmp/… -T <list>`),
   remove, then `git checkout <branch>` brings the tracked set back intact.
3. Path quirks when scripting the cleanup: `git -c core.quotepath=false`
   for CJK paths; `xargs -d '\n'` for paths with spaces.
4. The `data-v1.0` tag carries the full frozen corpus as a last-resort
   source, but prefer the branch (it may hold post-freeze work); push the
   restored branch (`git push -u origin <branch>`) so the next incident
   cannot lose it to reflog expiry.

#!/bin/sh
# PreToolUse (Bash) guard — blocks `git checkout <paths>` /
# `git checkout -- <paths>` / `git checkout <tree-ish> -- <paths>` /
# `git restore <paths>` / `git switch --discard-changes` when the target
# paths carry uncommitted (staged or unstaged) changes, and any
# force-switch (`git checkout -f`) while the tree is dirty. All of these
# silently destroy uncommitted work; found live 2026-10-26: a probe
# reverted via `git checkout <file>` wiped the file's unrelated uncommitted
# edits (three hunks of a new test) along with the probe.
# Installed via .claude/settings.json (PreToolUse, matcher Bash).
# Semantics notes:
#   - Command-position matching only (line start or after ; && || | ( ) /
#     newline), so a prose mention inside a commit message does not trip
#     the guard — same lesson as block-chained-pr-merge.sh (2026-10-26).
#   - git global-option prefixes are skipped before the subcommand match,
#     else `git -C <dir> checkout -- f` classifies as `-C` and never fires
#     (gate MINOR, PR #30). The risk oracle (git status) runs in the
#     hook's own cwd: a -C target at a DIFFERENT repo than the hook's cwd
#     fails open — accepted; the hazard this guard exists for is work in
#     the session's own repo.
#   - A bare `git checkout <ref>` is a branch switch: git refuses or
#     carries changes, never discards — allowed unless -f/--force.
#   - `git status --porcelain --untracked-files=no` is the risk oracle:
#     checkout/restore never touch untracked files.
#   - Tokens are word-split (quotes lost); paths with spaces may evade or
#     misfire the guard. Known imprecision, accepted — the guard is a
#     seatbelt, not a parser.
#   - macOS /bin/bash is 3.2, whose parser rejects `case` inside `$()`;
#     the candidate loop therefore writes a temp file instead of capturing
#     a pipeline (bash-3.2-parse lesson, found live 2026-10-26).
command -v jq >/dev/null 2>&1 || {
    echo "hook: jq not found — checkout-discard guard inactive (install jq)" >&2
    exit 0
}
cmd=$(jq -r '.tool_input.command // empty')
[ -n "$cmd" ] || exit 0

CANDS=$(mktemp "${TMPDIR:-/tmp}/maicdb-checkout-guard.XXXXXX") || exit 0
trap 'rm -f "$CANDS"' EXIT

dirty_in() { # pathspec... -> non-empty if tracked changes touch it
    [ -n "$(git status --porcelain --untracked-files=no -- "$@" 2>/dev/null)" ]
}
tree_dirty() { [ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]; }

# Normalize shell separators to newlines so each line starts at a real
# command position (&& -> ; first: BSD sed will not emit \n in a RHS).
# Then inspect lines led by a guarded subcommand; emit "subcmd paths..."
# for every invocation that names a pathspec or force/discard-switches.
printf '%s\n' "$cmd" | sed 's/&&/;/g' | tr ';|()' '\n\n\n\n' |
while IFS= read -r line; do
    set -- $line
    [ "$#" -ge 2 ] || continue
    [ "$1" = "git" ] || continue
    shift
    # Skip git global-option prefixes; value-taking opts consume their
    # argument (`git -C <dir> checkout -- f` must classify by subcommand).
    while [ "$#" -gt 0 ]; do
        case $1 in
            -C|-c|--git-dir|--work-tree|--namespace|--super-prefix)
                if [ "$#" -ge 2 ]; then shift 2; else break; fi ;;
            -*) shift ;;
            *) break ;;
        esac
    done
    [ "$#" -ge 2 ] || continue
    case $1 in
        checkout|restore|switch) subcmd=$1 ;;
        *) continue ;;
    esac
    shift
    after_dd=0; force=0; discard=0; paths=""
    for tok in "$@"; do
        if [ "$tok" = "--" ]; then after_dd=1; continue; fi
        case $tok in
            -*) case $tok in
                    -f|--force) force=1 ;;
                    --discard-changes) discard=1 ;;
                esac
                [ "$after_dd" -eq 1 ] && paths="$paths $tok" ;;
            *)  if [ "$after_dd" -eq 1 ] || [ "$subcmd" = "restore" ]; then
                    paths="$paths $tok"
                elif [ -e "$tok" ] &&
                     ! git rev-parse --verify --quiet "$tok" >/dev/null 2>&1;
                then
                    paths="$paths $tok"
                fi ;;
        esac
    done
    if [ -n "$paths" ] ||
        { [ "$subcmd" != restore ] && { [ "$force" -eq 1 ] || [ "$discard" -eq 1 ]; }; }
    then
        printf '%s %s\n' "$subcmd" "$paths"
    fi
done > "$CANDS"

RISKY=""
while IFS= read -r cand; do
    set -- $cand
    subcmd=$1; shift
    if [ -n "$1" ]; then
        dirty_in "$@" && RISKY="$cand"
    elif tree_dirty; then
        RISKY="$cand"
    fi
    [ -z "$RISKY" ] || break
done < "$CANDS"

if [ -n "$RISKY" ]; then
    echo "Blocked: '$RISKY' would discard uncommitted changes." >&2
    echo "Undo a probe by reverse edit; set work aside with 'git stash push -- <paths>'; or commit first." >&2
    exit 2
fi
exit 0

#!/bin/sh
# PreToolUse (Bash) guard — blocks chaining `gh pr create` and `gh pr merge`
# into ONE Bash command. Chained create+merge skips human review of the PR;
# the auto-mode classifier then denies it mid-sequence (2026-10-24 #21/#81,
# #22/#82; 2026-10-26 #26/#88 — third instance, retro finding).
# The fix is procedural: create the PR, merge it as its own approved command.
# Installed via .claude/settings.json (PreToolUse, matcher Bash).
cmd=$(jq -r '.tool_input.command // empty')
# Match command-position occurrences only (line start or after a shell
# separator), so a quoted/prose mention of either phrase — e.g. inside a
# commit message argument — does not trip the guard (found live 2026-10-26:
# the first version blocked a commit whose MESSAGE described the hook).
if printf '%s\n' "$cmd" | grep -qE '(^|[;&|(] *)gh pr create' && printf '%s\n' "$cmd" | grep -qE '(^|[;&|(] *)gh pr merge'; then
  echo "Blocked: this single command contains both 'gh pr create' and 'gh pr merge'." >&2
  echo "Run them as separate commands — the PR must exist for review before a merge command runs (repo retro 2026-10-26)." >&2
  exit 2
fi
exit 0

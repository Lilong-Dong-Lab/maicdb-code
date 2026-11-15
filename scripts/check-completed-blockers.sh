#!/usr/bin/env sh
# check-completed-blockers.sh — list closed-COMPLETED issues that still have
# an OPEN blocker (GitHub native dependencies). A completed ticket with a
# live blocker means the record diverged from the work: either the blocker
# is stale-open (its work already happened — close it with an evidence
# record) or the completion was premature. Exit 1 on findings, 0 when clean.
#
# Rationale: retro 2026-11-15 — #45 (T9 deploy) closed COMPLETED 2026-11-07
# while its blocker #44 (T8 PUBLIC FLIP) sat open with zero execution record
# until a manual status sweep on 2026-11-15. `issue_dependencies_summary
# .blocked_by` counts OPEN blockers only — exactly this anomaly's signal.
# (The edge is native: #45 reports total_blocked_by=3, #44 among them; at
# any point in 2026-11-07..15 the summary read blocked_by=1 → this audit
# fails on that state.)
#
# Usage:   scripts/check-completed-blockers.sh [limit]   (default: the 50
#          most recently updated closed issues; limit capped at 100 by the
#          REST API)
# Note:    closed-not-planned issues (wontfix/duplicate) are exempt — an
#          abandoned ticket may legitimately keep open blockers.
#          Findings print the blocker count; name the blockers with:
#          gh api "repos/<o>/<r>/issues/<n>/dependencies/blocked_by"
set -eu

limit="${1:-50}"
[ "$limit" -eq "$limit" ] 2>/dev/null || limit=50
[ "$limit" -gt 100 ] && limit=100

out=$(gh api "repos/Lilong-Dong-Lab/maicdb-code/issues?state=closed&per_page=$limit&sort=updated&direction=desc" --jq '
    .[]
    | select(.pull_request == null)
    | select(.state_reason == "completed")
    | select(.issue_dependencies_summary.blocked_by > 0)
    | "#\(.number)  \(.issue_dependencies_summary.blocked_by) open blocker(s)  \(.title)"')

if [ -n "$out" ]; then
  printf '%s\n' "$out"
  echo ""
  echo "FAIL: completed issues with an open blocker — close the stale blocker"
  echo "with its evidence record, or reopen the premature completion"
  echo "(docs/agents/issue-tracker.md)."
  exit 1
fi
echo "OK: no completed issue among the $limit most recently updated closed issues has an open blocker."

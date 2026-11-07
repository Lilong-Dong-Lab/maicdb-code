#!/usr/bin/env sh
# check-closed-ac.sh — list CLOSED issues whose bodies still contain unticked
# AC checkboxes (`- [ ]`). Exit 1 on findings (audit gate), 0 when clean.
#
# Rationale: retro 2026-11-07 — issue #19 sat closed-COMPLETED for 10 days with
# all four AC boxes unticked (docs/agents/issue-tracker.md "Closing an
# AC-carrying issue"). Run at close-outs, or whenever the tracker's record
# integrity is in question.
#
# Usage:   scripts/check-closed-ac.sh [limit]     (default: last 50 closed)
# Note:    closed-as-duplicate / wontfix tickets should carry a pointer
#          comment per the issue-tracker rule; if they legitimately retain
#          unticked boxes, fix the body, not this script.
set -eu

limit="${1:-50}"

out=$(gh issue list --state closed --limit "$limit" \
  --json number,title,body --jq '
    .[] | select(.body != null)
    | {number, title, unticked: ([.body | scan("- \\[ \\]")] | length)}
    | select(.unticked > 0)
    | "#\(.number)  \(.unticked) unticked  \(.title)"')

if [ -n "$out" ]; then
  printf '%s\n' "$out"
  echo ""
  echo "FAIL: closed issues with unticked AC boxes — tick the boxes or point"
  echo "each at its evidence (docs/agents/issue-tracker.md)."
  exit 1
fi
echo "OK: no closed issue in the last $limit carries an unticked AC box."

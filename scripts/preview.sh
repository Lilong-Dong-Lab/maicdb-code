#!/usr/bin/env bash
# MAIC-DB site one-command background preview: rebuild + http.server,
# idempotent (a live port is reused, not rebuilt).
#
# Usage:  bash scripts/preview.sh [port]     # default 8000
#
# Behavior:
#   * port already serving a preview → reuse it (no rebuild), exit 0
#   * otherwise → rebuild site/_site from the current worktree's sources
#     → nohup python3 -m http.server in the background → readiness probe
#     → print URL / pid / log / stop line
#
# Stop:    kill <printed pid>   (or pkill -f 'http.server 8000')
# Rebuild: with a preview running, stop it and re-run this script (or
#          rebuild manually with PYTHONPATH=src uv run python
#          site/build.py and refresh the browser).
set -euo pipefail

PORT="${1:-8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="/tmp/maicdb-preview-$PORT.log"

# Idempotent branch: a live port is reused (the tests lock that this
# branch never rebuilds).
if curl -sf -o /dev/null "http://localhost:$PORT/"; then
  echo "preview already running: http://localhost:$PORT/ (reusing the existing process, not rebuilt)"
  exit 0
fi

echo "Rebuilding the site (current worktree sources)..."
(cd "$ROOT" && PYTHONPATH=src uv run python site/build.py >/dev/null)

echo "Starting http.server in the background (port $PORT)..."
cd "$ROOT/site/_site"
nohup python3 -m http.server "$PORT" >"$LOG" 2>&1 &
SERVER_PID=$!

for _ in 1 2 3 4 5; do
  if curl -sf -o /dev/null "http://localhost:$PORT/"; then
    echo "preview ready: http://localhost:$PORT/"
    echo "  pid: $SERVER_PID   log: $LOG   stop: kill $SERVER_PID"
    exit 0
  fi
  sleep 1
done

echo "server not ready within 5s, log: $LOG" >&2
exit 1

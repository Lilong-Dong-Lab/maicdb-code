#!/usr/bin/env bash
# MAIC-DB 站点一键后台预览：重建 + 起 http.server（幂等——已在跑则复用）。
#
# 用法:  bash scripts/preview.sh [端口]     # 默认 8000
#
# 行为:
#   * 端口上已有预览在跑 → 直接复用（不重建），退出 0
#   * 否则 → 重建 site/_site（当前工作树的源，main 或任意分支）→
#     nohup 后台起 python3 -m http.server → 就绪探测 → 打印地址/pid
#
# 停止:  kill <打印出的 pid>（或 pkill -f 'http.server 8000'）
# 重建:  预览在跑时改动源码后，先停再跑本脚本（或手动
#        PYTHONPATH=src uv run python site/build.py 后浏览器刷新）。
set -euo pipefail

PORT="${1:-8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="/tmp/maicdb-preview-$PORT.log"

# 幂等分支：端口活着就复用（测试锁定该分支不重建）
if curl -sf -o /dev/null "http://localhost:$PORT/"; then
  echo "预览已在跑: http://localhost:$PORT/ （复用现有进程，未重建）"
  exit 0
fi

echo "重建站点（当前工作树源码）..."
(cd "$ROOT" && PYTHONPATH=src uv run python site/build.py >/dev/null)

echo "后台启动 http.server（端口 $PORT）..."
cd "$ROOT/site/_site"
nohup python3 -m http.server "$PORT" >"$LOG" 2>&1 &
SERVER_PID=$!

for _ in 1 2 3 4 5; do
  if curl -sf -o /dev/null "http://localhost:$PORT/"; then
    echo "预览就绪: http://localhost:$PORT/"
    echo "  pid: $SERVER_PID   日志: $LOG   停止: kill $SERVER_PID"
    exit 0
  fi
  sleep 1
done

echo "server 未在 5 秒内就绪，日志: $LOG" >&2
exit 1

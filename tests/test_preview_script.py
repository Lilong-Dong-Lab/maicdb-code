"""Preview-script tests (scripts/preview.sh).

The script's contract worth locking: **idempotent reuse** — when the
port already serves a preview, the script exits 0 with the reuse notice
and does NOT rebuild (no build side effects, no second server). The
cold-start path (build + nohup + readiness probe) is exercised manually
/ in the run flow; pinning it here would race the probe and pin the
environment rather than the contract.

No DB dependency: the idempotent branch must trigger before any build
step, which is exactly what these tests assert (a running stub server
on a scratch port must short-circuit the script before it can touch
``uv run``).
"""

import socket
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "preview.sh"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def test_script_passes_bash_syntax_check():
    """`bash -n` clean (the repo's other shell scripts' baseline too)."""
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_running_port_is_reused_without_rebuild():
    """Port already serving → exit 0, reuse notice, and the rebuild line
    never printed (the short-circuit happens before any build step, so
    the test needs no DB, no uv, and leaves no process behind)."""
    port = _free_port()
    stub = subprocess.Popen(
        ["python3", "-m", "http.server", str(port)],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # 就绪探测（与脚本同款），最多 5 秒
        for _ in range(10):
            with socket.socket() as probe:
                if probe.connect_ex(("localhost", port)) == 0:
                    break
            time.sleep(0.5)
        else:
            raise AssertionError("stub server never became ready")

        result = subprocess.run(
            ["bash", str(SCRIPT), str(port)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "复用现有进程" in result.stdout
        assert "重建站点" not in result.stdout  # 未走构建分支
    finally:
        stub.terminate()
        stub.wait(timeout=5)

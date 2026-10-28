"""Behavior pins for the full-history secret scanner (M3 flip gate, PR #32).

Public seam: ``scripts/secret-scan.py`` (subprocess), mirroring
``test_zenodo_bundle.py``'s script-testing pattern.

Provenance: none — every "secret" here is a synthetic fixture string built
by these tests, never cited to the vault or the published artifact. The
M3 runbook's recorded scan result is reproduced by
``test_this_repo_stays_clean``, which doubles as a standing net: any
commit that introduces scanner-matching content fails the suite.

The planted constants below are deliberately built by CONCATENATION so the
committed source of this very file never matches the scanner's patterns
(the flip gate runs on this repo's real history). Do not collapse them
into single literals; if you add a planted pattern, split it the same way.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_SCRIPT = REPO_ROOT / "scripts" / "secret-scan.py"

#: Planted fixture "secrets" — synthetic, concatenated so this file's own
#: blob stays scanner-clean (see module docstring).
GITHUB_TOKEN = "gh" + "p_" + "a" * 36
AWS_KEY_ID = "AK" + "IA" + "B" * 12 + "C" * 4
PRIVATE_KEY_LINE = "-----BEGIN " + "OPENSSH " + "PRIVATE KEY-----"
SLACK_TOKEN = "xox" + "b-" + "1" * 9 + "-" + "A" * 10
API_KEY_ASSIGN = 'api' + '_key = "Abcdef' + '123456"'  # value: 12 chars, has digit

DIRTY_APP = "\n".join(
    [
        f"GITHUB_TOKEN={GITHUB_TOKEN}",
        f"AWS_KEY={AWS_KEY_ID}",
        API_KEY_ASSIGN,
        PRIVATE_KEY_LINE,
        "benign line with no secrets here",
    ]
)

GIT_IDENTITY = ["-c", "user.name=maicdb-test", "-c", "user.email=test@example.invalid",
                "-c", "commit.gpgsign=false"]


def _run_scan(target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", str(SCAN_SCRIPT), str(target)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *GIT_IDENTITY, *args], cwd=repo, check=True,
                   capture_output=True, text=True)


def _make_repo(base: Path, name: str) -> Path:
    repo = base / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    return repo


def _commit(repo: Path, filename: str, content: str, message: str) -> None:
    (repo / filename).write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture()
def dirty_repo(tmp_path: Path) -> Iterator[Path]:
    """A repo whose history plants five finding shapes across blob and
    commit-message surfaces (values above are synthetic)."""
    repo = _make_repo(tmp_path, "dirty")
    _commit(repo, "app.py", DIRTY_APP, "add app with planted fakes")
    _commit(repo, "notes.txt", "nothing to see\n",
            "add notes\n\nbody mentions " + SLACK_TOKEN)
    yield repo


@pytest.fixture()
def clean_repo(tmp_path: Path) -> Iterator[Path]:
    repo = _make_repo(tmp_path, "clean")
    _commit(repo, "app.py", "password is stored in the environment\n",
            "benign prose only")
    yield repo


def test_planted_secrets_detected(dirty_repo: Path) -> None:
    """Five planted shapes across blob + commit-message surfaces: exit 1,
    FINDINGS, every pattern named, values redacted."""
    proc = _run_scan(dirty_repo)
    assert proc.returncode == 1
    assert "RESULT: FINDINGS" in proc.stdout
    for pattern in (
        "aws-access-key-id",
        "github-token",
        "generic-credential-assignment",
        "private-key-block",
        "slack-token",  # commit-message surface
    ):
        assert f"[{pattern}]" in proc.stdout
    # Redaction: the full value never appears; the redaction marker does.
    assert GITHUB_TOKEN not in proc.stdout
    assert "redacted" in proc.stdout


def test_scan_is_deterministic(dirty_repo: Path) -> None:
    """Same input, byte-stable output (repo convention: deterministic tools)."""
    first = _run_scan(dirty_repo)
    second = _run_scan(dirty_repo)
    assert first.returncode == second.returncode == 1
    assert first.stdout == second.stdout


def test_clean_repo_exit_zero(clean_repo: Path) -> None:
    """Benign content (prose 'password', no assignment shape): exit 0, CLEAN."""
    proc = _run_scan(clean_repo)
    assert proc.returncode == 0
    assert "RESULT: CLEAN" in proc.stdout
    assert "content findings: 0" in proc.stdout


def _have_git_history() -> bool:
    return (REPO_ROOT / ".git").exists()


@pytest.mark.skipif(not _have_git_history(), reason="no git history (exported tree)")
def test_this_repo_stays_clean() -> None:
    """The flip gate's standing form: the real repo scans CLEAN, exit 0.
    Depends on this file's planted constants staying concatenated (module
    docstring)."""
    proc = _run_scan(REPO_ROOT)
    assert proc.returncode == 0, proc.stdout
    assert "RESULT: CLEAN" in proc.stdout
    assert "content findings: 0" in proc.stdout

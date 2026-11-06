"""Behavior pins for the full-history secret scanner (M3 flip gate, PR #32).

Public seam: ``scripts/secret-scan.py`` (subprocess), mirroring
``test_zenodo_bundle.py``'s script-testing pattern.

Provenance: none — every "secret" here is a synthetic fixture string built
by these tests, never cited to the vault or the published artifact. The
M3 runbook's flip gate is re-checked in standing form by
``test_this_repo_stays_clean`` (exit 0 / CLEAN / zero content findings —
not the runbook's recorded counts, which are pinned there, superseded at
each flip-time re-run): any commit that introduces scanner-matching
content fails the suite.

The planted constants below are deliberately built by CONCATENATION so the
committed source of this very file never matches the scanner's patterns
(the flip gate runs on this repo's real history). Do not collapse them
into single literals; if you add a planted pattern, split it the same way.
"""

from __future__ import annotations

import os
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

#: Git repository-location vars that must never leak from this process
#: into fixture-repo git calls. Witness (2026-11-06, live): git exports
#: ``GIT_INDEX_FILE`` into the pre-commit hook env; the hook's pytest
#: child inherits it; the then-unsanitized ``git add -A`` in a tmp
#: fixture repo wrote the fixture's ``app.py`` entry into the MAIN
#: index, and ``git commit -am`` through the hook died with
#: ``invalid object ... for 'app.py'``. Stripped at every subprocess
#: boundary here; ``scripts/secret-scan.py`` runs index-free git ops
#: (log/cat-file/rev-list) but is sanitized too as defense-in-depth.
GIT_LOCATION_VARS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    # belt-and-braces (gate PR #73 NIT-1): provably inert for this
    # module's corruption class, listed to close git(1)'s
    # repo-location family
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
)


def _clean_git_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_VARS}


def _run_scan(target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", str(SCAN_SCRIPT), str(target)],
        capture_output=True, text=True, cwd=REPO_ROOT, env=_clean_git_env(),
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *GIT_IDENTITY, *args], cwd=repo, check=True,
                   capture_output=True, text=True, env=_clean_git_env())


def _make_repo(base: Path, name: str) -> Path:
    repo = base / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    return repo


def _commit(repo: Path, filename: str, content: str, message: str) -> None:
    (repo / filename).write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def test_git_helper_strips_hook_index_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fixture git calls must ignore inherited git location env vars.

    Witness (2026-11-06): git exports ``GIT_INDEX_FILE`` into the
    pre-commit hook's environment; the hook's pytest child inherits it,
    and this module's ``git add -A`` in a tmp fixture repo then wrote
    the fixture's staged entries (``app.py``, blob ``d64880e``) into
    the MAIN repository's index — ``git commit -am`` through the hook
    died with ``invalid object ... for 'app.py'``. The sentinel below
    is that poison: with the OLD unsanitized helper, ``git add -A``
    against a byte-empty index file dies exit 128 ("index file smaller
    than expected") and this test goes red via CalledProcessError; the
    sanitized helper never touches the sentinel (it stays byte-empty)
    and the fixture proceeds. Writing an index INTO a poisoned
    ``GIT_INDEX_FILE`` — the incident's actual corruption path —
    requires a valid pre-existing index (the main repo had one); this
    test pins the never-touched property, which suffices to catch the
    leak (gate PR #73 MINOR-1 wording; red mode re-executed by the
    reviewer).
    """
    sentinel = tmp_path / "poisoned-index"
    sentinel.write_bytes(b"")
    monkeypatch.setenv("GIT_INDEX_FILE", str(sentinel))
    repo = _make_repo(tmp_path, "leakcheck")
    (repo / "app.py").write_text("index leak probe\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "index leak probe")
    assert sentinel.read_bytes() == b""
    # the fixture repo's own history is intact (same sanitization the
    # helper applies)
    log = subprocess.run(
        ["git", *GIT_IDENTITY, "log", "--oneline"], cwd=repo,
        capture_output=True, text=True, check=True, env=_clean_git_env(),
    )
    assert "index leak probe" in log.stdout


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

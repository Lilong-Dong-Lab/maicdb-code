"""CI workflow structure guards (M3-T7, issue #42).

The workflow file is this ticket's deliverable; two of its properties are
load-bearing enough to pin against silent removal:

- CI builds the site on every PR/push (issue #42's pipeline: uv sync →
  site build, both locales → full suite incl. site tests), with a
  workflow-level byte-stability check (spec §6's determinism contract,
  exercised in the CI environment, not only via the suite's tmp-dir
  builds).
- The Pages deploy job cannot run before the public flip (ADR-0002: the
  site renders the published artifact and the flip is T8's human gate —
  premature deploy would be pre-submission publicity; runbook §3).

Both tests parse ``.github/workflows/ci.yml`` exactly as GitHub Actions
does (YAML → job/step structure), asserting structure rather than shell
behavior; the executed behavior is pinned separately by the suite-summary
pins (quirk 3) and the PR runs themselves.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = yaml.safe_load(
    (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
)


def test_ci_builds_the_site_on_every_pr():
    """The tests job carries ONE unconditional site-build step: two builds
    byte-compared (diff -r over both output trees) plus a both-locales
    smoke check — issue #42's "site build (both locales) → byte-stable
    assertion runs in CI too".

    Unconditional matters: the step has no ``if``, so it runs on every
    pull_request AND push event — "CI builds the site on every PR".
    """
    steps = WORKFLOW["jobs"]["tests"]["steps"]
    build_steps = [
        s for s in steps if "site/build.py" in str(s.get("run", ""))
    ]
    assert len(build_steps) == 1, "expected exactly one site-build step"
    step = build_steps[0]
    assert "if" not in step, "site build must run unconditionally (every PR)"
    run = step["run"]
    assert run.count("site/build.py") == 2, "byte-stability needs two builds"
    assert "diff -r" in run, "the two builds must be byte-compared"
    assert "site/_site/zh/index.html" in run, "both locale trees smoke-checked"


def test_pages_deploy_cannot_run_pre_flip():
    """The Pages deploy job (the only job using actions/deploy-pages):

    - gated on the repo variable DEPLOY_SITE, which stays unset until T9
      (issue #45) sets it after the public flip (T8, issue #44; runbook
      §3) — with the variable unset the job is SKIPPED in every run,
      which is issue #42's "verifiably skipped while repo is private"
      acceptance. ADR-0002: the flip is the human gate; a premature
      deploy would be pre-submission publicity.
    - scoped to push-on-main or manual workflow_dispatch — never a
      pull_request event;
    - needs the tests job, so a red suite never deploys;
    - publishes ``site/_site`` (both locale trees, spec Q6).
    """
    jobs = WORKFLOW["jobs"]
    deploy_jobs = [
        name
        for name, job in jobs.items()
        if any("deploy-pages" in str(s.get("uses", "")) for s in job.get("steps", []))
    ]
    assert deploy_jobs == ["deploy-pages"], "exactly one deploy job, by name"
    job = jobs["deploy-pages"]
    cond = str(job.get("if", ""))
    assert "vars.DEPLOY_SITE == 'true'" in cond, "the pre-flip variable gate"
    assert "github.ref == 'refs/heads/main'" in cond, "deploys come from main"
    assert "pull_request" not in cond, "PR events must never deploy"
    assert "workflow_dispatch" in cond, "T9's manual trigger path"
    assert job["needs"] in ("tests", ["tests"]), "deploy requires a green suite"
    uploads = [
        s
        for s in job["steps"]
        if "upload-pages-artifact" in str(s.get("uses", ""))
    ]
    assert uploads and uploads[0]["with"]["path"] == "site/_site"

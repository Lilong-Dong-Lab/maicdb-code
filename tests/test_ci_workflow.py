"""CI workflow structure guards (M3-T7, issue #42).

The workflow file is this ticket's deliverable; two of its properties are
load-bearing enough to pin against silent removal:

- CI builds the site on every PR/push (issue #42's pipeline: uv sync →
  site build, both locales → full suite incl. site tests), with a
  workflow-level byte-stability check (spec §6's determinism contract,
  exercised in the CI environment, not only via the suite's tmp-dir
  builds).
- The Pages deploy job cannot run before the public flip (ADR-0004:
  "Site publishing inherits the flip gate … Pre-submission publicity is
  intended for a resource paper" — ADR-0004 carries the constraint and
  itself cites ADR-0002 for the flip; runbook §3).

Both tests parse ``.github/workflows/ci.yml`` exactly as GitHub Actions
does (YAML → job/step structure), asserting structure rather than shell
behavior; the executed behavior is pinned separately by the suite-summary
pins (quirk 3) and the PR runs themselves.

The predicates are pure functions over a workflow mapping so the
rule-4 self-vectors (ESCAPE_FORMS) can feed them known-escape inputs and
watch them reject — a guard with no negative vector proves only that the
guarded surface is quiet, not that the guard bites.
"""

import copy
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = yaml.safe_load(
    (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
)


def site_build_pinned(workflow: dict) -> bool:
    """The tests job carries exactly ONE site-build step that is
    unconditional at BOTH levels (no step ``if``, no job-level ``if`` —
    so it runs on every pull_request and push), builds twice, and
    byte-compares the two builds ACROSS output directories (a same-dir
    self-diff would be vacuous), plus the both-locales smoke check.
    """
    tests_job = workflow["jobs"]["tests"]
    if "if" in tests_job:
        return False
    steps = tests_job["steps"]
    build_steps = [s for s in steps if "site/build.py" in str(s.get("run", ""))]
    if len(build_steps) != 1:
        return False
    step = build_steps[0]
    if "if" in step:
        return False
    run = step["run"]
    return (
        run.count("site/build.py") == 2
        # cross-directory diffs, never a self-compare
        and "diff -r site/_data /tmp/site-rebuild/_data" in run
        and "diff -r site/_site /tmp/site-rebuild/_site" in run
        and "site/_site/zh/index.html" in run
    )


def deploy_gate_pinned(workflow: dict) -> bool:
    """The Pages deploy job (the only job using actions/deploy-pages):

    - gated on the repo variable DEPLOY_SITE, which stays unset until T9
      (issue #45) sets it after the public flip (T8, issue #44; runbook
      §3) — with the variable unset the job is SKIPPED in every run,
      which is issue #42's "verifiably skipped while repo is private"
      acceptance. ADR-0004: the flip is the human gate; a premature
      deploy would be pre-submission publicity.
    - scoped to push-on-main or manual workflow_dispatch — never a
      pull_request event;
    - needs the tests job, so a red suite never deploys;
    - publishes ``site/_site`` (both locale trees per spec §6 — EN
      unprefixed + ``zh/``; Q6 is the relative-path Pages project site).
    """
    jobs = workflow["jobs"]
    deploy_jobs = [
        name
        for name, job in jobs.items()
        if any("deploy-pages" in str(s.get("uses", "")) for s in job.get("steps", []))
    ]
    if deploy_jobs != ["deploy-pages"]:
        return False
    job = jobs["deploy-pages"]
    cond = str(job.get("if", ""))
    if "vars.DEPLOY_SITE == 'true'" not in cond:
        return False
    if "github.ref == 'refs/heads/main'" not in cond:
        return False
    if "pull_request" in cond:
        return False
    if "workflow_dispatch" not in cond:
        return False
    if job.get("needs") not in ("tests", ["tests"]):
        return False
    uploads = [
        s for s in job["steps"] if "upload-pages-artifact" in str(s.get("uses", ""))
    ]
    return bool(uploads) and uploads[0].get("with", {}).get("path") == "site/_site"


def test_ci_builds_the_site_on_every_pr():
    """Issue #42's pipeline: uv sync → site build (both locales) → full
    suite; the byte-stable assertion runs in CI at the workflow level
    (and tests/test_site_build.py::test_build_is_byte_stable runs inside
    the suite — db ships in-repo, quirk 3)."""
    assert site_build_pinned(WORKFLOW), (
        "the site-build step drifted from the pinned shape: unconditional "
        "(step AND job level), two builds, cross-dir diff -r, both locales"
    )


def test_pages_deploy_cannot_run_pre_flip():
    """ADR-0004's flip gate, machine-enforced: see deploy_gate_pinned."""
    assert deploy_gate_pinned(WORKFLOW), (
        "the deploy-pages gate drifted: variable gate + main-ref/dispatch "
        "scope + green-suite dependency + site/_site upload path"
    )


# --------------------------------------------------------------------------- #
# Rule-4 self-vectors: known escape forms, each fed to the predicate that
# must REJECT it (CODING_STANDARDS §4; the two named in the PR #54 gate:
# job-level `if` skipping the build, same-dir self-diff). An escape form
# the predicates fail to reject is a finding against this guard.
# --------------------------------------------------------------------------- #
def _set_step_if(w: dict) -> None:  # step-level condition smuggled in
    for s in w["jobs"]["tests"]["steps"]:
        if "site/build.py" in str(s.get("run", "")):
            s["if"] = "github.event_name == 'push'"


ESCAPE_FORMS = [
    (
        "job-level if on the tests job skips the build on PRs",
        site_build_pinned,
        lambda w: w["jobs"]["tests"].update({"if": "github.event_name == 'push'"}),
    ),
    (
        "step-level if on the build step skips it on PRs",
        site_build_pinned,
        _set_step_if,
    ),
    (
        "same-dir self-diff is a vacuous byte-compare",
        site_build_pinned,
        lambda w: [
            s.update(
                run=(
                    "PYTHONPATH=src uv run python site/build.py\n"
                    "PYTHONPATH=src uv run python site/build.py\n"
                    "diff -r site/_data site/_data\n"
                    "diff -r site/_site site/_site\n"
                    "test -f site/_site/index.html && "
                    "test -f site/_site/zh/index.html"
                )
            )
            for s in w["jobs"]["tests"]["steps"]
            if "site/build.py" in str(s.get("run", ""))
        ],
    ),
    (
        "inverted variable gate (!= 'false') runs pre-flip: unset != 'false'",
        deploy_gate_pinned,
        lambda w: w["jobs"]["deploy-pages"].update(
            {
                "if": "vars.DEPLOY_SITE != 'false' && "
                "(github.event_name == 'workflow_dispatch' || "
                "(github.event_name == 'push' && github.ref == 'refs/heads/main'))"
            }
        ),
    ),
    (
        "pull_request added to the deploy scope",
        deploy_gate_pinned,
        lambda w: w["jobs"]["deploy-pages"].update(
            {"if": "vars.DEPLOY_SITE == 'true' || github.event_name == 'pull_request'"}
        ),
    ),
    (
        "needs removed: a red suite could deploy",
        deploy_gate_pinned,
        lambda w: w["jobs"]["deploy-pages"].pop("needs"),
    ),
]


def test_selfvectors_escape_forms_are_rejected():
    """Each known escape form must flip the corresponding predicate to
    False — the guard bites, not just passes (rule 4)."""
    for label, predicate, mutate in ESCAPE_FORMS:
        escaped = copy.deepcopy(WORKFLOW)
        mutate(escaped)
        assert not predicate(escaped), f"escape form not pinned: {label}"

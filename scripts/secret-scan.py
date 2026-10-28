#!/usr/bin/env python3
"""Full-history secret scan for maicdb-code.

Scans every unique blob reachable from all refs (local + remote-tracking),
plus every commit message, for high-signal credential patterns. Binary
blobs are skipped (counted, listed by path). Matched values are redacted
in the output. Exit status is 1 iff findings exist, so the M3 flip
runbook (docs/m3-flip-runbook.md) can gate on it.

Usage:
    uv run scripts/secret-scan.py [REPO_PATH]

Stdlib only; deterministic output given the same refs.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from typing import NamedTuple

# High-signal patterns only. The generic assignment pattern is
# post-filtered (value needs a digit, length >= 12, no obvious
# placeholder text) to keep the false-positive rate usable.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,255}\b")),
    ("github-fine-grained-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,255}\b")),
    ("sk-style-api-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("huggingface-token", re.compile(r"\bhf_[A-Za-z0-9]{34}\b")),
    ("npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        "generic-credential-assignment",
        re.compile(
            r"\b(password|passwd|secret|api[_-]?key|access[_-]?token|"
            r"auth[_-]?token|client[_-]?secret|private[_-]?token)\b[\"']?"
            r"\s*[:=]\s*[\"']?([A-Za-z0-9_\-/+=.]{8,})"
        ),
    ),
]

PLACEHOLDER_MARKERS = ("xxx", "example", "your_", "your-", "placeholder", "<", "${", "changeme")

# Advisory filename flags (path shape, not content).
FILENAME_FLAGS = re.compile(
    r"(^id_rsa|^id_dsa|^id_ed25519|\.pem$|\.key$|\.p12$|\.pfx$|^\.env$|^\.env\.|"
    r"credentials|^secret)",
    re.IGNORECASE,
)

MAX_TEXT_BLOB_BYTES = 4 * 1024 * 1024
BINARY_SNIFF_BYTES = 8192


def git(repo: str, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True
    ).stdout


def redact(value: str) -> str:
    if len(value) <= 8:
        return f"<redacted len={len(value)}>"
    return value[:4] + "…<redacted len=%d>" % len(value)


def redact_line(line: str, span: tuple[int, int]) -> str:
    start, end = span
    text = (line[:start] + redact(line[start:end]) + line[end:]).rstrip("\n")
    return text[:160] + ("…" if len(text) > 160 else "")


def generic_value_ok(value: str) -> bool:
    if len(value) < 12 or not any(c.isdigit() for c in value):
        return False
    low = value.lower()
    return not any(m in low for m in PLACEHOLDER_MARKERS)


class Hit(NamedTuple):
    """One pattern match inside one scanned line."""

    pattern: str
    line_no: int
    line: str
    start: int
    end: int


def scan_text(text: str) -> list[Hit]:
    hits: list[Hit] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for name, pattern in PATTERNS:
            for m in pattern.finditer(line):
                start, end = m.start(), m.end()
                if name == "generic-credential-assignment":
                    start, end = m.start(2), m.end(2)
                    if not generic_value_ok(m.group(2)):
                        continue
                hits.append(Hit(name, line_no, line, start, end))
    return hits


def blob_findings(
    repo: str, blob_sizes: dict[str, int], blob_paths: dict[str, list[str]]
) -> tuple[list[dict], list[str], list[str], int]:
    """Scan every unique text blob; skip binary/oversized (counted, listed)."""
    findings: list[dict] = []
    binary_skipped: list[str] = []
    oversized_skipped: list[str] = []
    scanned = 0
    for sha in sorted(blob_sizes):
        paths = sorted(set(blob_paths.get(sha, [])))
        if blob_sizes[sha] > MAX_TEXT_BLOB_BYTES:
            oversized_skipped.extend(paths or [f"<unnamed blob {sha[:12]}>"])
            continue
        content = subprocess.run(
            ["git", "-C", repo, "cat-file", "blob", sha],
            check=True, capture_output=True,
        ).stdout
        if b"\x00" in content[:BINARY_SNIFF_BYTES]:
            binary_skipped.extend(paths or [f"<unnamed blob {sha[:12]}>"])
            continue
        scanned += 1
        for hit in scan_text(content.decode("utf-8", errors="replace")):
            findings.append({
                "kind": "blob", "pattern": hit.pattern, "blob": sha[:12],
                "commit": "", "date": "", "subject": "",
                "paths": paths, "line": hit.line_no,
                "excerpt": redact_line(hit.line, (hit.start, hit.end)),
            })
    return findings, binary_skipped, oversized_skipped, scanned


def commit_message_findings(repo: str) -> list[dict]:
    findings: list[dict] = []
    log = git(repo, "log", "--all", "--format=%H%x09%ad%x09%s%x09%B%x1e", "--date=short")
    for record in log.split("\x1e"):
        if not record.strip():
            continue
        parts = record.split("\t", 3)
        if len(parts) < 3:
            continue
        cid, date, subject = parts[0].strip(), parts[1], parts[2]
        for hit in scan_text(record):
            findings.append({
                "kind": "commit-message", "pattern": hit.pattern, "blob": "-",
                "commit": cid[:12], "date": date, "subject": subject,
                "paths": [], "line": hit.line_no,
                "excerpt": redact_line(hit.line, (hit.start, hit.end)),
            })
    return findings


def attribute_intros(repo: str, findings: list[dict]) -> None:
    """Fill in each blob finding's introducing commit (advisory context)."""
    for f in findings:
        if f["kind"] != "blob":
            continue
        intro = git(repo, "log", "--all", "--find-object=" + f["blob"],
                    "--format=%h|%ad|%s", "--date=short", "-n", "1")
        if "|" in intro:
            h, d, s = intro.strip().split("|", 2)
            f["commit"], f["date"], f["subject"] = h, d, s


def filename_flags(blob_paths: dict[str, list[str]]) -> list[str]:
    """Advisory flags on path shape (no content check), across all trees."""
    flags: list[str] = []
    seen: set[str] = set()
    for _sha, paths in sorted(blob_paths.items()):
        for p in paths:
            if p in seen:
                continue
            if FILENAME_FLAGS.search(p.rsplit("/", 1)[-1]) or FILENAME_FLAGS.search(p):
                seen.add(p)
                flags.append(p)
    return flags


def print_report(
    repo: str,
    n_refs: int,
    n_commits: int,
    scanned: int,
    binary_skipped: list[str],
    oversized_skipped: list[str],
    findings: list[dict],
    flags: list[str],
) -> int:
    print("== maicdb full-history secret scan ==")
    print(f"repo: {repo}")
    print(f"refs: {n_refs}  commits: {n_commits}")
    print(f"text blobs scanned: {scanned}")
    print(f"binary blobs skipped: {len(binary_skipped)}  paths: {sorted(set(binary_skipped))}")
    print(f"oversized text blobs skipped: {len(oversized_skipped)}  paths: {sorted(set(oversized_skipped))}")

    print(f"\ncontent findings: {len(findings)}")
    for f in sorted(findings, key=lambda f: (f["pattern"], f["blob"], f["line"])):
        where = f["commit"] + " " + f["date"] if f["commit"] else "(introducing commit unknown)"
        loc = f"paths {f['paths']} line {f['line']}" if f["kind"] == "blob" else "commit message"
        print(f"  [{f['pattern']}] blob {f['blob']} {where} {loc}")
        print(f"    {f['excerpt']}")

    print(f"\nfilename flags (advisory, content not matched): {len(flags)}")
    for p in flags:
        print(f"  {p}")

    status = "FINDINGS" if findings else "CLEAN"
    print(f"\nRESULT: {status}")
    return 1 if findings else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo", nargs="?", default=".", help="path to the git repository")
    args = ap.parse_args()
    repo = args.repo

    commits = git(repo, "rev-list", "--all").split()
    objects = git(repo, "rev-list", "--all", "--objects").splitlines()

    blob_paths: dict[str, list[str]] = defaultdict(list)
    obj_ids = []
    for entry in objects:
        parts = entry.split(" ", 1)
        obj_ids.append(parts[0])
        if len(parts) == 2 and parts[1]:
            blob_paths[parts[0]].append(parts[1])

    # Filter to blobs via batch-check (one process, all objects on stdin).
    batch = subprocess.run(
        ["git", "-C", repo, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
        check=True, capture_output=True, text=True,
        input="\n".join(obj_ids) + "\n",
    ).stdout
    blob_sizes: dict[str, int] = {}
    for line in batch.splitlines():
        sha, otype, size = line.split()
        if otype == "blob":
            blob_sizes[sha] = int(size)

    findings, binary_skipped, oversized_skipped, scanned = blob_findings(
        repo, blob_sizes, blob_paths
    )
    findings += commit_message_findings(repo)
    attribute_intros(repo, findings)
    flags = filename_flags(blob_paths)

    n_refs = len(git(repo, "for-each-ref", "--format=%(refname)").splitlines())
    return print_report(
        repo, n_refs, len(commits), scanned,
        binary_skipped, oversized_skipped, findings, flags,
    )


if __name__ == "__main__":
    sys.exit(main())

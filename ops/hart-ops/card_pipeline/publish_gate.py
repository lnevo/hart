"""Stage 3 gate: checks that must pass before ``cars.py publish`` changes STS or Operations Pro.

Decision: hart/wiki/decisions/ADR-018-staged-intake-workflow.md. A full publish waits until
every photo in every batch is recorded or rejected. ``publish --only ID...`` skips the batch
check so one car can be tested alone; the other checks still apply.

Each check returns a list of problems (empty when it passes). ``--skip-check NAME`` skips
one by name, and the skip is printed.
"""
from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path

CHECKS = ("batches", "committed", "pi", "backup")
BACKUP_MAX_AGE_HOURS = 12
OPS_FILES = ["Operations.xml", "OperationsCarRoster.xml", "OperationsEngineRoster.xml",
             "OperationsLocationRoster.xml", "OperationsRouteRoster.xml",
             "OperationsTrainRoster.xml"]


def unfinished_batches(batch_root: Path) -> list[str]:
    """Photos still pending, or approved but not yet recorded, in any batch."""
    import csv

    problems = []
    for review in sorted(batch_root.glob("*/review.csv")):
        with review.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            if r["status"] in ("pending", "approved"):
                problems.append(f"{review.parent.name}/{r['photo']} is {r['status']}")
    return problems


def uncommitted(paths: list[Path], run=subprocess.run) -> list[str]:
    """Repository files changed since the last commit: stage 2 is not committed yet."""
    problems = []
    for path in paths:
        out = run(["git", "status", "--porcelain", "--", str(path)], capture_output=True,
                  text=True, cwd=path.parent if path.parent.is_dir() else None)
        if out.returncode:
            problems.append(f"git status failed for {path}")
        elif out.stdout.strip():
            problems.append(f"{path.name} has uncommitted changes")
    return problems


def ops_hash(directory: Path) -> str:
    h = hashlib.sha256()
    for name in OPS_FILES:
        h.update((directory / name).read_bytes())
    return h.hexdigest()


def pi_out_of_step(local_dir: Path, pi_host: str, pi_dir: str, run=subprocess.run) -> list[str]:
    """The Pi's Operations files must equal the repo copy: otherwise run make ops-pull first."""
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", pi_host,
           f"cd '{pi_dir}' && cat {' '.join(OPS_FILES)} | sha256sum | cut -d' ' -f1"]
    try:
        out = run(cmd, capture_output=True, text=True, timeout=45)
    except Exception as err:  # unreachable Pi, ssh missing, timeout
        return [f"could not reach the Pi to compare Operations files: {err}"]
    if out.returncode:
        return [f"could not read the Pi's Operations files: {out.stderr.strip()[:120]}"]
    if out.stdout.strip() != ops_hash(local_dir):
        return ["the Pi's Operations files differ from the repo copy: run make ops-pull "
                "(JMRI closed) and commit what it brings in"]
    return []


def backup_missing(backups_dir: Path, now: float | None = None) -> list[str]:
    """Something in the STS backups folder must be newer than BACKUP_MAX_AGE_HOURS."""
    now = time.time() if now is None else now
    newest = 0.0
    if backups_dir.is_dir():
        for entry in backups_dir.iterdir():
            newest = max(newest, entry.stat().st_mtime)
    if now - newest > BACKUP_MAX_AGE_HOURS * 3600:
        return [f"no STS backup newer than {BACKUP_MAX_AGE_HOURS} hours in {backups_dir}: "
                "take one in the STS web app or with the sts_backup tool"]
    return []


def run_gate(*, batch_root, tracked, ops_local, pi_host, pi_dir, backups_dir,
             only: bool, skip: list[str]) -> list[str]:
    """All problems from the checks that apply. An empty list means publish may go ahead."""
    problems = []
    for name in skip:
        if name not in CHECKS:
            raise SystemExit(f"--skip-check takes one of: {' '.join(CHECKS)}")
        print(f"  gate: skipping the {name} check")
    steps = {
        "batches": lambda: [] if only else unfinished_batches(batch_root),
        "committed": lambda: [] if only else uncommitted(tracked),
        "pi": lambda: pi_out_of_step(ops_local, pi_host, pi_dir),
        "backup": lambda: backup_missing(backups_dir),
    }
    for name, check in steps.items():
        if name not in skip:
            problems += [f"[{name}] {p}" for p in check()]
    return problems

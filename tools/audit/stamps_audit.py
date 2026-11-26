"""The audits of tools/audit/check_stamps.py: the CHECK_AUDIT folder's reads (read_audit, for `audit-report`) and the
declaration audit of the step-manifest jobs (ADR-037 stages 4a, 4c; docs/pipeline-map/build-graph-design.md 4.5:
step_reads, audit_lines, manifest_steps and `check_stamps.py audit`). check_stamps.py imports this file from its own
folder and re-exports every name; record's audit (audit_trace) and the unit jobs' coverage check (uncovered) stay
there, beside the declarations they read. An edit here reruns the same jobs an edit to check_stamps.py does.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # pm is tools/pipeline/manifest.py loaded by path (stamps_cache); this import gives mypy its types only
    from tools.pipeline.manifest_jobs import Declared

HERE = Path(__file__).resolve().parent
# Loaded by path from any cwd (check_stamps.py does so): its sibling comes from this folder, on sys.path only while
# it is imported, and one from another folder (a second checkout in one process) is refused.
_added = str(HERE) not in sys.path
if _added:
    sys.path.insert(0, str(HERE))
try:
    import stamps_cache
finally:
    if _added:
        sys.path.remove(str(HERE))
_where = getattr(stamps_cache, "__file__", None)
if not _where or Path(_where).resolve().parent != HERE:
    raise ImportError(f"stamps_audit.py: stamps_cache must be the file beside it in {HERE}, not {_where}")
from stamps_cache import LITTER, MANIFEST, _file, _pruned, pm, traced  # noqa: E402

# ---- the audit ----


def read_audit(folder: Path) -> dict[str, tuple[set[str], set[str]]]:
    """job name -> (files read, folders listed), from a CHECK_AUDIT folder: N.name and N.log per job."""
    jobs = {}
    for namef in sorted(folder.glob("*.name")):
        files: set[str] = set()
        dirs: set[str] = set()
        logf = namef.with_suffix(".log")
        if logf.is_file():
            for line in logf.read_text(errors="replace").splitlines():
                kind, _, rel = line.partition("\t")
                if not rel or rel.startswith(("<", ".git/", ".venv/")) or rel in (".git", ".venv") \
                        or "__pycache__" in rel.split("/") or rel.endswith(LITTER):
                    continue
                if _pruned(rel):
                    continue
                (files if kind == "r" else dirs).add(rel)
        jobs[namef.read_text().strip()] = (files, dirs)
    return jobs


def _reaches(d: str, pat: str) -> bool:
    """Whether listing folder `d` is covered by pattern `pat`: `d` is on the way to a file it names, or inside the
    folder its wildcard spans. A file pattern ("Makefile", "AGENTS.md") reaches only its parent folders, and a
    root wildcard only "**" (every folder), not "*.md" (root files)."""
    if "*" not in pat:
        return pat.startswith(d + "/")
    head = pat.split("*", 1)[0]
    if "/" not in head:
        return pat.startswith("**")
    literal = head.rsplit("/", 1)[0]
    return d == literal or d.startswith(literal + "/") or literal.startswith(d + "/")


# ---- the declaration audit (ADR-037 stages 4a, 4c; docs/pipeline-map/build-graph-design.md 4.5) ----

class AuditError(Exception):
    """The declaration audit cannot run for a job (no such manifest job, no trace, no audit in its stamp)."""


AUDIT_HOW = "warn only in this run; a CHECK_AUDIT run and the weekly full run fail on it (ADR-037 stage 4c)"
AUDIT_FAILS = "this run fails on it (ADR-037 stage 4c: a CHECK_AUDIT run or CHECK_AUDIT_FAILS=1)"


def step_reads(name: str, trace_log: str | Path, root: Path, steps: Sequence[Declared]) -> dict:
    """Job `name`'s data reads, from its trace: {"steps": {step: [files]}, "unowned": {}, "absent": [], "bash": [the
    step, when bash runs it, whose reads the trace cannot see]}. Every job of the manifest is one step (stage 4b), so
    every process in its trace is that step's. Files are the repo paths its processes read as data ("r" lines; an open
    as code, a "c" line, is not one, but the same file read as text is). The shape is stage 4a's, which `audit` reads.
    Raises AuditError when the job is not one step, or the trace cannot be read or holds no process."""
    if len(steps) != 1:
        raise AuditError(f"{name} has {len(steps)} steps in {MANIFEST.as_posix()}; each job is one step")
    (step,) = steps
    try:
        text = Path(trace_log).read_text(encoding="utf-8", errors="surrogateescape")
    except OSError as exc:
        raise AuditError(f"cannot read the trace of {name}: {exc}") from exc
    skip = traced._skip_prefixes(str(root))
    reads: set[str] = set()
    started = 0
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        kind, rest = parts[1], parts[2:]
        if kind == "s" and len(rest) >= 3:
            started += 1
        elif kind == "r":
            rel = traced.keep(rest[0], str(root), skip)
            if rel is not None and not os.path.isabs(rel):
                reads.add(rel)
    if not started and step.python:
        raise AuditError(f"the trace of {name} ({trace_log}) holds no process start")
    if not step.python:
        return {"steps": {}, "unowned": {}, "absent": [], "bash": [step.name]}
    return {"steps": {step.name: sorted(reads)}, "unowned": {}, "absent": [], "bash": []}


def audit_lines(name: str, audit: dict, steps: Sequence[Declared], full: bool = False, how: str = AUDIT_HOW) -> tuple[list[str], int]:
    """The audit's report for job `name` from its step_reads and the manifest's steps now, and the number of
    warnings. A job with none gets one line. `full` lists every file (the `audit` command); else at most 8 a step."""
    by_name = {s.name: s for s in steps}
    rows: list[str] = []
    count = 0
    for step, files in sorted(audit.get("steps", {}).items()):
        if step not in by_name:
            rows.append(f"    {step}: in the stamp, not in tools/pipeline/checks.toml now; run the job again")
            count += 1
            continue
        bad = pm.undeclared(by_name[step], files)
        count += len(bad)
        if bad:
            shown = bad if full or len(bad) <= 8 else [*bad[:8], f"and {len(bad) - 8} more"]
            rows.append(f"    {step}: {', '.join(shown)}")
    for who, files in audit.get("unowned", {}).items():
        count += len(files)
        rows.append(f"    no step started this process ({who}): {', '.join(files)}")
    for step in audit.get("absent", []):
        count += 1
        rows.append(f"    {step}: no process of it in the trace, so its reads are not audited")
    recorded = set(audit.get("steps", {})) | set(audit.get("absent", []))
    for s in steps:                 # a step added to the manifest after the stamp was recorded
        if s.python and s.name not in recorded:
            count += 1
            rows.append(f"    {s.name}: in tools/pipeline/checks.toml, not in the stamp; run the job again")
    bash = [s.name for s in steps if not s.python]          # from the manifest now, not the stamp
    tail = f" ({', '.join(bash)}: bash, which the trace cannot see, so not audited)" if bash else ""
    if not count:
        return [f"stamp audit: {name}: every data read is declared in tools/pipeline/checks.toml (the code "
                f"the job imported or ran is not audited){tail}"], 0
    return ([f"WARNING: stamp audit: {name}: {count} read(s) not declared in tools/pipeline/checks.toml "
             f"(inputs, or quiet_inputs for a read not drawn on the map); {how}", *rows,
             *([f"    not audited: {', '.join(bash)} (bash, which the trace cannot see)"] if bash else []),
             f"    again: python3 tools/audit/check_stamps.py audit {name}"], count)


def manifest_steps(name: str, root: Path) -> tuple[Declared, ...]:
    """Job `name`'s steps as the audit sees them (manifest.declarations). Raises AuditError for a job that is not a
    manifest job, manifest.ManifestError for a manifest that will not read."""
    decls: dict[str, tuple[Declared, ...]] = pm.declarations(root / MANIFEST)
    if name not in decls:
        raise AuditError(f"{name!r} is no job of {MANIFEST.as_posix()} (its jobs: {', '.join(decls)})")
    return decls[name]


def audit_stamp(names: list[str], root: Path, store: Path) -> int:
    """`check_stamps.py audit [NAME...]`: each manifest job's report from the audit its last recorded pass kept (every
    manifest job when no name is given), against the manifest now. 0 when every read is declared, 1 with warnings,
    2 when a job cannot be audited (its line says why)."""
    try:
        decls = pm.declarations(root / MANIFEST)
    except pm.ManifestError as exc:
        print(f"stamp audit: cannot run: {exc}", file=sys.stderr)
        return 2
    rc = 0
    for name in names or list(decls):
        if name not in decls:
            print(f"stamp audit: {name}: no job of {MANIFEST.as_posix()} (its jobs: {', '.join(decls)})",
                  file=sys.stderr)
            rc = 2
            continue
        stamp = traced.load(_file(name, store))
        if decls[name][0].unaudited:
            print(f"stamp audit: {name}: not audited: {decls[name][0].unaudited}")
            continue
        if not stamp or not isinstance(stamp.get("audit"), dict):
            print(f"stamp audit: {name}: {'no stamp' if not stamp else 'its stamp holds no audit'}; a pass of the "
                  f"job records one (FULL=1 CHECK_ONLY='^{name}$' tools/check.sh)", file=sys.stderr)
            rc = 2
            continue
        lines, count = audit_lines(name, stamp["audit"], decls[name], full=True)
        print("\n".join(lines))
        rc = max(rc, 1 if count else 0)
    return rc

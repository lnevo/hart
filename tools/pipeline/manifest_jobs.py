"""manifest_jobs.py

What tools/audit/check_stamps.py reads of checks.toml per job, without the checks against git and the map: each job's
stamp key (job_keys, ADR-037 stage 4b) and the trace audit's declarations, undeclared() and covers() (stage 4a).
tools/pipeline/manifest.py is the entry point and re-exports every name here.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from manifest_base import MANIFEST, ManifestError, _entries, glob_regex, is_glob, path_problem, read
from manifest_checks import _script, _split_env, git_problem


@dataclass(frozen=True)
class JobKey:
    """What check.sh's stamp key takes from a job's manifest entry: a sha256 of the entry, and the git refs it names."""
    digest: str
    git: tuple[str, ...]


def job_keys(path: Path = MANIFEST) -> dict[str, JobKey]:
    """check.sh's job name (each step is a job of its own, named after it) -> its JobKey. tools/audit/check_stamps.py
    puts both in the job's stamp key, so an edited entry reruns its own job and no other, and a job whose entry names
    `head` reruns after every commit. Read without the checks against git and the map (check.sh ran `jobs` on the file
    before any job started, and that checks it all), but a git field the key cannot use is a ManifestError, as is an
    entry with no name, a name that is not text, or two steps of one name."""
    data, shown = read(path)
    out = {}
    for name, entry in _jobs(data, shown).items():
        why = git_problem(entry.get("git"))
        if why:
            raise ManifestError(f"{shown}: step {name!r}: git: {why} (manifest.py check names every problem)")
        try:
            digest = hashlib.sha256(json.dumps({"job": name, "step": entry}, sort_keys=True, ensure_ascii=False,
                                               separators=(",", ":")).encode()).hexdigest()
        except (TypeError, ValueError) as err:     # a TOML date or time: no field of a step takes one
            raise ManifestError(f"{shown}: step {name!r} holds a value JSON cannot hold (a date or time?): {err}") \
                from None
        out[name] = JobKey(digest, tuple(entry["git"]))
    return out


def _jobs(data: dict, shown: str) -> dict[str, dict]:
    """check.sh's job name -> the manifest entry it runs, in file order: every step is a job of its own, under its
    name. An entry with no name, a name that is not text, or two steps of one name is a ManifestError."""
    jobs: dict[str, dict] = {}
    for i, entry in enumerate(_entries(data, shown), 1):
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ManifestError(f"{shown}: step {i}: no name, or a name that is not text "
                                f"(manifest.py check names every problem)")
        if name in jobs:
            raise ManifestError(f"{shown}: step {i}: two steps named {name!r} (manifest.py check names every problem)")
        jobs[name] = entry
    return jobs


# ---- the trace audit (ADR-037 stage 4a; build-graph-design.md 4.5): warn only, it never changes a skip

@dataclass(frozen=True)
class Declared:
    """What the trace audit needs of one step: whether Python runs it (so its trace holds its reads), its script, and
    every path or glob it declares it reads: inputs, quiet_inputs, outputs (a --check reads what it would write) and
    the programs' paths."""
    name: str
    python: bool                    # run by Python (traced); a bash step's reads are not in the job's trace
    script: str
    patterns: tuple[str, ...]


def declarations(path: Path = MANIFEST) -> dict[str, tuple[Declared, ...]]:
    """check.sh's job name -> its step as the audit sees it (Declared), as a tuple of one: every step is a job of its
    own (ADR-037 stage 4b), so each process in a job's trace is that step's. Read like job_keys, without the checks
    against git and the map (check.sh ran `jobs` before any job started), but each field the audit uses must have its
    type: otherwise a ManifestError, never an audit that quietly checks less."""
    data, shown = read(path)
    out: dict[str, tuple[Declared, ...]] = {}
    for job, entry in _jobs(data, shown).items():
        who = f"{shown}: step {job!r}"
        cmd = entry.get("cmd")
        if not isinstance(cmd, list) or not cmd or not all(isinstance(w, str) and w for w in cmd):
            raise ManifestError(f"{who}: cmd: not a list of words (manifest.py check names every problem)")
        _env, words = _split_env(cmd)
        if len(words) < 2:
            raise ManifestError(f"{who}: cmd: runs nothing (manifest.py check names every problem)")
        patterns: list[str] = []
        for key in ("inputs", "outputs", "quiet_inputs"):
            items = entry.get(key, [])
            if not isinstance(items, list):
                raise ManifestError(f"{who}: {key}: not a list (manifest.py check names every problem)")
            for item in items:
                p = item.get("path") if isinstance(item, dict) else item
                if path_problem(p):
                    raise ManifestError(f"{who}: {key}: {path_problem(p)} (manifest.py check names every problem)")
                patterns.append(p)
        programs = entry.get("programs", {})
        if not isinstance(programs, dict) or not all(isinstance(g, list) for g in programs.values()):
            raise ManifestError(f"{who}: programs: not a table of path lists (manifest.py check names every problem)")
        for globs in programs.values():
            for p in globs:
                if path_problem(p):
                    raise ManifestError(f"{who}: programs: {path_problem(p)} (manifest.py check names every problem)")
                patterns.append(p)
        out[job] = (Declared(job, words[0] != "bash", _script(tuple(cmd)), tuple(dict.fromkeys(patterns))),)
    return out


def covers(pattern: str, path: str) -> bool:
    """Whether a declared path or glob covers a repo file: the file itself, a folder above it, or a glob match."""
    if is_glob(pattern):
        return bool(glob_regex(pattern).fullmatch(path))
    return path == pattern or path.startswith(pattern + "/")


def undeclared(step: Declared, reads) -> list[str]:
    """The files of `reads` (repo paths the step's processes read as data: the code they imported or ran is left out
    before, by check_stamps.step_reads from the trace's "c" lines) that are not the step's own script and not covered
    by any path the step declares, sorted. A .py file or a file under tools/ read as data is audited like any other."""
    return sorted(r for r in set(reads) if r != step.script and not any(covers(p, r) for p in step.patterns))

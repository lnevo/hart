"""manifest_jobs.py

What tools/audit/check_stamps.py reads of checks.toml per job, without the checks against git and the map: each job's
stamp key (job_keys, ADR-037 stage 4b) and the trace audit's declarations, undeclared() and covers() (stage 4a). The
panels step stands for one job per step of panels.toml, panels-<step> (stage 6; manifest_panels.panel_check_lines).
tools/pipeline/manifest.py is the entry point and re-exports every name here.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from manifest_base import MANIFEST, ManifestError, _entries, glob_regex, is_glob, path_problem, read
from manifest_checks import _script, _split_env, git_problem
from manifest_panels import PANEL_JOB_PREFIX, PANELS, PANELS_UNAUDITED, PanelStep, panel_steps, runs_panels


@dataclass(frozen=True)
class JobKey:
    """What check.sh's stamp key takes from a job's manifest entry: a sha256 of the entry, and the git refs it names.
    `panel` is None for a step of checks.toml; for a panels job, the step's outputs and the files its programs read,
    which its key hashes whole (with make panels' code, panel_stamps.CODE), read or not, as make panels' stamps do."""
    digest: str
    git: tuple[str, ...]
    panel: tuple[str, ...] | None = None


def _digest(name: str, entry: dict, **more) -> str:
    try:
        return hashlib.sha256(json.dumps({"job": name, "step": entry, **more}, sort_keys=True, ensure_ascii=False,
                                         separators=(",", ":")).encode()).hexdigest()
    except (TypeError, ValueError) as err:     # a TOML date or time: no field of a step takes one
        raise ManifestError(f"step {name!r} holds a value JSON cannot hold (a date or time?): {err}") from err


def panel_jobs(runner: dict, path: Path, taken) -> dict[str, tuple[dict, PanelStep]]:
    """check.sh's panels jobs, panels-<step> -> (the step's panels.toml entry, its PanelStep), in file order, for the
    checks.toml step `runner` that runs build_panels.sh. panels.toml is read as build_panels.sh reads it (every field
    and the order; ManifestError otherwise). A job name that is also a step of checks.toml (`taken`) is an error."""
    data, shown = read(path)
    raw = {e.get("name"): e for e in _entries(data, shown)}
    out = {}
    for step in panel_steps(path):
        job = PANEL_JOB_PREFIX + step.name
        if job in taken:
            raise ManifestError(f"{shown}: step {step.name!r}: its check.sh job {job!r} is also a step of checks.toml")
        out[job] = (raw[step.name], step)
    return out


def job_keys(path: Path = MANIFEST, panels: Path | None = None) -> dict[str, JobKey]:
    """check.sh's job name (each step is a job of its own, named after it) -> its JobKey. tools/audit/check_stamps.py
    puts both in the job's stamp key, so an edited entry reruns its own job and no other, and a job whose entry names
    `head` reruns after every commit. Read without the checks against git and the map (check.sh ran `jobs` on the file
    before any job started, and that checks it all), but a git field the key cannot use is a ManifestError, as is an
    entry with no name, a name that is not text, or two steps of one name. The panels step's jobs (panel_jobs, from
    `panels`, by default panels.toml beside `path`) each hash their own panels.toml entry with the panels step's, and
    hold its refs plus "base" for a step that publishes (make panels keys those on the merge base too)."""
    data, shown = read(path)
    out = {}
    jobs = _jobs(data, shown)
    for name, entry in jobs.items():
        why = git_problem(entry.get("git"))
        if why:
            raise ManifestError(f"{shown}: step {name!r}: git: {why} (manifest.py check names every problem)")
        if not runs_panels(entry.get("cmd") or []):
            out[name] = JobKey(_digest(name, entry), tuple(entry["git"]))
            continue
        for job, (raw, step) in panel_jobs(entry, panels or path.with_name(PANELS.name), jobs).items():
            git = tuple(dict.fromkeys((*entry["git"], *(("base",) if step.publishes else ()))))
            hashed = (*(o.path for o in step.outputs), *(g for _, globs in step.programs for g in globs))
            out[job] = JobKey(_digest(job, raw, runner=entry), git, hashed)
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
    unaudited: str = ""             # why the job's reads are not audited at all (a panels job: PANELS_UNAUDITED)


def declarations(path: Path = MANIFEST, panels: Path | None = None) -> dict[str, tuple[Declared, ...]]:
    """check.sh's job name -> its step as the audit sees it (Declared), as a tuple of one: every step is a job of its
    own (ADR-037 stage 4b), so each process in a job's trace is that step's. Read like job_keys, without the checks
    against git and the map (check.sh ran `jobs` before any job started), but each field the audit uses must have its
    type: otherwise a ManifestError, never an audit that quietly checks less. The panels step's jobs (panel_jobs) are
    named with PANELS_UNAUDITED: their declarations are map edges, never filled from a trace."""
    data, shown = read(path)
    out: dict[str, tuple[Declared, ...]] = {}
    jobs = _jobs(data, shown)
    for job, entry in jobs.items():
        who = f"{shown}: step {job!r}"
        cmd = entry.get("cmd")
        if not isinstance(cmd, list) or not cmd or not all(isinstance(w, str) and w for w in cmd):
            raise ManifestError(f"{who}: cmd: not a list of words (manifest.py check names every problem)")
        if runs_panels(cmd):
            for name, (_raw, step) in panel_jobs(entry, panels or path.with_name(PANELS.name), jobs).items():
                pats = (*(e.path for e in (*step.inputs, *step.outputs)), *(g for _, gs in step.programs for g in gs))
                out[name] = (Declared(name, True, step.script, tuple(dict.fromkeys(pats)), PANELS_UNAUDITED),)
            continue
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

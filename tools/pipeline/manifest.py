#!/usr/bin/env python3
"""manifest.py

Load and check the step manifest, tools/pipeline/checks.toml (ADR-037; docs/pipeline-map/build-graph-design.md), and
print the lists its runners will read.

    python3 tools/pipeline/manifest.py check                       exit 1 and name each problem in the manifest
    python3 tools/pipeline/manifest.py list                        one line per step: name, group, script, edges
    python3 tools/pipeline/manifest.py jobs check [--group static | --ungrouped | --docs-only]
                                                                   one shell line per step: its name, then its command

tools/check.sh runs every step as a job of its own, named after the step (ADR-037 stage 4b): the static group's
ahead of the unit tests, the steps in no group after them; tools/ci/docs_checks.sh runs the docs-only steps. Both
stop, naming the error, when `jobs` fails. check.sh's stamps (tools/audit/check_stamps.py) key each job on its own
entry and on the git refs its `git` field names (job_keys), so an edited entry reruns that job only.

A `jobs` line is shell text for check.sh to eval: each word shell-quoted, except "{python}", which is written as
"$HOPS_PY", and an env PYTHONPATH=dir word, which is written as PYTHONPATH="dir${PYTHONPATH:+:$PYTHONPATH}" so the
caller's PYTHONPATH (the trace hook) stays on it, as check.sh writes it today. A selection with no step is an error,
so a runner reading it cannot pass with nothing run.

What the loader checks (the file's header lists the fields): the file is TOML with [[step]] tables and at least one
step; each field has its type and no other field is set; names are unique; the command is one check.sh takes
(python3, env PYTHONPATH=dir python3, or bash; "{python}" only for a step in no group) and names a tracked script,
or a -m module that is a tracked file under its PYTHONPATH; every input, output and program glob is a plain repo path
(no ./, ../, leading / or backslash) that names a tracked file or folder, or a map node marked "local"; the domain
and every edge side are the map's (docs/pipeline-map/pipeline_map.json); `git` names each ref at most once, from
GIT_REFS. Every problem is reported, each naming the file, the step and the field.

The trace audit (ADR-037 stage 4a) reads the manifest through declarations(): each job's step with every path it
declares (inputs, quiet_inputs, outputs, programs). undeclared() names the data reads its processes made that none
of those cover; tools/audit/check_stamps.py takes those reads from the trace, leaving out the code the job imported
or ran (the trace's "c" lines), and makes the report; it warns only.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import re
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tools" / "pipeline" / "checks.toml"

RUNNERS = ("check",)          # panels and manual steps come with stage 5 (panels.toml)
GROUPS = ("static",)          # the read-only checks check.sh queues ahead of the unit tests, each a job of its own
# The git refs a step's stamp key may hold (its `git` field); check_stamps.GIT_REFS says how each is read.
GIT_REFS = ("head", "base", "origin")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
PROGRAM_RE = re.compile(r"[a-z0-9][a-z0-9_.-]*")
MODULE_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
PLAIN_DIR_RE = re.compile(r"[\w./-]+")        # a PYTHONPATH folder written unquoted into the shell line
PYTHON = "{python}"                            # check.sh's $HOPS_PY
SHELL_PYTHON = '"$HOPS_PY"'
# field -> (type, required); the item lists are checked further below
FIELDS: dict[str, tuple[type, bool]] = {
    "name": (str, True), "runner": (str, True), "cmd": (list, True), "domain": (str, True), "label": (str, True),
    "desc": (str, True),
    "group": (str, False), "docs_only": (bool, False), "inputs": (list, False), "outputs": (list, False),
    "programs": (dict, False), "quiet_inputs": (list, False), "git": (list, True), "reads_all": (str, False),
}
# The globs that name every file of the repo: a scan glob a step may hold only with reads_all (_scan_problems)
WHOLE_REPO = ("**", "**/*")
EDGE_KEYS = {"inputs": ("path", "label", "side"), "outputs": ("path", "label")}


class ManifestError(Exception):
    """A manifest, or the map or git it is checked against, that cannot be used; the message says where."""


@functools.cache
def pipeline_map():
    """tools/ops/build_pipeline_map.py, loaded on first use: only the checks against the map need it, not the stamps'
    job_keys (tools/audit/check_stamps.py imports this module for every job it checks or records)."""
    spec = importlib.util.spec_from_file_location("build_pipeline_map", ROOT / "tools/ops/build_pipeline_map.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Edge:
    path: str
    label: str = ""
    side: str = ""


@dataclass(frozen=True)
class Step:
    name: str
    runner: str
    cmd: tuple[str, ...]
    domain: str
    label: str                      # the map box's name
    desc: str
    script: str                     # the file the command runs: the script, or the -m module's file
    group: str = ""
    docs_only: bool = False
    inputs: tuple[Edge, ...] = ()
    outputs: tuple[Edge, ...] = ()
    programs: tuple[tuple[str, tuple[str, ...]], ...] = ()
    quiet_inputs: tuple[str, ...] = ()          # read, not drawn on the map: for the trace audit only
    git: tuple[str, ...] = ()                   # the git refs in its stamp key (GIT_REFS)
    reads_all: str = ""                         # why its script reads every tracked file (quiet_inputs **/*)


@dataclass(frozen=True)
class Repo:
    """What a manifest is checked against: the tracked files and folders, the map's domains, edge sides and the paths
    of its nodes marked local."""
    files: frozenset[str]
    folders: frozenset[str]
    domains: frozenset[str]
    sides: frozenset[str]
    local: frozenset[str]

    @functools.cached_property
    def _sorted(self) -> tuple[str, ...]:
        return tuple(sorted(self.files | self.folders))

    def matches(self, pattern: str) -> bool:
        """Whether a path or glob names a tracked file or folder, or is a local map node's path."""
        if pattern in self.local:
            return True
        if not is_glob(pattern):
            return pattern in self.files or pattern in self.folders
        rx = glob_regex(pattern)
        return any(rx.fullmatch(p) for p in self._sorted)

    def matches_file(self, pattern: str) -> bool:
        """Whether a glob matches a tracked file (not only a folder)."""
        rx = glob_regex(pattern)
        return any(rx.fullmatch(p) for p in self.files)


def repo_from(tracked: frozenset[str] | set[str], graph: dict) -> Repo:
    """A Repo from tracked file paths (folders are derived) and the map's data as build_pipeline_map.read gives it."""
    files = frozenset(tracked)
    folders = frozenset(p.rsplit("/", k)[0] for p in files for k in range(1, p.count("/") + 1))
    domains = frozenset(d.get("id") for d in graph["domains"] if isinstance(d.get("id"), str))
    if not domains:
        raise ManifestError("the map lists no domains")
    local = frozenset(n["path"] for n in graph["nodes"] if n.get("local") is True and n.get("path"))
    overlap = files & folders
    if overlap:
        raise ManifestError(f"git lists {sorted(overlap)[0]} as a file and as a folder")
    return Repo(files, folders, domains, frozenset(pipeline_map().SIDES), local)


def tracked_files() -> frozenset[str]:
    """This checkout's tracked files (git ls-files) that are on disk; ManifestError when git fails or lists none."""
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as err:
        raise ManifestError(f"git ls-files could not run in {ROOT}: {err}") from None
    if out.returncode != 0:
        raise ManifestError(f"git ls-files failed in {ROOT}: {out.stderr.strip() or f'exit {out.returncode}'}")
    # a tracked file deleted from the checkout but not yet from the index is gone for the runner: not counted
    tracked = frozenset(p for p in out.stdout.split("\0") if p and (ROOT / p).exists())
    if not tracked:
        raise ManifestError(f"git ls-files lists no file in {ROOT}")
    return tracked


def repo() -> Repo:
    """This checkout: its tracked files (tracked_files) and the map, docs/pipeline-map/pipeline_map.json."""
    tracked = tracked_files()
    graph_map = pipeline_map()
    try:
        graph = graph_map.read(graph_map.GRAPH)
    except graph_map.GraphError as err:
        raise ManifestError(f"{_shown(graph_map.GRAPH)}: {err}") from None
    return repo_from(tracked, graph)


@functools.cache
def glob_regex(pattern: str) -> re.Pattern[str]:
    """A glob as a regex over repo paths: ** crosses folders, * and ? stay within one; anything else is literal."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:[^/]+/)*", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out)


def path_problem(path: object) -> str | None:
    """Why `path` is not a plain repo path (from the root, POSIX, no ./ or ../, no trailing /), or None."""
    if not isinstance(path, str) or not path:
        return f"{path!r} is not a path"
    if path.startswith("/") or "\\" in path:
        return f"{path} is not a path from the repo root"
    if any(part in ("", ".", "..") for part in path.split("/")):
        return f"{path} has an empty, ./ or ../ segment (write it from the repo root)"
    if path != path.strip():
        return f"{path!r} has spaces at its ends"
    return None


def _shown(path: Path) -> str:
    """`path` from the repo root when it is inside it, else as given."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def read(path: Path = MANIFEST) -> tuple[dict, str]:
    """The manifest file as TOML, unchecked, and its name for messages; ManifestError when it cannot be read."""
    shown = _shown(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise ManifestError(f"{shown}: cannot read it: {err.strerror or err}") from None
    except UnicodeDecodeError as err:
        raise ManifestError(f"{shown}: not UTF-8 text: {err}") from None
    try:
        return tomllib.loads(text), shown
    except tomllib.TOMLDecodeError as err:
        raise ManifestError(f"{shown}: not valid TOML: {err}") from None


def load(path: Path = MANIFEST, where: Repo | None = None) -> tuple[Step, ...]:
    """The manifest's steps in file order, or ManifestError listing every problem."""
    data, shown = read(path)
    return parse(data, shown, repo() if where is None else where)


def _entries(data: dict, shown: str) -> list[dict]:
    """The [[step]] tables of a manifest read as TOML, unchecked beyond that; ManifestError when there are none."""
    other = sorted(set(data) - {"step"})
    if other:
        raise ManifestError(f"{shown}: only [[step]] tables belong here, not {', '.join(other)}")
    raw = data.get("step")
    if raw is None or raw == []:
        raise ManifestError(f"{shown}: no [[step]] in it; a manifest with no steps would run nothing")
    if not isinstance(raw, list) or not all(isinstance(s, dict) for s in raw):
        raise ManifestError(f"{shown}: step must be [[step]] tables")
    return raw


def parse(data: dict, shown: str, where: Repo) -> tuple[Step, ...]:
    """The steps of a manifest already read as TOML; `shown` names the file in messages."""
    raw = _entries(data, shown)
    problems: list[str] = []
    steps: list[Step] = []
    seen: dict[str, int] = {}
    for i, entry in enumerate(raw, 1):
        name = entry.get("name")
        who = f"step {name!r}" if isinstance(name, str) and name else f"step {i}"
        bad = [f"{shown}: {who}: {msg}" for msg in _step_problems(entry, where)]
        if isinstance(name, str) and name in seen:
            bad.append(f"{shown}: {who}: name: also step {seen[name]}'s name")
        if isinstance(name, str):
            seen.setdefault(name, i)
        problems += bad
        if not bad:
            steps.append(_step(entry))
    if problems:
        raise ManifestError("\n".join(problems))
    names = [s.name for s in steps]
    if len(steps) != len(raw) or len(set(names)) != len(names):     # every entry checked became one named step
        raise ManifestError(f"{shown}: {len(raw)} [[step]] tables gave {len(set(names))} distinct steps")
    return tuple(steps)


def _step_problems(entry: dict, where: Repo) -> list[str]:
    out = []
    for key in sorted(set(entry) - set(FIELDS)):
        out.append(f"{key}: not a field (fields: {', '.join(FIELDS)})")
    for key, (kind, required) in FIELDS.items():
        if key not in entry:
            if required:
                out.append(f"{key}: missing")
        elif not isinstance(entry[key], kind) or kind is str and not entry[key].strip():
            out.append(f"{key}: must be {'true or false' if kind is bool else 'a ' + kind.__name__}"
                       f"{'' if kind is not str else ' with text'}, not {entry[key]!r}")
    if out:
        return out
    if not NAME_RE.fullmatch(entry["name"]):
        out.append(f"name: {entry['name']!r} must be lower case letters, digits and hyphens (stamps key on it)")
    if entry["name"] in GROUPS:
        out.append(f"name: {entry['name']!r} is a group's name (and the job the static group ran as until ADR-037 "
                   f"stage 4b, whose old stamps check_stamps.RETIRED drops)")
    if entry["runner"] not in RUNNERS:
        out.append(f"runner: {entry['runner']!r} is not one of {', '.join(RUNNERS)}")
    if "group" in entry and entry["group"] not in GROUPS:
        out.append(f"group: {entry['group']!r} is not one of {', '.join(GROUPS)}")
    if entry["domain"] not in where.domains:
        out.append(f"domain: {entry['domain']!r} is not a map domain ({', '.join(sorted(where.domains))})")
    out += [f"cmd: {msg}" for msg in _cmd_problems(entry["cmd"], "group" in entry, where)]
    why = git_problem(entry["git"])
    if why:
        out.append(f"git: {why}")
    for key in EDGE_KEYS:
        out += [f"{key}: {msg}" for msg in _edge_problems(entry.get(key, []), EDGE_KEYS[key], where)]
    quiet = entry.get("quiet_inputs", [])
    if not all(isinstance(p, str) for p in quiet):
        out.append("quiet_inputs: must be a list of paths (no label or side: they are not drawn)")
    else:
        out += [f"quiet_inputs: {msg}" for msg in _path_list_problems(quiet, where)]
        out += [f"quiet_inputs: {msg}" for msg in _scan_problems(quiet, entry.get("reads_all"), where)]
        drawn = {p for i in entry.get("inputs", []) for p in [i.get("path") if isinstance(i, dict) else i]
                 if isinstance(p, str)}         # a path that is no text is _edge_problems' to name
        both = sorted(set(quiet) & drawn)
        if both:
            out.append(f"quiet_inputs: {', '.join(both)} also in inputs; a read is drawn or quiet, not both")
    for prog, globs in entry.get("programs", {}).items():
        if not PROGRAM_RE.fullmatch(prog):
            out.append(f"programs: {prog!r} is not a program name")
        if not isinstance(globs, list) or not globs:
            out.append(f"programs: {prog}: must be a list of the paths it reads")
            continue
        out += [f"programs: {prog}: {msg}" for msg in _path_list_problems(globs, where)]
    return out


def _scan_problems(quiet: list[str], reads_all: str | None, where: Repo) -> list[str]:
    """Why a step's quiet_inputs globs are not a scan list the audit may trust: each glob must match a tracked file
    (a folder alone is not enough: the audit covers files), and a glob of the whole repo (WHOLE_REPO) only with the
    step's reads_all saying why the script reads every file, which then needs that glob."""
    out = []
    for p in quiet:      # one that matches nothing at all is _path_list_problems' to name
        if is_glob(p) and path_problem(p) is None and where.matches(p) and not where.matches_file(p):
            out.append(f"{p} matches tracked folders only, no file; a scan glob names the files the script reads")
    whole = [p for p in quiet if p in WHOLE_REPO]
    if whole and reads_all is None:
        out.append(f"{', '.join(whole)} is the whole repo: a step whose script reads every tracked file says why in "
                   f"reads_all; any other step lists the folders or suffixes it scans")
    if reads_all is not None and not whole:
        out.append(f"reads_all is set, so quiet_inputs must hold {WHOLE_REPO[-1]} (the script reads every file)")
    return out


def is_glob(pattern: str) -> bool:
    return any(c in pattern for c in "*?")


def git_problem(refs: object) -> str | None:
    """Why `refs` is not a step's git field (a list of distinct names from GIT_REFS, [] for none), or None."""
    if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
        return f"{refs!r} must be a list of ref names ({', '.join(GIT_REFS)}), [] for none"
    bad = [r for r in refs if r not in GIT_REFS]
    if bad:
        return f"{', '.join(map(repr, bad))}: not a ref name ({', '.join(GIT_REFS)})"
    if len(set(refs)) != len(refs):
        return f"{refs!r} names a ref twice"
    return None


def _path_list_problems(paths: list, where: Repo) -> list[str]:
    out = []
    for p in paths:
        why = path_problem(p)
        if why:
            out.append(why)
        elif not where.matches(p):
            out.append(f"{p} names no tracked file or folder and no map node marked local")
    dup = sorted({p for p in paths if isinstance(p, str) and paths.count(p) > 1})
    if dup:
        out.append(f"{', '.join(dup)} listed twice")
    return out


def _edge_problems(items: list, keys: tuple[str, ...], where: Repo) -> list[str]:
    out, paths = [], []
    for item in items:
        if isinstance(item, dict):
            extra = sorted(set(item) - set(keys))
            if extra:
                out.append(f"{item!r}: {', '.join(extra)} not allowed here (keys: {', '.join(keys)})")
            for key in ("label", "side"):
                if key in item and (not isinstance(item[key], str) or not item[key].strip()):
                    out.append(f"{item!r}: {key} must be text")
            if isinstance(item.get("side"), str) and item["side"] not in where.sides:
                out.append(f"{item!r}: side {item['side']!r} is not a map edge side ({', '.join(sorted(where.sides))})")
            if "path" not in item:
                out.append(f"{item!r}: no path")
                continue
            paths.append(item["path"])
        else:
            paths.append(item)
    return out + _path_list_problems(paths, where)


def _split_env(cmd: tuple[str, ...] | list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """A command's leading `env VAR=value ...` assignments, and the words after them."""
    words = list(cmd)
    if words[0] != "env":
        return [], words
    env, rest = [], words[1:]
    while rest and "=" in rest[0]:
        var, _, value = rest.pop(0).partition("=")
        env.append((var, value))
    return env, rest


def _cmd_problems(cmd: list, grouped: bool, where: Repo) -> list[str]:
    """Why `cmd` is not a command check.sh can run as this step, or []. grouped: a static check, which check.sh's
    run_check runs."""
    if not cmd or not all(isinstance(w, str) and w.strip() for w in cmd):
        return [f"{cmd!r} must be a list of words, none empty"]
    assigned, words = _split_env(cmd)
    if cmd[0] == "env" and not assigned:
        return ["env sets nothing; drop it or give PYTHONPATH=dir"]
    if [var for var, _ in assigned] not in ([], ["PYTHONPATH"]):
        return [f"env sets {', '.join(v for v, _ in assigned)}; only one PYTHONPATH=dir is taken (check.sh keeps "
                f"the caller's after it)"]
    env = dict(assigned)
    if not words:
        return ["no program after env"]
    prog, rest = words[0], words[1:]
    if prog == PYTHON and grouped:
        return [f"{PYTHON} ($HOPS_PY) is for a step in no group; check.sh's run_check runs a static check with "
                f"python3 or bash"]
    if prog == "bash" and env:
        return ["env ... bash: check.sh's run_check takes env only before python3"]
    if prog not in ("python3", PYTHON, "bash"):
        return [f"runs {prog}; check.sh takes python3, {PYTHON}, env PYTHONPATH=dir python3 or bash"]
    out = []
    pp = env.get("PYTHONPATH")
    if pp is not None:
        why = path_problem(pp)
        if why or not PLAIN_DIR_RE.fullmatch(pp):
            out.append(f"PYTHONPATH: {why or f'{pp} must be one folder, plain letters, digits, . _ / -'}")
        elif pp not in where.folders:
            out.append(f"PYTHONPATH: {pp} is not a tracked folder")
    if not rest:
        return out + [f"{prog} runs nothing (no script or -m module)"]
    if prog != "bash" and rest[0] == "-m":
        mod = rest[1] if len(rest) > 1 else ""
        if not MODULE_RE.fullmatch(mod):
            return out + [f"-m {mod!r} is not a module name"]
        if pp is None:
            return out + [f"-m {mod} needs env PYTHONPATH=dir to say where the module is"]
        if not out and f"{pp}/{mod.replace('.', '/')}.py" not in where.files:
            out.append(f"-m {mod}: {pp}/{mod.replace('.', '/')}.py is not a tracked file")
    else:
        script, suffix = rest[0], ".sh" if prog == "bash" else ".py"
        why = path_problem(script)
        if why:
            out.append(why)
        elif not script.endswith(suffix):
            out.append(f"{prog} runs {script}, not a {suffix} file")
        elif script not in where.files:
            out.append(f"{script} is not a tracked file (a new script needs git add; a deleted one is gone)")
    stray = [w for w in rest if w.startswith("{") and w.endswith("}")]
    if stray:
        out.append(f"{', '.join(stray)}: only {PYTHON} is a placeholder, and only as the program")
    return out


def _edges(items: list) -> tuple[Edge, ...]:
    return tuple(Edge(i, "", "") if isinstance(i, str) else Edge(i["path"], i.get("label", ""), i.get("side", ""))
                 for i in items)


def _script(cmd: tuple[str, ...]) -> str:
    """The file a checked command runs (the -m module as its file under PYTHONPATH)."""
    env, words = _split_env(cmd)
    if words[1] == "-m":
        return f"{dict(env)['PYTHONPATH']}/{words[2].replace('.', '/')}.py"
    return words[1]


def _step(entry: dict) -> Step:
    cmd = tuple(entry["cmd"])
    return Step(
        name=entry["name"], runner=entry["runner"], cmd=cmd, domain=entry["domain"], label=entry["label"],
        desc=entry["desc"],
        script=_script(cmd), group=entry.get("group", ""), docs_only=entry.get("docs_only", False),
        inputs=_edges(entry.get("inputs", [])), outputs=_edges(entry.get("outputs", [])),
        programs=tuple((p, tuple(g)) for p, g in entry.get("programs", {}).items()),
        quiet_inputs=tuple(entry.get("quiet_inputs", ())), git=tuple(entry["git"]),
        reads_all=entry.get("reads_all", ""),
    )


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


def shell_line(step: Step) -> str:
    """The step as one shell line for check.sh to eval: its name, then its command (see the module docstring)."""
    env, rest = _split_env(step.cmd)
    words = ["env"] if env else []
    words += [f'PYTHONPATH="{value}${{PYTHONPATH:+:$PYTHONPATH}}"' for _, value in env]
    words += [SHELL_PYTHON if w == PYTHON else shlex.quote(w) for w in rest]
    return " ".join([shlex.quote(step.name), *words])


def select(steps: tuple[Step, ...], runner: str, group: str | None = None, ungrouped: bool = False,
           docs_only: bool = False) -> tuple[Step, ...]:
    """The steps of `runner`, in file order: those of `group`, those in no group, or those on the docs-only path.
    ManifestError when none is left, so a runner reading the list cannot pass having run nothing."""
    if runner not in RUNNERS:
        raise ManifestError(f"runner {runner!r} is not one of {', '.join(RUNNERS)}")
    if group is not None and group not in GROUPS:
        raise ManifestError(f"group {group!r} is not one of {', '.join(GROUPS)}")
    chosen = tuple(s for s in steps if s.runner == runner
                   and (group is None or s.group == group)
                   and (not ungrouped or not s.group)
                   and (not docs_only or s.docs_only))
    if not chosen:
        raise ManifestError(f"no {runner} step matches (group {group}, ungrouped {ungrouped}, docs-only {docs_only})")
    return chosen


# make panels' steps: tools/pipeline/panels.toml (ADR-037 stage 5). Its header lists the fields.
PANELS = ROOT / "tools" / "pipeline" / "panels.toml"
PANELS_RUNNER = "tools/schematic/build_panels.sh"     # runs the panels steps; the map box of checks.toml's panels step
PANEL_MODES = ("step", "guard")
PANEL_WORD_RE = re.compile(r"[A-Za-z0-9_./=-]+")     # build_panels.sh splits a jobs line on spaces, with no quoting
PANEL_FIELDS: dict[str, tuple[type, bool]] = {
    "name": (str, True), "mode": (str, True), "cmd": (list, True), "check_args": (list, True),
    "box": (str, False), "domain": (str, False), "label": (str, False), "desc": (str, False),
    "inputs": (list, False), "outputs": (list, False), "updates": (list, False), "programs": (dict, False),
    "publishes": (bool, False),
}
PANEL_BOX_TEXT = ("domain", "label", "desc")
PANEL_EDGE_KEYS = {"inputs": ("path", "label", "side", "written_later"), "outputs": ("path", "label", "drawn")}


@dataclass(frozen=True)
class PanelStep:
    name: str
    mode: str                       # "step" (writes; stamped) or "guard" (checks only; always runs)
    cmd: tuple[str, ...]
    check_args: tuple[str, ...]     # what --check adds to cmd
    script: str                     # the file cmd runs
    box: str                        # the map box it is drawn in: the script's, unless the step names another
    domain: str = ""                # the box's text: set on the first step of each box only
    label: str = ""
    desc: str = ""
    inputs: tuple[Edge, ...] = ()
    outputs: tuple[Edge, ...] = ()
    updates: tuple[str, ...] = ()
    programs: tuple[tuple[str, tuple[str, ...]], ...] = ()
    publishes: bool = False
    written_later: tuple[tuple[str, tuple[str, ...]], ...] = ()     # input path -> steps that write it later
    undrawn: tuple[str, ...] = ()   # outputs the map leaves out (drawn = false): stamped, not drawn


def load_panels(path: Path = PANELS, where: Repo | None = None) -> tuple[PanelStep, ...]:
    """panels.toml's steps in file order, checked against git and the map as well (tracked paths, domains, edge
    sides); ManifestError listing every problem. manifest.py check and the map lane load it this way."""
    data, shown = read(path)
    return parse_panels(data, shown, repo() if where is None else where)


def panel_steps(path: Path = PANELS) -> tuple[PanelStep, ...]:
    """panels.toml's steps in file order, checked without git or the map: every field, the order (writers before
    readers), and each command's script on disk. build_panels.sh (through `jobs panels`) and panel_stamps.py read it
    this way, so a scratch checkout with stub scripts runs; the full checks run in check.sh's map and manifest checks."""
    data, shown = read(path)
    return parse_panels(data, shown, None)


def parse_panels(data: dict, shown: str, where: Repo | None) -> tuple[PanelStep, ...]:
    """The steps of a panels manifest read as TOML; `where` None checks the file alone, with scripts on disk."""
    raw = _entries(data, shown)
    problems: list[str] = []
    steps: list[PanelStep] = []
    seen: dict[str, int] = {}
    boxes: dict[str, PanelStep] = {}            # box -> its first step, which carries the box's text
    for i, entry in enumerate(raw, 1):
        name = entry.get("name")
        who = f"{shown}: step {name!r}" if isinstance(name, str) and name else f"{shown}: step {i}"
        bad = [f"{who}: {msg}" for msg in _panel_problems(entry, where)]
        if isinstance(name, str) and name in seen:
            bad.append(f"{who}: name: also step {seen[name]}'s name")
        if isinstance(name, str):
            seen.setdefault(name, i)
        if not bad:
            step = _panel_step(entry)
            first = boxes.setdefault(step.box, step)
            text = [k for k in PANEL_BOX_TEXT if k in entry]
            if first is step and len(text) != len(PANEL_BOX_TEXT):
                bad.append(f"{who}: {', '.join(k for k in PANEL_BOX_TEXT if k not in entry)}: missing (the first "
                           f"step drawn in box {step.box} gives its {', '.join(PANEL_BOX_TEXT)})")
            elif first is not step and text:
                bad.append(f"{who}: {', '.join(text)}: step {first.name!r} gives box {step.box}'s text; drop it here")
            if first.script != step.script:
                bad.append(f"{who}: box: {step.box} is the box of step {first.name!r}, which runs {first.script}, not "
                           f"{step.script}")
            if where is not None and first is step and step.domain not in where.domains:
                bad.append(f"{who}: domain: {step.domain!r} is not a map domain ({', '.join(sorted(where.domains))})")
            steps.append(step)
        problems += bad
    if problems:
        raise ManifestError("\n".join(problems))
    problems = [f"{shown}: {msg}" for msg in panel_order_problems(steps)]
    if problems:
        raise ManifestError("\n".join(problems))
    if len(steps) != len(raw) or len({s.name for s in steps}) != len(raw):
        raise ManifestError(f"{shown}: {len(raw)} [[step]] tables gave {len({s.name for s in steps})} distinct steps")
    return tuple(steps)


def _panel_problems(entry: dict, where: Repo | None) -> list[str]:
    out = []
    for key in sorted(set(entry) - set(PANEL_FIELDS)):
        out.append(f"{key}: not a field (fields: {', '.join(PANEL_FIELDS)})")
    for key, (kind, required) in PANEL_FIELDS.items():
        if key not in entry:
            if required:
                out.append(f"{key}: missing")
        elif not isinstance(entry[key], kind) or kind is str and not entry[key].strip():
            out.append(f"{key}: must be {'true or false' if kind is bool else 'a ' + kind.__name__}"
                       f"{'' if kind is not str else ' with text'}, not {entry[key]!r}")
    if out:
        return out
    if not NAME_RE.fullmatch(entry["name"]):
        out.append(f"name: {entry['name']!r} must be lower case letters, digits and hyphens (stamps key on it)")
    if entry["mode"] not in PANEL_MODES:
        out.append(f"mode: {entry['mode']!r} is not one of {', '.join(PANEL_MODES)}")
    cmd, check_args = entry["cmd"], entry["check_args"]
    words_bad = [w for w in (*cmd, *check_args) if not isinstance(w, str) or not PANEL_WORD_RE.fullmatch(w)]
    if words_bad:
        out.append(f"cmd, check_args: {words_bad!r}: each word must be letters, digits and . _ / = - (build_panels.sh "
                   f"splits the line on spaces)")
    elif len(cmd) < 2 or cmd[0] != "python3":
        out.append(f"cmd: {cmd!r} must be python3 and a script, then its arguments")
    else:
        script = cmd[1]
        why = path_problem(script)
        if why:
            out.append(f"cmd: {why}")
        elif not script.endswith(".py"):
            out.append(f"cmd: python3 runs {script}, not a .py file")
        elif where is None and not (ROOT / script).is_file():
            out.append(f"cmd: {script} is not a file in {ROOT}")
        elif where is not None and script not in where.files:
            out.append(f"cmd: {script} is not a tracked file (a new script needs git add; a deleted one is gone)")
        if "box" in entry:
            box = entry["box"]
            why = path_problem(box)
            if why or box == script:
                out.append(f"box: {why or f'{box} is the script cmd runs; drop box'}")
            elif where is not None and box not in where.files:
                out.append(f"box: {box} is not a tracked file")
    for key in PANEL_EDGE_KEYS:
        out += [f"{key}: {msg}" for msg in _panel_edge_problems(entry.get(key, []), key, where)]
    outputs = {i if isinstance(i, str) else i.get("path") for i in entry.get("outputs", [])
               if isinstance(i, (str, dict))}       # any other item is named by _panel_edge_problems above
    updates = entry.get("updates", [])
    out += [f"updates: {msg}" for msg in _panel_paths_problems(updates, where)]
    out += [f"updates: {p} is not one of the step's outputs" for p in updates if isinstance(p, str) and p not in outputs]
    for prog, globs in entry.get("programs", {}).items():
        if not PROGRAM_RE.fullmatch(prog):
            out.append(f"programs: {prog!r} is not a program name")
        if not isinstance(globs, list):
            out.append(f"programs: {prog}: must be a list of the paths it reads ([] for none)")
            continue
        out += [f"programs: {prog}: {msg}" for msg in _panel_paths_problems(globs, where)]
    return out


def _panel_paths_problems(paths: list, where: Repo | None) -> list[str]:
    """Why a list of paths or globs is not plain repo paths (and, with `where`, tracked or local ones)."""
    if where is not None:
        return _path_list_problems(paths, where)
    out = [why for why in map(path_problem, paths) if why]
    dup = sorted({p for p in paths if isinstance(p, str) and paths.count(p) > 1})
    return out + ([f"{', '.join(dup)} listed twice"] if dup else [])


def _panel_edge_problems(items: list, field: str, where: Repo | None) -> list[str]:
    keys = PANEL_EDGE_KEYS[field]
    out, paths = [], []
    for item in items:
        if not isinstance(item, dict):
            paths.append(item)
            continue
        extra = sorted(set(item) - set(keys))
        if extra:
            out.append(f"{item!r}: {', '.join(extra)} not allowed here (keys: {', '.join(keys)})")
        for key in ("label", "side"):
            if key in item and (not isinstance(item[key], str) or not item[key].strip()):
                out.append(f"{item!r}: {key} must be text")
        if where is not None and isinstance(item.get("side"), str) and item["side"] not in where.sides:
            out.append(f"{item!r}: side {item['side']!r} is not a map edge side ({', '.join(sorted(where.sides))})")
        later = item.get("written_later")
        if "written_later" in item and (not isinstance(later, list) or not later
                                        or not all(isinstance(n, str) and n for n in later)):
            out.append(f"{item!r}: written_later must be a list of step names")
        if "drawn" in item and item["drawn"] is not False:
            out.append(f"{item!r}: drawn is only ever false (an output the map leaves out)")
        if "path" not in item:
            out.append(f"{item!r}: no path")
            continue
        paths.append(item["path"])
    return out + _panel_paths_problems(paths, where)


def _panel_step(entry: dict) -> PanelStep:
    cmd = tuple(entry["cmd"])
    inputs = entry.get("inputs", [])
    return PanelStep(
        name=entry["name"], mode=entry["mode"], cmd=cmd, check_args=tuple(entry["check_args"]), script=cmd[1],
        box=entry.get("box", cmd[1]), domain=entry.get("domain", ""), label=entry.get("label", ""),
        desc=entry.get("desc", ""), inputs=_edges(inputs), outputs=_edges(entry.get("outputs", [])),
        updates=tuple(entry.get("updates", [])),
        programs=tuple((p, tuple(g)) for p, g in entry.get("programs", {}).items()),
        publishes=entry.get("publishes", False),
        written_later=tuple((i["path"], tuple(i["written_later"])) for i in inputs
                            if isinstance(i, dict) and "written_later" in i),
        undrawn=tuple(o["path"] for o in entry.get("outputs", []) if isinstance(o, dict) and "drawn" in o),
    )


def _overlap(a: str, b: str) -> bool:
    """Whether two paths or globs can name one file."""
    return a == b or bool(glob_regex(a).fullmatch(b)) or bool(glob_regex(b).fullmatch(a))


def panel_order_problems(steps) -> list[str]:
    """Why the steps' file order is not one make panels can run, or []. Each writer of a file a step reads comes
    before it, unless the step updates that file itself or names the writer in the input's written_later; two steps
    write one file only when both list it in updates; a written_later name is a step that writes that file later."""
    out = []
    index = {s.name: i for i, s in enumerate(steps)}
    for i, a in enumerate(steps):
        for b in steps[i + 1:]:
            for oa in a.outputs:
                for ob in b.outputs:
                    if _overlap(oa.path, ob.path) and not (oa.path in a.updates and ob.path in b.updates):
                        out.append(f"steps {a.name!r} and {b.name!r} both write {ob.path}; list it in both steps' "
                                   f"updates when each rewrites only its part")
    for r, reader in enumerate(steps):
        later = dict(reader.written_later)
        for item in reader.inputs:
            named = later.get(item.path, ())
            writers = [(w, s) for w, s in enumerate(steps) if any(_overlap(o.path, item.path) for o in s.outputs)]
            for n in named:
                if n not in index:
                    out.append(f"step {reader.name!r}: inputs: {item.path}: written_later names {n!r}, no step")
                elif n not in {s.name for _, s in writers} or index[n] <= r:
                    out.append(f"step {reader.name!r}: inputs: {item.path}: written_later names {n!r}, which does "
                               f"not write it after this step; drop it")
            if item.path in reader.updates:
                continue                        # it rewrites its own part and carries the others' over
            for w, writer in writers:
                if w >= r and writer.name not in named:
                    where = "itself" if w == r else f"later (step {w + 1})"
                    out.append(f"step {reader.name!r} (step {r + 1}) reads {item.path}, which {writer.name!r} writes "
                               f"{where}; run the writer first, or name it in the input's written_later (or list the "
                               f"file in updates, for a step that reads what it writes)")
    return out


def panel_lines(steps) -> list[str]:
    """build_panels.sh's lines, one per step: mode, name, how many check_args, the check_args, then cmd. Words are
    plain (PANEL_WORD_RE), so the script splits each line on spaces. ManifestError on no step."""
    if not steps:
        raise ManifestError("no panels step; make panels would run nothing")
    return [" ".join((s.mode, s.name, str(len(s.check_args)), *s.check_args, *s.cmd)) for s in steps]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--manifest", type=Path, default=MANIFEST, help=f"default {_shown(MANIFEST)}")
    ap.add_argument("--panels", type=Path, default=PANELS, help=f"default {_shown(PANELS)}")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="check both manifests; exit 1 naming each problem")
    sub.add_parser("list", help="one line per step: name, runner, group, docs-only, domain, script, edge counts")
    jobs = sub.add_parser("jobs", help="one shell line per step of RUNNER: its name, then its command")
    jobs.add_argument("runner", choices=(*RUNNERS, "panels"))
    which = jobs.add_mutually_exclusive_group()
    which.add_argument("--group", choices=GROUPS)
    which.add_argument("--ungrouped", action="store_true", help="the steps that are jobs of their own")
    which.add_argument("--docs-only", action="store_true", help="the steps on the docs-only path")
    args = ap.parse_args(argv)
    try:
        if args.command == "jobs" and args.runner == "panels":
            if args.group or args.ungrouped or args.docs_only:
                raise ManifestError("jobs panels takes no --group, --ungrouped or --docs-only")
            print("\n".join(panel_lines(panel_steps(args.panels))))
            return 0
        steps = load(args.manifest)
        if args.command == "jobs":
            lines = [shell_line(s) for s in select(steps, args.runner, args.group, args.ungrouped, args.docs_only)]
        elif args.command == "list":
            lines = ["\t".join((s.name, s.runner, s.group or "-", "docs" if s.docs_only else "-", s.domain, s.script,
                                f"{len(s.inputs)} in", f"{len(s.outputs)} out")) for s in steps]
        else:
            lines = [f"{_shown(args.manifest)}: {len(steps)} steps, all checked",
                     f"{_shown(args.panels)}: {len(load_panels(args.panels))} steps, all checked"]
    except ManifestError as err:
        print(f"manifest.py: {err}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())

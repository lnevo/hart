"""manifest_checks.py

The check runner's manifest, tools/pipeline/checks.toml (ADR-037): its fields, Step, the loader that checks every
entry against git and the map, and what check.sh's `jobs` lines are made from (shell_line, select).
tools/pipeline/manifest.py is the entry point and re-exports every name here (its docstring says what is checked).
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from manifest_base import (MANIFEST, NAME_RE, PROGRAM_RE, Edge, ManifestError, Repo, _edges, _entries,
                           _path_list_problems, glob_regex, is_glob, path_problem, read, repo)

RUNNERS = ("check",)          # panels and manual steps come with stage 5 (panels.toml)
GROUPS = ("static",)          # the read-only checks check.sh queues ahead of the unit tests, each a job of its own
# The git refs a step's stamp key may hold (its `git` field); check_stamps.GIT_REFS says how each is read.
GIT_REFS = ("head", "base", "origin")
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


def load(path: Path = MANIFEST, where: Repo | None = None) -> tuple[Step, ...]:
    """The manifest's steps in file order, or ManifestError listing every problem."""
    data, shown = read(path)
    return parse(data, shown, repo() if where is None else where)



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
    whole = [p for p in quiet if p in WHOLE_REPO or is_glob(p) and path_problem(p) is None
             and all(glob_regex(p).fullmatch(f) for f in where.files)]          # **/** names every file too
    if whole and reads_all is None:
        out.append(f"{', '.join(whole)} is the whole repo: a step whose script reads every tracked file says why in "
                   f"reads_all; any other step lists the folders or suffixes it scans")
    if reads_all is not None and not whole:
        out.append(f"reads_all is set, so quiet_inputs must hold {WHOLE_REPO[-1]} (the script reads every file)")
    return out



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

#!/usr/bin/env python3
"""manifest.py

Load and check the step manifest, tools/pipeline/checks.toml (ADR-037; docs/pipeline-map/build-graph-design.md), and
print the lists its runners will read.

    python3 tools/pipeline/manifest.py check                       exit 1 and name each problem in the manifest
    python3 tools/pipeline/manifest.py list                        one line per step: name, group, script, edges
    python3 tools/pipeline/manifest.py jobs check [--group static | --ungrouped | --docs-only]
                                                                   one shell line per step: its name, then its command

Stage 1: nothing runs from these lists yet. tools/check.sh and tools/ci/docs_checks.sh keep their own, and
tools/audit/tests/test_pipeline_manifest.py checks the three agree until stage 2 makes them read `jobs`.

A `jobs` line is shell text for check.sh to eval: each word shell-quoted, except "{python}", which is written as
"$HOPS_PY", and an env PYTHONPATH=dir word, which is written as PYTHONPATH="dir${PYTHONPATH:+:$PYTHONPATH}" so the
caller's PYTHONPATH (the trace hook) stays on it, as check.sh writes it today. A selection with no step is an error,
so a runner reading it cannot pass with nothing run.

What the loader checks (the file's header lists the fields): the file is TOML with [[step]] tables and at least one
step; each field has its type and no other field is set; names are unique; the command is one check.sh's run() takes
(python3, env PYTHONPATH=dir python3, or bash; "{python}" only for a job of its own) and names a tracked script, or a
-m module that is a tracked file under its PYTHONPATH; every input, output and program glob is a plain repo path
(no ./, ../, leading / or backslash) that names a tracked file or folder, or a map node marked "local"; the domain
and every edge side are the map's (docs/pipeline-map/pipeline_map.json). Every problem is reported, each naming the
file, the step and the field.
"""
from __future__ import annotations

import argparse
import functools
import importlib.util
import re
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tools" / "pipeline" / "checks.toml"
_spec = importlib.util.spec_from_file_location("build_pipeline_map", ROOT / "tools/ops/build_pipeline_map.py")
MAP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MAP)

RUNNERS = ("check",)          # panels and manual steps come with stage 5 (panels.toml)
GROUPS = ("static",)          # check.sh's one job that runs its checks one after another
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
PROGRAM_RE = re.compile(r"[a-z0-9][a-z0-9_.-]*")
MODULE_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
PLAIN_DIR_RE = re.compile(r"[\w./-]+")        # a PYTHONPATH folder written unquoted into the shell line
PYTHON = "{python}"                            # check.sh's $HOPS_PY
SHELL_PYTHON = '"$HOPS_PY"'
# field -> (type, required); the item lists are checked further below
FIELDS: dict[str, tuple[type, bool]] = {
    "name": (str, True), "runner": (str, True), "cmd": (list, True), "domain": (str, True), "desc": (str, True),
    "group": (str, False), "docs_only": (bool, False), "inputs": (list, False), "outputs": (list, False),
    "programs": (dict, False),
}
EDGE_KEYS = {"inputs": ("path", "label", "side"), "outputs": ("path", "label")}


class ManifestError(Exception):
    """A manifest, or the map or git it is checked against, that cannot be used; the message says where."""


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
    desc: str
    script: str                     # the file the command runs: the script, or the -m module's file
    group: str = ""
    docs_only: bool = False
    inputs: tuple[Edge, ...] = ()
    outputs: tuple[Edge, ...] = ()
    programs: tuple[tuple[str, tuple[str, ...]], ...] = ()


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
        if not any(c in pattern for c in "*?"):
            return pattern in self.files or pattern in self.folders
        rx = glob_regex(pattern)
        return any(rx.fullmatch(p) for p in self._sorted)


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
    return Repo(files, folders, domains, frozenset(MAP.SIDES), local)


def repo() -> Repo:
    """This checkout: its tracked files (git ls-files) and the map, docs/pipeline-map/pipeline_map.json."""
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as err:
        raise ManifestError(f"git ls-files could not run in {ROOT}: {err}") from None
    if out.returncode != 0:
        raise ManifestError(f"git ls-files failed in {ROOT}: {out.stderr.strip() or f'exit {out.returncode}'}")
    tracked = frozenset(filter(None, out.stdout.split("\0")))
    if not tracked:
        raise ManifestError(f"git ls-files lists no file in {ROOT}")
    try:
        graph = MAP.read(MAP.GRAPH)
    except MAP.GraphError as err:
        raise ManifestError(f"{_shown(MAP.GRAPH)}: {err}") from None
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


def load(path: Path = MANIFEST, where: Repo | None = None) -> tuple[Step, ...]:
    """The manifest's steps in file order, or ManifestError listing every problem."""
    shown = _shown(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise ManifestError(f"{shown}: cannot read it: {err.strerror or err}") from None
    except UnicodeDecodeError as err:
        raise ManifestError(f"{shown}: not UTF-8 text: {err}") from None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        raise ManifestError(f"{shown}: not valid TOML: {err}") from None
    return parse(data, shown, repo() if where is None else where)


def parse(data: dict, shown: str, where: Repo) -> tuple[Step, ...]:
    """The steps of a manifest already read as TOML; `shown` names the file in messages."""
    other = sorted(set(data) - {"step"})
    if other:
        raise ManifestError(f"{shown}: only [[step]] tables belong here, not {', '.join(other)}")
    raw = data.get("step")
    if raw is None or raw == []:
        raise ManifestError(f"{shown}: no [[step]] in it; a manifest with no steps would run nothing")
    if not isinstance(raw, list) or not all(isinstance(s, dict) for s in raw):
        raise ManifestError(f"{shown}: step must be [[step]] tables")
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
    if entry["runner"] not in RUNNERS:
        out.append(f"runner: {entry['runner']!r} is not one of {', '.join(RUNNERS)}")
    if "group" in entry and entry["group"] not in GROUPS:
        out.append(f"group: {entry['group']!r} is not one of {', '.join(GROUPS)}")
    if entry["domain"] not in where.domains:
        out.append(f"domain: {entry['domain']!r} is not a map domain ({', '.join(sorted(where.domains))})")
    out += [f"cmd: {msg}" for msg in _cmd_problems(entry["cmd"], "group" in entry, where)]
    for key in EDGE_KEYS:
        out += [f"{key}: {msg}" for msg in _edge_problems(entry.get(key, []), EDGE_KEYS[key], where)]
    for prog, globs in entry.get("programs", {}).items():
        if not PROGRAM_RE.fullmatch(prog):
            out.append(f"programs: {prog!r} is not a program name")
        if not isinstance(globs, list) or not globs:
            out.append(f"programs: {prog}: must be a list of the paths it reads")
            continue
        out += [f"programs: {prog}: {msg}" for msg in _path_list_problems(globs, where)]
    return out


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
    """Why `cmd` is not a command check.sh can run as this step, or []. grouped: run inside the static job."""
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
        return [f"{PYTHON} ($HOPS_PY) is for a job of its own; check.sh's static checks run python3 or bash"]
    if prog == "bash" and env:
        return ["env ... bash: check.sh's run() takes env only before python3"]
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
            out.append(f"{script} is not a tracked file")
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
        name=entry["name"], runner=entry["runner"], cmd=cmd, domain=entry["domain"], desc=entry["desc"],
        script=_script(cmd), group=entry.get("group", ""), docs_only=entry.get("docs_only", False),
        inputs=_edges(entry.get("inputs", [])), outputs=_edges(entry.get("outputs", [])),
        programs=tuple((p, tuple(g)) for p, g in entry.get("programs", {}).items()),
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--manifest", type=Path, default=MANIFEST, help=f"default {_shown(MANIFEST)}")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="check the manifest; exit 1 naming each problem")
    sub.add_parser("list", help="one line per step: name, runner, group, docs-only, domain, script, edge counts")
    jobs = sub.add_parser("jobs", help="one shell line per step of RUNNER: its name, then its command")
    jobs.add_argument("runner", choices=RUNNERS)
    which = jobs.add_mutually_exclusive_group()
    which.add_argument("--group", choices=GROUPS)
    which.add_argument("--ungrouped", action="store_true", help="the steps that are jobs of their own")
    which.add_argument("--docs-only", action="store_true", help="the steps on the docs-only path")
    args = ap.parse_args(argv)
    try:
        steps = load(args.manifest)
        if args.command == "jobs":
            lines = [shell_line(s) for s in select(steps, args.runner, args.group, args.ungrouped, args.docs_only)]
        elif args.command == "list":
            lines = ["\t".join((s.name, s.runner, s.group or "-", "docs" if s.docs_only else "-", s.domain, s.script,
                                f"{len(s.inputs)} in", f"{len(s.outputs)} out")) for s in steps]
        else:
            lines = [f"{_shown(args.manifest)}: {len(steps)} steps, all checked"]
    except ManifestError as err:
        print(f"manifest.py: {err}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())

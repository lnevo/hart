"""manifest_base.py

What both step manifests (tools/pipeline/checks.toml and panels.toml) are read and checked with: ManifestError, the
Edge every input and output becomes, the Repo of tracked files and map facts the paths are checked against, the glob
and path rules, and reading a manifest file's [[step]] tables. tools/pipeline/manifest.py is the entry point and
re-exports every name here; load it, not this module (its docstring says what the loader checks).
"""
from __future__ import annotations

import functools
import importlib.util
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import files  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tools" / "pipeline" / "checks.toml"
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
PROGRAM_RE = re.compile(r"[a-z0-9][a-z0-9_.-]*")


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
        listed = files.tracked_files(ROOT)
    except files.GitError as err:
        raise ManifestError(str(err)) from None
    # a tracked file deleted from the checkout but not yet from the index is gone for the runner: not counted
    tracked = frozenset(p for p in listed if (ROOT / p).exists())
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


def is_glob(pattern: str) -> bool:
    return any(c in pattern for c in "*?")


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


def _edges(items: list) -> tuple[Edge, ...]:
    return tuple(Edge(i, "", "") if isinstance(i, str) else Edge(i["path"], i.get("label", ""), i.get("side", ""))
                 for i in items)

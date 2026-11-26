"""The shared ground of tools/audit/check_stamps.py: the modules the stamps are made with (panel_stamps, traced, the
step manifest's loader, hartlib.paths), the walk of a pattern set, the file-hash cache, the interpreters' state and
the Checker that works out once what is the same for every job of a check.sh run. check_stamps.py is the entry point
and the CLI; it imports this file and stamps_audit.py from its own folder and re-exports every name, so callers keep
using check_stamps.<name>. An edit here reruns the same jobs an edit to check_stamps.py does (check_stamps.FILES).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from functools import partial
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, TypeVar, cast

if TYPE_CHECKING:
    # pm below is the same file loaded by path; this import gives mypy its types only
    from tools.pipeline.manifest_jobs import JobKey

T = TypeVar("T")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "schematic"))
import panel_stamps as ps  # noqa: E402

traced = ps.traced
sys.path[:0] = [str(ROOT / "tools/hartlib/src")]
from hartlib.paths import cache_dir, main_checkout  # noqa: E402,F401 - check_stamps' STORE and record use them


def _import(name: str, path: Path) -> ModuleType:
    """The module at `path` under `name`, loaded once per process (its dataclasses look it up in sys.modules)."""
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


pm = _import("pipeline_manifest", ROOT / "tools/pipeline/manifest.py")
MANIFEST = pm.MANIFEST.relative_to(pm.ROOT)     # tools/pipeline/checks.toml, under each Checker's root

PRUNE = {".git", ".cache", "__pycache__", "node_modules", ".venv", "venv", ".pages-dist", ".mypy_cache", ".pytest_cache"}
PRUNE_PATHS = {".claude/worktrees", "external/model-railroad-skills"}     # the plugin is stamped by its commit
LITTER = (".DS_Store", ".pyc")


def _pruned(rel: str) -> bool:
    return any(rel == p or rel.startswith(p + "/") for p in PRUNE_PATHS)


def walk(patterns: Iterable[str], root: Path = ROOT) -> list[Path]:
    """Every file under `root` the patterns name, sorted; caches, VCS data, other worktrees and the plugin left out.
    Linked folders (media/, ops/car-cards in a worktree) are walked through their links, whatever the pattern."""
    heads = set()
    for pat in patterns:
        # a literal pattern ("tools/check.sh") starts at itself, not at its folder: no walk of all of tools/ for it
        if not any(c in pat for c in "*?"):
            heads.add(pat)
            continue
        head = pat.split("*", 1)[0].split("?", 1)[0]
        heads.add(head.rsplit("/", 1)[0] if "/" in head else "")
    found: set[Path] = set()
    starts = {h for h in heads if not any(h != o and (h + "/").startswith(o + "/") for o in heads if o)}
    seen: set[str] = set()                          # real paths of the folders walked: a link back up ends there
    for start in sorted(starts):
        base = root / start
        walked: Iterable[tuple[str, list[str], list[str]]]
        if base.is_file():
            walked = [(str(base.parent), [], [base.name])]
        else:
            walked = os.walk(base, followlinks=True)
        for dirpath, dirnames, filenames in walked:
            seen.add(os.path.realpath(dirpath))
            rel_dir = Path(dirpath).relative_to(root).as_posix()
            rel_dir = "" if rel_dir == "." else rel_dir
            dirnames[:] = [d for d in dirnames
                           if d not in PRUNE and not _pruned(f"{rel_dir}/{d}".lstrip("/"))
                           and os.path.realpath(os.path.join(dirpath, d)) not in seen]
            for f in filenames:
                if f.endswith(LITTER) or f == ".DS_Store":
                    continue
                rel = f"{rel_dir}/{f}".lstrip("/")
                if any(ps._glob_match(rel, pat) for pat in patterns):
                    p = root / rel
                    if p.is_file():
                        found.add(p)
    return sorted(found)


class HashCache:
    """sha256 of files, reused while a file's size and mtime stay; shared by the jobs through one JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.dirty = False
        try:
            self.data = json.loads(path.read_text())
        except (OSError, ValueError):
            self.data = {}

    def __call__(self, p: Path) -> str:
        st = p.stat()
        hit = self.data.get(str(p))
        if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
            sha: str = hit[2]
            return sha
        new = hashlib.sha256(p.read_bytes()).hexdigest()
        self.data[str(p)] = [st.st_mtime_ns, st.st_size, new]
        self.dirty = True
        return new

    def save(self) -> None:
        """Write the cache, less the files whose folder is gone (a removed worktree: make remote makes one per run,
        so on the Windows box the file grew to 747k entries for 152 worktrees, 5.6k of them live, 2026-11-25)."""
        if not self.dirty:
            return
        alive = {d: not d or os.path.isdir(d) for d in {os.path.dirname(k) for k in self.data}}   # "": no folder part
        self.data = {k: v for k, v in self.data.items() if alive[os.path.dirname(k)]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(self.data))
        os.replace(tmp, self.path)


def _run(*cmd: str, cwd: Path) -> str:
    try:
        done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    return done.stdout if done.returncode == 0 else f"failed:{done.returncode}"


def venv_state(python: Path) -> str:
    """An interpreter's real path and the names and versions of the packages it can import: for the Python running
    this (the jobs' python3), its site-packages and the user's (pip install --user); for another one (a venv), the
    site-packages under its prefix."""
    out = [os.path.realpath(python)]
    if out[0] == os.path.realpath(sys.executable):
        import site
        sites = [Path(s) for s in site.getsitepackages()]
        if site.ENABLE_USER_SITE:
            sites.append(Path(site.getusersitepackages()))
    else:
        sites = sorted(Path(python).parent.parent.glob("lib/python*/site-packages"))
    for s in sites:
        out += sorted(d.name for d in s.glob("*.dist-info"))
    return "|".join(out)


class Checker:
    """The stamp checks of one moment: one file-hash cache, and what is the same for every job then (git's answers,
    the plugin's state, the walk of a pattern set, the interpreters, the snapshot) worked out once. check.sh's
    `current-batch` checks every job with one; a single `current`, `why` or `record` makes one of its own. `root` is
    the checkout and `store` the stamp folder (check_stamps.ROOT and check_stamps.STORE for the CLI)."""

    def __init__(self, root: Path, store: Path) -> None:
        self.root, self.store = root, store
        self.cache = HashCache(store / "filehash.json")
        self._memo: dict[tuple, object] = {}

    def _once(self, key: tuple[object, ...], make: Callable[[], T]) -> T:
        if key not in self._memo:
            self._memo[key] = make()
        return cast(T, self._memo[key])     # the memo holds make()'s value under its own key

    def git(self, *args: str) -> str:
        return self._once(("git", args), lambda: _run("git", *args, cwd=self.root))

    def plugin(self) -> str:
        return self._once(("plugin",), lambda: cast(str, ps.plugin_state(self.root)))

    def unstampable(self) -> str | None:
        return self._once(("unstampable",), lambda: cast("str | None", ps.unstampable(self.root)))

    def walk(self, patterns: tuple[str, ...]) -> list[Path]:
        return self._once(("walk", patterns), lambda: walk(patterns, self.root))

    def manifest(self) -> dict[str, JobKey]:
        """manifest.job_keys of the checkout's tools/pipeline/checks.toml (raises manifest.ManifestError)."""
        return self._once(("manifest",), lambda: pm.job_keys(self.root / MANIFEST))

    def venv(self, python: Path) -> str:
        return self._once(("venv", str(python)), lambda: venv_state(python))

    def replay(self, gits: Iterable[list[str]]) -> list[str]:
        """traced.git_replay, each command run once."""
        return [self._once(("replay", tuple(cmd)), partial(self._replay_one, cmd)) for cmd in gits]

    def _replay_one(self, cmd: list[str]) -> str:
        return cast(str, traced.git_replay([cmd], str(self.root))[0])

    def snapshot(self, outside: str) -> str:
        return self._once(("snapshot", outside), lambda: cast(str, traced.snapshot(self.root, self.plugin(), outside)))


def _file(name: str, store: Path) -> Path:
    """Job `name`'s stamp file in the stamp folder `store`."""
    slug = "".join(c if c.isalnum() else "_" for c in name)[:60]
    return store / f"{slug}-{hashlib.sha256(name.encode()).hexdigest()[:10]}.json"

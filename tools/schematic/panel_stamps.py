#!/usr/bin/env python3
"""Traced stamps for the `step`s of build_panels.sh: a step whose recorded reads and outputs are unchanged is skipped.

    panel_stamps.py current NAME [CMD ...]               exit 0 when NAME's stamp still holds (the step may be skipped)
    panel_stamps.py snapshot FILE                        what the key takes from git and the plugin, before a run
    panel_stamps.py record  NAME --trace LOG [--snapshot FILE] [CMD ...]
                                                         record NAME's stamp from the trace of the run that just passed
    panel_stamps.py why     NAME [CMD ...]               say why NAME is not current
    panel_stamps.py unstampable                          prints why no stamp is recorded now and exits 1, or exits 0
    panel_stamps.py forget  NAME                         drop NAME's stamp (after a failure)

build_panels.sh runs each step with the trace hook of tools/audit/traced.py, which logs every repo file the step's
Python processes open, every file they probe and find absent, every folder they list and every subprocess they
start. After a pass the stamp records that read set with its hashes, and a key: the sha256 over the step's command
line, its outputs (STEPS, read from tools/pipeline/panels.toml), the code every step may run (CODE, whole), the
schematic-maps plugin's commit and uncommitted changes (of the SCHEMATIC_PLUGIN folder when set), the Python
(version, real path, PYTHONPATH), SCHEMATIC_REQUIRED, and, for the steps that publish, the merge base with origin/main. The next run skips the step
only when the key and every read-set entry match: each file's content, each miss's absence, each listing's names,
and the output of each read-only git command the step ran (run again). An edit to one data file re-runs only the
steps that read it.

What the hook cannot see is a subprocess that is not a traced Python (bash, Chrome, git that writes). A step that
ran one records nothing, so it always runs, unless STEPS names that program with the files it reads (`programs`;
an output it reads is hashed already). Nothing is recorded, and nothing skipped, while HART_TABLES is set or the
plugin is not at its pinned commit (unstampable), when the trace is missing or a Python child did not load the
hook, or when a file the step read and did not write changed while it ran; build_panels.sh records nothing for a
step that printed SKIPPED. The stamps are kept per checkout in .cache/panel-stamps/ (gitignored). `make panels
FULL=1` ignores them (and records). Guards never use them: they are cheap and they check.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".cache" / "panel-stamps"
PLUGIN = ROOT / "external" / "model-railroad-skills"


def _load_traced():
    """tools/audit/traced.py, by path (this script cannot import hartlib: the shell test runs a copy of it)."""
    if "_hart_traced" in sys.modules:
        return sys.modules["_hart_traced"]
    path = Path(__file__).resolve().parents[1] / "audit" / "traced.py"
    spec = importlib.util.spec_from_file_location("_hart_traced", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_hart_traced"] = mod
    spec.loader.exec_module(mod)
    return mod


traced = _load_traced()

DATA = "jmri/layouts/hart/data"
# The device master's file names: the generated file the device-map and panel-items steps write, and the
# owner's field file. This script cannot import hartlib (the shell test runs a copy of it alone), so the names are
# here, and test_devices_one_path pins them to hartlib.devices.
DEVICES_FILE = "devices_generated.csv"
DEVICES_FIELD_FILE = "devices_field.csv"

# The code every step may run, declared whole: hartlib, the schematic tools, the helpers they import, the trace hook.
CODE = (
    "tools/hartlib/src/**/*.py",
    "tools/schematic/*.py",
    "tools/ops/screenshot.py",
    "cats/scripts/*.py",
    "jmri/layouts/hart/scripts/layout_facts.py",
    "jmri/layouts/hart/scripts/build_hart_signal_heads.py",
    "jmri/scripts/signal_coordinator.py",
    "jmri/scripts/sml_*.py",     # its modules: le_names.lcos_rule imports the LCOS head rule, sml_lcos.py
    *traced.HOOK_FILES,
)


@dataclass(frozen=True)
class Step:
    outputs: tuple[str, ...]
    publishes: bool = False       # reads main's published files through git: the merge base with origin/main is input
    # untraceable programs the step may run (matched by name, case-insensitive substring) -> the files they read
    programs: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _load_manifest():
    """tools/pipeline/manifest.py, by path, under the name tools/audit/check_stamps.py and the map lane load it by: its
    dataclasses look their module up in sys.modules, so it is put there before it runs."""
    if "pipeline_manifest" not in sys.modules:
        spec = importlib.util.spec_from_file_location("pipeline_manifest", ROOT / "tools" / "pipeline" / "manifest.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["pipeline_manifest"] = mod
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            del sys.modules["pipeline_manifest"]
            raise
    return sys.modules["pipeline_manifest"]


class StepsError(Exception):
    """The panels manifest does not load, or lists no step; the message says why."""


_STEPS: dict[str, Step] | None = None


def steps() -> dict[str, Step]:
    """The `step`s of the panels manifest (tools/pipeline/panels.toml; guards have no stamp), each with its outputs,
    publish flag and programs, read on first use (importing this module reads nothing); StepsError when the manifest
    does not load or lists no step."""
    global _STEPS
    if _STEPS is None:
        manifest = _load_manifest()
        try:
            listed = manifest.panel_steps()
        except manifest.ManifestError as err:
            raise StepsError(str(err)) from err
        found = {s.name: Step(tuple(o.path for o in s.outputs), s.publishes, {p: tuple(g) for p, g in s.programs})
                 for s in listed if s.mode == "step"}
        if not found:
            raise StepsError(f"{manifest.PANELS} lists no step")
        _STEPS = found
    return _STEPS


def __getattr__(name: str):
    """STEPS, the module attribute, is steps()."""
    if name == "STEPS":
        return steps()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

SKIP_PARTS = {"__pycache__", ".DS_Store"}


def expand(patterns, root: Path = ROOT) -> list[Path]:
    """Every file under `root` the patterns name (** crosses folders), sorted, caches and Finder litter left out."""
    found: set[Path] = set()
    for pat in patterns:
        for p in root.glob(pat):
            if p.is_file() and not SKIP_PARTS & set(p.relative_to(root).parts):
                found.add(p)
    return sorted(found)


def _glob_match(rel: str, pat: str) -> bool:
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pat.startswith("**", i):
            out += ".*"
            i += 2
        elif pat[i] == "*":
            out += "[^/]*"
            i += 1
        elif pat[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pat[i])
            i += 1
    return re.fullmatch(out, rel) is not None


def _git(*args: str, cwd: Path) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "git-unavailable"
    return r.stdout.strip() if r.returncode == 0 else f"git-failed:{r.returncode}"


def _tree_state(folder: Path) -> str:
    """A folder's git HEAD, its uncommitted changes (status and a hash of the diff against HEAD)."""
    diff = subprocess.run(["git", "diff", "HEAD"], cwd=folder, capture_output=True, timeout=60)
    return "|".join((_git("rev-parse", "HEAD", cwd=folder), _git("status", "--porcelain", cwd=folder),
                     hashlib.sha256(diff.stdout).hexdigest()))


def plugin_state(root: Path = ROOT) -> str:
    """The plugin code the steps run: the SCHEMATIC_PLUGIN folder when a trial points at one, else this checkout's
    submodule; in both, its commit and what is uncommitted in it."""
    trial = os.environ.get("SCHEMATIC_PLUGIN", "")
    plugin = Path(trial) if trial else root / "external" / "model-railroad-skills"
    if not plugin.is_dir():
        return f"{trial}|no-plugin"
    return f"{trial}|{_tree_state(plugin)}"


def unstampable(root: Path = ROOT) -> str | None:
    """Why no stamp may be recorded (or trusted) now, or None: a step that did not really run must never stamp.
    HART_TABLES points the checks at another tables file; the plugin must be at its pinned commit (or a trial folder
    named by SCHEMATIC_PLUGIN, which the stamp then holds by its own state)."""
    if os.environ.get("HART_TABLES"):
        return f"HART_TABLES is set ({os.environ['HART_TABLES']}): the steps run on another tables file"
    if os.environ.get("SCHEMATIC_PLUGIN"):
        plugin = Path(os.environ["SCHEMATIC_PLUGIN"])
        return None if plugin.is_dir() else f"SCHEMATIC_PLUGIN={plugin} is not a folder"
    plugin = root / "external" / "model-railroad-skills"
    if not plugin.is_dir() or not any(plugin.iterdir()):
        return "the schematic-maps plugin submodule is not checked out"
    pinned = _git("rev-parse", "HEAD:external/model-railroad-skills", cwd=root)
    have = _git("rev-parse", "HEAD", cwd=plugin)
    if pinned != have:
        return f"the schematic-maps plugin is at {have[:8]}, not its pinned commit {pinned[:8]}"
    return None


def digest(label: str, cmd, patterns, root: Path = ROOT, publishes: bool = False, hasher=None, extra: str = "", files=None,
           plugin: str | None = None) -> str:
    """The sha256 over a job's label and command line, the Python, SCHEMATIC_REQUIRED, the plugin's state, `extra`, the
    merge base with origin/main when `publishes`, and every file `patterns` name. Shared with tools/audit/check_stamps.py;
    `hasher(path)` may stand in for reading the file (a cache keyed on its size and mtime); `files` replaces the expansion
    of `patterns` (a caller that walks a wide tree and prunes it); `plugin` replaces plugin_state(root) (a caller that
    checks many jobs at one moment and works it out once)."""
    h = hashlib.sha256()

    def put(tag: str, text: str) -> None:
        h.update(f"{tag}\0{text}\0".encode())

    put("step", label)
    put("cmd", " ".join(cmd))
    put("python", f"{sys.version_info[:3]} {os.path.realpath(sys.executable)} {os.environ.get('PYTHONPATH', '')}")
    put("schematic-required", os.environ.get("SCHEMATIC_REQUIRED", ""))
    put("plugin", plugin_state(root) if plugin is None else plugin)
    if extra:
        put("extra", extra)
    if publishes:
        put("merge-base", _git("merge-base", "HEAD", "origin/main", cwd=root))
    hasher = hasher or (lambda p: hashlib.sha256(p.read_bytes()).hexdigest())
    for p in (files if files is not None else expand(patterns, root)):
        put(p.relative_to(root).as_posix(), hasher(p))
    return h.hexdigest()


def allowed(name: str, programs: list[str]) -> tuple[list[str], list[str]]:
    """(the programs STEPS lets `name` run untraced, the ones it does not)."""
    rules = steps()[name].programs
    ok = [p for p in programs if any(k.lower() in p.lower() for k in rules)]
    return ok, [p for p in programs if p not in ok]


def key(name: str, cmd, root: Path, programs: list[str], gits: list) -> str:
    """The stamp key: the step's command, outputs, code, plugin, interpreter and environment, the untraced programs it
    ran with the files STEPS says they read, and its git commands' output now."""
    step = steps()[name]
    extra_pats = [pat for k, pats in step.programs.items() if any(k.lower() in p.lower() for p in programs)
                  for pat in pats]
    extra = f"programs={','.join(programs)}\ngit={','.join(traced.git_replay(gits, str(root)))}"
    return digest(name, cmd, (*step.outputs, *CODE, *extra_pats), root, step.publishes, extra=extra)


def _file(name: str, store: Path) -> Path:
    return store / f"{name}.json"


def why_not_current(name: str, cmd=(), root: Path = ROOT, store: Path = STORE) -> str | None:
    """None when step `name` may be skipped, else why it must run."""
    reason = unstampable(root)
    if reason:
        return reason
    stamp = traced.load(_file(name, store))
    if not stamp:
        return "no stamp"
    return traced.mismatch(stamp, key(name, cmd, root, stamp.get("programs", []), stamp.get("git", [])), str(root))


def is_current(name: str, cmd=(), root: Path = ROOT, store: Path = STORE) -> bool:
    return why_not_current(name, cmd, root, store) is None


def snapshot(root: Path = ROOT) -> str:
    """traced.snapshot with the plugin's state: taken before a step runs and compared when it records."""
    return traced.snapshot(root, plugin_state(root))


def record(name: str, trace_log, cmd=(), root: Path = ROOT, store: Path = STORE, before: str | None = None) -> str | None:
    """Record `name`'s stamp from `trace_log`; None when recorded, else why not (and any old stamp is dropped).
    `before` is the snapshot() taken before the step ran: a different one now records nothing."""
    reason = unstampable(root)
    if reason is None and before is not None and before != snapshot(root):
        reason = "HEAD, origin/main or the plugin changed while the step ran"
    if reason is None:
        t = traced.parse(trace_log)
        reason = traced.problem(t)
        if reason is None:
            from_main = _main_checkout(root)
            programs, gits = traced.untraced(t, str(root), (from_main,) if from_main else ())
            ok, bad = allowed(name, programs)
            if bad:
                reason = f"ran {', '.join(bad)}, which the trace cannot see and STEPS does not declare"
            else:
                rs = traced.read_set(t, str(root))
                late = traced.changed_since(t, rs, str(root), [p.relative_to(root).as_posix() for p in expand(CODE, root)])
                if late:
                    reason = f"{late[0]} changed while the step ran"
                else:
                    k = key(name, cmd, root, ok, gits)
                    traced.save(_file(name, store), traced.make_stamp(k, t, str(root), programs=ok, git=gits))
                    return None
    forget(name, store)
    return reason


def _main_checkout(root: Path) -> str | None:
    common = _git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=root)
    if common.startswith("git-"):
        return None
    return str(Path(common).parent)


def forget(name: str, store: Path = STORE) -> None:
    _file(name, store).unlink(missing_ok=True)
    (store / f"{name}.sha256").unlink(missing_ok=True)      # the declared-input stamps before the traced ones


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["unstampable"]:
        reason = unstampable()
        if reason:
            print(reason)
        return 1 if reason else 0
    if len(argv) == 2 and argv[0] == "snapshot":
        Path(argv[1]).write_text(snapshot() + "\n")
        return 0
    if len(argv) < 2 or argv[0] not in ("current", "record", "forget", "why"):
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    action, name, rest = argv[0], argv[1], argv[2:]
    if action == "forget":      # needs no manifest: a failed step's stamp goes even when panels.toml is broken
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            print(f"panel_stamps.py: {name!r} is not a step name", file=sys.stderr)
            return 2
        forget(name)
        return 0
    try:
        known = steps()
    except StepsError as err:
        print(f"panel_stamps.py: {err}", file=sys.stderr)
        return 2
    if name not in known:
        print(f"panel_stamps.py: no step {name!r} (known: {', '.join(known)})", file=sys.stderr)
        return 2
    if action == "current":
        return 0 if is_current(name, rest) else 1
    if action == "why":
        print(why_not_current(name, rest) or "current")
        return 0
    if action == "record":
        if rest[:1] != ["--trace"] or len(rest) < 2:
            print("panel_stamps.py record NAME --trace LOG [--snapshot FILE] [CMD ...]", file=sys.stderr)
            return 2
        log, rest = rest[1], rest[2:]
        before = None
        if rest[:1] == ["--snapshot"] and len(rest) >= 2:
            snap = Path(rest[1])
            before, rest = (snap.read_text().strip() if snap.is_file() else "missing"), rest[2:]
        reason = record(name, log, rest, before=before)
        if reason:
            print(f"   {name}: not stamped: {reason}")
        return 0
    forget(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())

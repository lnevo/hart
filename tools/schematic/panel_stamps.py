#!/usr/bin/env python3
"""Stamps for the `step`s of build_panels.sh: a step whose stamp equals its last successful run's is skipped.

    panel_stamps.py current NAME [CMD ...]   exit 0 when NAME's stamp equals the recorded one (the step may be skipped)
    panel_stamps.py record  NAME [CMD ...]   record NAME's stamp now (build_panels.sh does it after the step passed)
    panel_stamps.py unstampable              prints why no stamp is recorded now and exits 1, or exits 0
    panel_stamps.py forget  NAME             drop NAME's stamp (after a failure)

A stamp is the sha256 over the step's command line, every file its declaration names (STEPS: the inputs, the code that
runs, the outputs), the schematic-maps plugin's commit and uncommitted changes (of the SCHEMATIC_PLUGIN folder when set), the
Python (version, real path, PYTHONPATH), SCHEMATIC_REQUIRED, and, for the steps that publish, the merge base with origin/main. The outputs are in it, so an edited or
deleted output makes the step run again, and the same stamp means "this step's inputs and outputs are what its last
successful run left". Nothing is recorded, and nothing skipped, while HART_TABLES is set or the plugin is not at
its pinned commit (unstampable), and build_panels.sh records nothing for a step that printed SKIPPED. The stamps are kept per checkout in .cache/panel-stamps/ (gitignored). `make panels FULL=1`
ignores them. Guards never use them: they are cheap and they check.

The risk is an input the declaration misses, so tests/test_panel_stamps.py runs every step under an audit hook and fails
for any repo file it reads that its declaration does not cover. What the hook cannot see: a subprocess of a step (git,
Chrome's PDF print of `schematic`) and the plugin's reads (covered by its commit). The `data` folder is declared whole
for the heavy steps ("coarse" below), so a new data file can never be missed there.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".cache" / "panel-stamps"
PLUGIN = ROOT / "external" / "model-railroad-skills"

DATA = "jmri/layouts/hart/data"
# The device master's file name. This script cannot import hartlib (the shell test runs a copy of it alone), so the
# name is here, and test_panel_stamps pins it to hartlib.devices.MASTER_FILE.
DEVICES_FILE = "devices.csv"
SCH = f"{DATA}/schematic"
OUT = "jmri/layouts/hart/output"

# The code every step may run, declared whole (coarse): hartlib, the schematic tools, the helpers they import.
CODE = (
    "tools/hartlib/src/**/*.py",
    "tools/schematic/*.py",
    "tools/ops/screenshot.py",
    "cats/scripts/*.py",
    "jmri/layouts/hart/scripts/layout_facts.py",
    "jmri/layouts/hart/scripts/build_hart_signal_heads.py",
    "jmri/scripts/signal_coordinator.py",
)
# The shared source data: the whole data folder (coarse: a new file there is covered) and the parked tables.
ALL_DATA = (f"{DATA}/**/*", "jmri/layouts/hart/parked/tables_parked.xml")


@dataclass(frozen=True)
class Step:
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    publishes: bool = False       # reads main's published files through git: the merge base with origin/main is input


STEPS: dict[str, Step] = {
    "hands": Step(
        (f"{SCH}/inputs/main.json", f"{SCH}/plan_overrides.json", f"{DATA}/switches.csv"),
        (f"{DATA}/switches.csv",)),
    "staging-sets": Step(
        (f"{SCH}/plan_overrides.json", f"{SCH}/preferences.json", f"{SCH}/sheets.csv", f"{SCH}/stations.csv",
         f"{DATA}/switches.csv"),
        (f"{SCH}/plan_overrides.json", f"{SCH}/preferences.json")),
    "main-route": Step(
        (f"{SCH}/block_numbering.csv", f"{SCH}/inputs/*.json", f"{SCH}/main_lines.csv", f"{SCH}/plan_overrides.json",
         f"{SCH}/preferences.json", f"{SCH}/signals.json", f"{SCH}/stations.csv", f"{SCH}/sheets.csv",
         f"{DATA}/switches.csv"),
        (f"{SCH}/plan_overrides.json",)),
    "device-map": Step(ALL_DATA, (f"{SCH}/plan_overrides.json", f"{DATA}/{DEVICES_FILE}")),
    "masts": Step(ALL_DATA, (f"{SCH}/masts.csv", f"{DATA}/{DEVICES_FILE}")),
    "signals": Step(ALL_DATA, (f"{SCH}/signals.json",)),
    "head-plan": Step((f"{DATA}/wiring.csv", f"{SCH}/lcos_nodes.csv"), (f"{OUT}/signal_head_plan.csv",)),
    "schematic": Step(
        (*ALL_DATA, "www/data/*.json", "www/crew/maps/*/index.html"),
        ("docs/ops/schematic-system-draft.*", "docs/ops/stations/*", "www/crew/maps/*/index.html",
         f"{SCH}/preferences.json"),
        publishes=True),
    "le-cutover": Step(ALL_DATA, (f"{OUT}/trial/*.xml",)),
    "tables": Step((*ALL_DATA, f"{OUT}/trial/*.xml"), (f"{OUT}/tables.xml",)),
    "cats": Step(
        (*ALL_DATA, f"{OUT}/tables.xml", f"{OUT}/signal_head_plan.csv", f"{OUT}/trial/*.xml", "cats/data/*"),
        ("cats/panels/HART_CTC.xml", "cats/panels/HART_ABS.xml", "cats/panels/HART_CTC.bindings.json")),
}

SKIP_PARTS = {"__pycache__", ".DS_Store"}


def expand(patterns, root: Path = ROOT) -> list[Path]:
    """Every file under `root` the patterns name (** crosses folders), sorted, caches and Finder litter left out."""
    found: set[Path] = set()
    for pat in patterns:
        for p in root.glob(pat):
            if p.is_file() and not SKIP_PARTS & set(p.relative_to(root).parts):
                found.add(p)
    return sorted(found)


def covered(rel: str, step: str) -> bool:
    """Is repo file `rel` named by `step`'s declaration (its inputs, outputs or the code every step may run), or the
    plugin (stamped by its commit)?"""
    if rel.startswith("external/model-railroad-skills/"):
        return True
    if "__pycache__" in rel.split("/"):
        return True
    s = STEPS[step]
    for pat in (*s.inputs, *s.outputs, *CODE):
        # glob "**/" matches zero or more folders; "*" stays within one folder, as in Path.glob
        if _glob_match(rel, pat):
            return True
    return False


def dir_covered(rel: str, step: str) -> bool:
    """Is folder `rel` (listed or globbed by `step`) one a declaration reaches: a declared pattern's fixed folder is it,
    inside it, or above it."""
    if rel.startswith("external/model-railroad-skills") or rel in (".", "") or "__pycache__" in rel.split("/"):
        return True
    s = STEPS[step]
    for pat in (*s.inputs, *s.outputs, *CODE):
        head = pat.split("*", 1)[0]                     # the part before the first glob character
        literal = head.rsplit("/", 1)[0] if "/" in head else ""
        if rel == literal or rel.startswith(literal + "/") or literal.startswith(rel + "/"):
            return True
    return False


def _glob_match(rel: str, pat: str) -> bool:
    import re
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


def digest(label: str, cmd, patterns, root: Path = ROOT, publishes: bool = False, hasher=None, extra: str = "", files=None) -> str:
    """The sha256 over a job's label and command line, the Python, SCHEMATIC_REQUIRED, the plugin's state, `extra`, the
    merge base with origin/main when `publishes`, and every file `patterns` name. Shared with tools/audit/check_stamps.py;
    `hasher(path)` may stand in for reading the file (a cache keyed on its size and mtime); `files` replaces the expansion
    of `patterns` (a caller that walks a wide tree and prunes it)."""
    h = hashlib.sha256()

    def put(tag: str, text: str) -> None:
        h.update(f"{tag}\0{text}\0".encode())

    put("step", label)
    put("cmd", " ".join(cmd))
    put("python", f"{sys.version_info[:3]} {os.path.realpath(sys.executable)} {os.environ.get('PYTHONPATH', '')}")
    put("schematic-required", os.environ.get("SCHEMATIC_REQUIRED", ""))
    put("plugin", plugin_state(root))
    if extra:
        put("extra", extra)
    if publishes:
        put("merge-base", _git("merge-base", "HEAD", "origin/main", cwd=root))
    hasher = hasher or (lambda p: hashlib.sha256(p.read_bytes()).hexdigest())
    for p in (files if files is not None else expand(patterns, root)):
        put(p.relative_to(root).as_posix(), hasher(p))
    return h.hexdigest()


def stamp(name: str, cmd: list[str] | tuple[str, ...] = (), root: Path = ROOT) -> str:
    """The sha256 of step `name` as described in the module docstring."""
    step = STEPS[name]
    return digest(name, cmd, (*step.inputs, *step.outputs, *CODE), root, step.publishes)


def _file(name: str, store: Path) -> Path:
    return store / f"{name}.sha256"


def is_current(name: str, cmd=(), root: Path = ROOT, store: Path = STORE) -> bool:
    f = _file(name, store)
    return unstampable(root) is None and f.is_file() and f.read_text().strip() == stamp(name, cmd, root)


def record(name: str, cmd=(), root: Path = ROOT, store: Path = STORE) -> None:
    if unstampable(root) is not None:
        return
    store.mkdir(parents=True, exist_ok=True)
    _file(name, store).write_text(stamp(name, cmd, root) + "\n")


def forget(name: str, store: Path = STORE) -> None:
    _file(name, store).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["unstampable"]:
        reason = unstampable()
        if reason:
            print(reason)
        return 1 if reason else 0
    if len(argv) < 2 or argv[0] not in ("current", "record", "forget"):
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    action, name, cmd = argv[0], argv[1], argv[2:]
    if name not in STEPS:
        print(f"panel_stamps.py: no step {name!r} (known: {', '.join(STEPS)})", file=sys.stderr)
        return 2
    if action == "current":
        return 0 if is_current(name, cmd) else 1
    if action == "record":
        record(name, cmd)
    else:
        forget(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())

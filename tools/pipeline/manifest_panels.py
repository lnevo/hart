"""manifest_panels.py

make panels' manifest, tools/pipeline/panels.toml (ADR-037 stage 5): its fields, PanelStep, the loaders with and
without the checks against git and the map, the order rule (writers before readers) and build_panels.sh's lines.
tools/pipeline/manifest.py is the entry point and re-exports every name here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from manifest_base import (NAME_RE, PROGRAM_RE, ROOT, Edge, ManifestError, Repo, _edges, _entries, _path_list_problems,
                           glob_regex, path_problem, read, repo)


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


# A file a step of each manifest declares as an output, on purpose: path -> (its checks.toml step, its panels.toml
# step, why). Any other file declared in both fails writer_problems: one file, one writer (#1187 found crew.json
# written by two code paths).
SHARED_OUTPUTS: dict[str, tuple[str, str, str]] = {
    "www/data/crew.json": ("crew-json", "schematic", "both write it whole through crew_master.build() (#1187): the "
                           "crew-json job from the crew master, the schematic step when the title block's revision "
                           "changes"),
}


def writer_problems(checks, panels, checks_shown: str, panels_shown: str,
                    shared: dict[str, tuple[str, str, str]] = SHARED_OUTPUTS) -> list[str]:
    """Why a file is declared as an output of a step of checks.toml and of a step of panels.toml, or []. Two outputs
    that can name one file (a glob included) are a problem unless they are one path that `shared` lists with those
    two steps. A `shared` entry without a reason, or one the manifests no longer declare that way, is a problem too,
    so the list cannot go stale."""
    out = [f"SHARED_OUTPUTS in tools/pipeline/manifest_panels.py: {path}: give the reason both manifests write it"
           for path, (_c, _p, why) in shared.items() if not why.strip()]
    used: set[str] = set()
    for c in checks:
        for oc in c.outputs:
            for p in panels:
                for op in p.outputs:
                    if not _overlap(oc.path, op.path):
                        continue
                    if oc.path == op.path and shared.get(oc.path, ())[:2] == (c.name, p.name):
                        used.add(oc.path)
                        continue
                    same = oc.path if oc.path == op.path else f"{oc.path} and {op.path}"
                    out.append(f"{same}: an output of step {c.name!r} in {checks_shown} and of step {p.name!r} in "
                               f"{panels_shown}; a file has one writer: drop it from one step, or, when both must "
                               f"write it whole the same way, list it in SHARED_OUTPUTS in "
                               f"tools/pipeline/manifest_panels.py with the two steps and why")
    out += [f"SHARED_OUTPUTS in tools/pipeline/manifest_panels.py: {path}: step {c!r} in {checks_shown} and step "
            f"{p!r} in {panels_shown} no longer both declare it; remove the entry"
            for path, (c, p, _why) in sorted(shared.items()) if path not in used]
    return out


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


# check.sh's jobs for the panels steps (ADR-037 stage 6): the panels step of checks.toml, the one that runs
# build_panels.sh, stands for one job per step here, panels-<step>, which runs that step's check (cmd and check_args)
# under check.sh's own trace and stamps, so an unchanged panels check is skipped locally and on pull requests.
PANEL_JOB_PREFIX = "panels-"
PANELS_UNAUDITED = ("tools/pipeline/panels.toml's inputs are the map's edges, not every file a step reads, so the "
                    "reads of its jobs are not audited (ADR-037 stage 6)")


def runs_panels(cmd) -> bool:
    """Whether a checks.toml command is the one that runs make panels' steps (bash build_panels.sh ...)."""
    return list(cmd[:2]) == ["bash", PANELS_RUNNER]


def panel_check_lines(steps) -> list[str]:
    """check.sh's lines for the panels steps' checks, one job each: panels-<name>, then cmd and check_args. A check
    writes nothing, so the jobs run in any order and side by side; make panels keeps the file order for its builds.
    The words are plain (PANEL_WORD_RE), so they need no quoting. ManifestError on no step."""
    if not steps:
        raise ManifestError("no panels step; check.sh would check no panel output")
    return [" ".join((PANEL_JOB_PREFIX + s.name, *s.cmd, *s.check_args)) for s in steps]

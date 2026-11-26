"""pipeline_map_eff.py

What the pipeline map page shows beside the graph itself, worked out when the page is built (build_pipeline_map.py
calls page_extras() from render()): how each step runs, how many scripts write each output, one summary per lane with
the links between lanes counted, and the logged step times when there are any. The page's lane overview and its
efficiency overlay draw from these, so the page needs no layout of the whole map to open.

- eff, on a box that runs as a step: one entry per step of tools/pipeline/panels.toml (make panels) or
  tools/pipeline/checks.toml (check.sh) drawn in it, {"r": "panels" | "check", "s": step name, "m": mode}. Mode
  "step" is stamped: the step is skipped while its inputs are unchanged (panel_stamps.py for make panels,
  check_stamps.py for every check.sh job); "guard" is a make panels check that always runs. A step is matched to its
  box by the box id (a panels step's box) or the box's path (the step's script), as the manifest lane draws them.
- w, on an output box: {"n": writers} counts the generator boxes with a content link into it (side links, a check's
  read, a doc pointer or a Store pull, carry nothing and are not counted). Two or more writers carry "ok": why the
  manifests allow it, "updates" when every writer is a panels step that lists the file in its updates (each rewrites
  only its part) or "shared" when SHARED_OUTPUTS (manifest_panels.py) lists it.
- lanes: per domain, its box count, counts by kind and by status, and its steps (panels steps, stamped ones, guards,
  check.sh jobs, how many have a time). bundles: each pair of lanes a link joins, {"from", "to", "n", "side"}, with
  "side" the links among them that carry nothing on.
- timings: docs/pipeline-map/timings.json when the file exists, {"updated", "source", "steps": {"<runner>:<step>":
  {"runner", "step", "runs", "warm_s", "cold_s", "skip_rate", "last"}}}; each step's entry goes on its eff entry as
  "t". No file means no times, not an error; a file that does not read is a TimingsError.
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, NamedTuple, TypedDict

ROOT = Path(__file__).resolve().parents[2]
TIMINGS = ROOT / "docs" / "pipeline-map" / "timings.json"
SIDE_WRITES = ("check", "pointer", "pull")     # link sides that write nothing into the box they point at
TIME_KEYS = ("runs", "warm_s", "cold_s", "skip_rate", "last")
Runner = Literal["panels", "check"]


class TimingsError(Exception):
    """docs/pipeline-map/timings.json exists but does not read as the timings schema."""


class StepRef(NamedTuple):
    """One manifest step as the page needs it: its runner, name, mode, and the box id and script path it is drawn by."""
    runner: Runner
    name: str
    mode: Literal["step", "guard"]
    box: str
    script: str
    updates: tuple[str, ...] = ()


class Eff(TypedDict, total=False):
    r: Runner
    s: str
    m: str
    t: dict[str, Any]


def manifest_steps(manifest: Any) -> tuple[StepRef, ...]:
    """Every step of checks.toml and panels.toml, from the manifest module (tools/pipeline/manifest.py, loaded by the
    caller), loaded and checked as the manifest lane loads them (load_both); its ManifestError when they do not."""
    checks, panels = manifest.load_both()
    return (tuple(StepRef("check", s.name, "step", s.script, s.script) for s in checks)
            + tuple(StepRef("panels", s.name, "guard" if s.mode == "guard" else "step", s.box, s.script, s.updates)
                    for s in panels))


def read_timings(path: Path | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """Each step's logged times by (runner, step), from the timings file (TIMINGS by default); {} when there is none."""
    path = TIMINGS if path is None else path
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise TimingsError(f"cannot read {path.name}: {err}") from err
    steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps, dict):
        raise TimingsError(f"{path.name} needs a \"steps\" object")
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for key, entry in steps.items():
        if not isinstance(entry, dict):
            raise TimingsError(f"{path.name}: step {key!r} must be an object")
        runner, _, name = str(key).partition(":")
        runner, name = entry.get("runner", runner), entry.get("step", name)
        if runner not in ("panels", "check") or not name:
            raise TimingsError(f"{path.name}: step {key!r} is not <panels|check>:<step>")
        bad = [k for k in ("warm_s", "cold_s", "skip_rate") if entry.get(k) is not None
               and (isinstance(entry[k], bool) or not isinstance(entry[k], int | float) or entry[k] < 0)]
        if bad:
            raise TimingsError(f"{path.name}: step {key!r}: {', '.join(bad)} must be a number, 0 or more")
        out[(runner, name)] = {k: entry[k] for k in TIME_KEYS if entry.get(k) is not None}
    return out


def node_eff(nodes: Sequence[Mapping[str, Any]], steps: Sequence[StepRef],
             timings: Mapping[tuple[str, str], Mapping[str, Any]]) -> dict[str, list[Eff]]:
    """Each box id that runs as a step -> its steps (eff), with each step's time when the timings have one. A step
    whose box is not on the map (a test graph) is left out."""
    ids = {n["id"] for n in nodes}
    by_path = {n["path"].rstrip("/"): n["id"] for n in nodes if n.get("path")}
    out: dict[str, list[Eff]] = {}
    for s in steps:
        box = s.box if s.box in ids else by_path.get(s.script)
        if box is None:
            continue
        e: Eff = {"r": s.runner, "s": s.name, "m": s.mode}
        if (s.runner, s.name) in timings:
            e["t"] = dict(timings[(s.runner, s.name)])
        out.setdefault(box, []).append(e)
    return out


def writers(nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]], steps: Sequence[StepRef],
            shared: frozenset[str] = frozenset()) -> dict[str, dict[str, Any]]:
    """Each output box id -> {"n": its writers}, and "ok" (see the module doc) when two or more are allowed."""
    kind = {n["id"]: n["kind"] for n in nodes}
    path = {n["id"]: n.get("path", "").rstrip("/") for n in nodes}
    into: dict[str, set[str]] = {n["id"]: set() for n in nodes if n["kind"] == "output"}
    for e in edges:
        if e.get("side") in SIDE_WRITES or kind.get(e["from"]) != "generator" or e["to"] not in into:
            continue
        into[e["to"]].add(e["from"])
    updates: dict[str, set[str]] = {}       # box id -> the paths its panels steps update
    for s in steps:
        if s.runner == "panels":
            updates.setdefault(s.box, set()).update(s.updates)
    out: dict[str, dict[str, Any]] = {}
    for oid, ws in into.items():
        w: dict[str, Any] = {"n": len(ws)}
        if len(ws) > 1 and all(path[oid] in updates.get(x, ()) for x in ws):
            w["ok"] = "updates"
        elif len(ws) > 1 and path[oid] in shared:
            w["ok"] = "shared"
        out[oid] = w
    return out


def lanes(domains: Sequence[Mapping[str, Any]], nodes: Sequence[Mapping[str, Any]],
          eff: Mapping[str, list[Eff]]) -> list[dict[str, Any]]:
    """One summary per domain, in the graph's order (see the module doc)."""
    out = []
    for d in domains:
        mine = [n for n in nodes if n.get("domain") == d["id"]]
        steps = [e for n in mine for e in eff.get(n["id"], [])]
        panels = [e for e in steps if e["r"] == "panels"]
        out.append({
            "id": d["id"], "n": len(mine),
            "kinds": dict(Counter(n["kind"] for n in mine).most_common()),
            "status": dict(Counter(n.get("status", "live") for n in mine).most_common()),
            "steps": {"panels": len(panels), "stamped": sum(e["m"] == "step" for e in panels),
                      "guards": sum(e["m"] == "guard" for e in panels),
                      "checks": sum(e["r"] == "check" for e in steps), "timed": sum("t" in e for e in steps)},
        })
    return out


def bundles(nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The links between lanes, one entry per (from lane, to lane), most links first."""
    lane = {n["id"]: n.get("domain") for n in nodes}
    count: Counter[tuple[str, str]] = Counter()
    side: Counter[tuple[str, str]] = Counter()
    for e in edges:
        a, b = lane.get(e["from"]), lane.get(e["to"])
        if a is None or b is None or a == b:
            continue
        count[(a, b)] += 1
        if e.get("side"):
            side[(a, b)] += 1
    return [{"from": a, "to": b, "n": n, "side": side[(a, b)]} for (a, b), n in count.most_common()]


def page_extras(data: Mapping[str, Any], steps: Sequence[StepRef],
                timings: Mapping[tuple[str, str], Mapping[str, Any]],
                shared: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Everything above for one graph: {"eff", "w", "lanes", "bundles", "timed"}. shared: the paths SHARED_OUTPUTS
    lists."""
    eff = node_eff(data["nodes"], steps, timings)
    return {"eff": eff, "w": writers(data["nodes"], data["edges"], steps, shared),
            "lanes": lanes(data["domains"], data["nodes"], eff), "bundles": bundles(data["nodes"], data["edges"]),
            "timed": bool(timings)}

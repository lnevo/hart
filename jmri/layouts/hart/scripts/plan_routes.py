#!/usr/bin/env python3
"""The speed-match test routes on the AnyRail plan 5.3c (ADR-026): each route's length and where its pinned turnouts
sit along it, read from the plan file with the schematic-maps plugin's plan reader.

    python3 jmri/layouts/hart/scripts/plan_routes.py [PLAN.any]     # print both routes' values

infer_block_lengths.py scales its timed lap shares to a route's length and pins the timed positions to its turnouts.
A route is walked from Switch 5's points: at each turnout it leaves by the leg ROUTE_STEPS names, and the plan's
joins decide which turnout comes next. The length adds each turnout's route through it (the straight distance
between its points end and the leg the route uses) and the flex track between turnouts (the reader's runs). A
pinned turnout sits at the centre of its route through it, in mm from Switch 5's points, rounded to the mm.

A plan turnout's switch number comes from the staging relabel map of plan_overrides.json (the plan's T number is the
part's place in the file). The walk stops with PlanRouteError when a turnout is not the switch ROUTE_STEPS expects,
when a leg it names is the one the route came in on, when the route reaches a track end, or when it does not close
at Switch 5's points.

The plan file is the owner's and never committed: PLAN (plan_lengths.PLAN; ANYRAIL_PLAN overrides it).
"""
from __future__ import annotations

import argparse
import functools
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, NamedTuple

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import layer_files, paths, track_names  # noqa: E402

SCHEMATIC_TOOLS = paths.REPO_ROOT / "tools/schematic"
MM_PER_CM = 10.0

Leg = Literal["points", "straight", "diverging"]
# A plan part as the plugin's reader gives it (schematic.anyplan.read): a dict of its ends, kind and legs. Any: the
# plugin's own untyped records.
Part = Mapping[str, Any]


class PlanRouteError(ValueError):
    """A route cannot be walked on the plan as ROUTE_STEPS gives it; the message names the switch and the part."""


class Step(NamedTuple):
    """One turnout on a route: its switch number, the leg the route leaves by, and the OS sensor pinned to its centre
    (None: not pinned)."""
    switch: str
    leave: Leg
    pin: str | None = None


class RoutePlan(NamedTuple):
    """A route on the plan: its length in mm, and each pinned OS sensor's centre in mm from Switch 5's points."""
    loop_mm: float
    turnouts: dict[str, int]


# Loop 1, the 2026-11-08 test route: Switch 5 -> Switch 7 -> Main East -> Switch 33 -> East Lead -> Switch 35 -> 37 ->
# K loop -> 39 -> 35 -> West Ext -> 23 -> Main West -> 1 -> Brick-Plane -> 5. Switches 7, 37 and 39 are not pinned:
# 7 sits beside Switch 5 on a short stretch, and 37 and 39 sit 0.4 m and 0.2 m from the Switch 35 crossover, so
# pinning both ends of such a short stretch would turn a few cm of gap placement into a large error in the OS lengths
# between them.
_FROM_EAST_LEAD: tuple[Step, ...] = (
    Step("35", "straight", "Switch 35a"),
    Step("37", "diverging"),
    Step("39", "points"),
    Step("35", "straight", "Switch 35b"),
    Step("23", "points", "Switch 23a"),
    Step("1", "diverging", "Switch 1"),
)
# Loop 2: Switch 5 thrown into Scale, Switch 7, Barn, Switch 13, 15, Track S-R, 23b, 31, 33, then as loop 1 from East
# Lead. Switches 23b and 31 are not pinned: too close to Switch 33 for a pinned stretch of a few cm to stay
# meaningful. Switches 7 and 13 are the ones the loop 2 runs place (infer_block_lengths.py --locate).
ROUTE_STEPS: dict[str, tuple[Step, ...]] = {
    "loop1": (Step("5", "straight", "Switch 5"), Step("7", "straight"), Step("33", "points", "Switch 33"),
              *_FROM_EAST_LEAD),
    "loop2": (Step("5", "diverging", "Switch 5"), Step("7", "points"), Step("13", "points"),
              Step("15", "straight", "Switch 15"), Step("23", "points"), Step("31", "points"),
              Step("33", "points", "Switch 33"), *_FROM_EAST_LEAD),
}


def plan_path() -> Path:
    """The plan file: plan_lengths.PLAN (ANYRAIL_PLAN, else the owner's 5.3c in ~/Documents/Layout)."""
    return Path(_plan_lengths().PLAN)


def _plan_lengths() -> Any:
    """tools/schematic/plan_lengths.py, imported only when the plan is read. Any: a script module loaded by path."""
    if str(SCHEMATIC_TOOLS) not in sys.path:
        sys.path.insert(0, str(SCHEMATIC_TOOLS))
    import plan_lengths  # noqa: PLC0415  the plan path and the pinned plugin's reader

    return plan_lengths


def switch_labels(relabel: Mapping[str, str]) -> dict[int, str]:
    """{plan part index: switch number} from a relabel map {"T114": "5", ...}; PlanRouteError for a key that is no
    T number."""
    out: dict[int, str] = {}
    for key, switch in relabel.items():
        if not key.startswith("T") or not key[1:].isdigit():
            raise PlanRouteError(f"relabel key {key!r} is no plan T number (T<part index>)")
        out[int(key[1:])] = switch
    return out


def _leg_end(part: Part, leg: Leg) -> int:
    end = part.get(leg)
    if not isinstance(end, int):
        raise PlanRouteError(f"plan part T{part['index']} ({part.get('kind')}) has no {leg} leg")
    return end


def _through_mm(part: Part, a: int, b: int) -> float:
    """The straight distance between two ends of a part, in mm."""
    ea, eb = part["ends"][a], part["ends"][b]
    return math.hypot(ea["x"] - eb["x"], ea["y"] - eb["y"]) * MM_PER_CM


def walk(parts: Sequence[Part], runs: Sequence[tuple[int, int, int | None, int | None, float]],
         labels: Mapping[int, str], steps: Sequence[Step], route: str = "route") -> RoutePlan:
    """The route's length and pinned centres. parts and runs are the plugin's (anyplan.read, anyplan.runs); labels is
    {part index: switch number}. The route starts at steps[0]'s points and must close there."""
    if not steps:
        raise PlanRouteError(f"{route}: no steps")
    first = [i for i, s in labels.items() if s == steps[0].switch]
    if len(first) != 1:
        raise PlanRouteError(f"{route}: Switch {steps[0].switch} is {len(first)} plan parts; a route starts at one")
    nxt = {(a, ka): (b, kb, cm) for a, ka, b, kb, cm in runs}
    start = parts[first[0]]
    here, came_in = start, _leg_end(start, "points")
    pos, pins = 0.0, {}
    for step in steps:
        name = f"{route}: Switch {step.switch} (plan T{here['index']})"
        if labels.get(here["index"]) != step.switch:
            raise PlanRouteError(f"{name}: the plan part reached is Switch {labels.get(here['index'], 'none')}")
        if here.get("kind") != "turnout":
            raise PlanRouteError(f"{name}: is a {here.get('kind')}, not a turnout")
        points = _leg_end(here, "points")
        if came_in == points:
            if step.leave == "points":
                raise PlanRouteError(f"{name}: the route comes in at the points and cannot leave by them")
            leave = _leg_end(here, step.leave)
        else:
            if step.leave != "points":
                raise PlanRouteError(f"{name}: the route comes in on a leg, so it leaves by the points, "
                                     f"not the {step.leave} leg")
            leave = points
        through = _through_mm(here, came_in, leave)
        if step.pin:
            pins[step.pin] = round(pos + through / 2)
        pos += through
        if (here["index"], leave) not in nxt:
            raise PlanRouteError(f"{name}: no run leaves end {leave}")
        b, kb, cm = nxt[(here["index"], leave)]
        if b is None or kb is None:
            raise PlanRouteError(f"{name}: the route reaches a track end")
        pos += cm * MM_PER_CM
        here, came_in = parts[b], kb
    if here["index"] != start["index"] or came_in != _leg_end(start, "points"):
        raise PlanRouteError(f"{route}: the route ends at plan T{here['index']} end {came_in}, not at "
                             f"Switch {steps[0].switch}'s points: it does not close")
    return RoutePlan(round(pos, 1), pins)


def read_plan(plan: Path) -> dict[str, RoutePlan]:
    """{route: RoutePlan} of ROUTE_STEPS on the plan file `plan`."""
    reader = _plan_lengths().anyplan()
    parts = reader.read(plan)
    links, _free = reader.joins(parts)
    runs = reader.runs(parts, links)
    labels = switch_labels(track_names.relabel_map(layer_files.read("plan_overrides", "staging")))
    return {route: walk(parts, runs, labels, steps, route) for route, steps in ROUTE_STEPS.items()}


@functools.cache
def plan_routes() -> dict[str, RoutePlan]:
    """read_plan of the plan file (plan_path), read once."""
    plan = plan_path()
    if not plan.is_file():
        raise PlanRouteError(f"{plan}: the AnyRail plan is not on this machine (set ANYRAIL_PLAN to its path)")
    return read_plan(plan)


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("plan", nargs="?", type=Path, help="the AnyRail plan (default: plan_lengths.PLAN)")
    a = ap.parse_args(argv)
    try:
        got = read_plan(a.plan) if a.plan else plan_routes()
    except PlanRouteError as exc:
        raise SystemExit(f"plan_routes: {exc}") from exc
    for route, rp in got.items():
        print(f"{route}: {rp.loop_mm:.1f} mm; pinned centres (mm from Switch 5's points): {rp.turnouts}")


if __name__ == "__main__":
    main()

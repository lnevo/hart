"""Test copies of the block length files the speed-match tools read (block_lengths.csv and
block_lengths_measured.csv beside it), written for blocks named as routes.json names them, and the speed-match
routes' values on the AnyRail plan 5.3c (LOOP1, LOOP2) for tests that run without the plan file (CI never has it);
test_plan_routes.py holds those to what plan_routes.py reads from the plan where the plan is on the machine."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "speedmatch"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze  # noqa: E402
import plan_routes  # noqa: E402

LOOP1 = plan_routes.RoutePlan(35108.7, {
    "Switch 5": 142, "Switch 33": 12427, "Switch 35a": 15402,
    "Switch 35b": 22540, "Switch 23a": 27071, "Switch 1": 33172,
})
LOOP2 = plan_routes.RoutePlan(35434.2, {
    "Switch 5": 140, "Switch 15": 5913, "Switch 33": 12753, "Switch 35a": 15728,
    "Switch 35b": 22865, "Switch 23a": 27396, "Switch 1": 33498,
})
PLAN_ROUTES = {"loop1": LOOP1, "loop2": LOOP2}


def write_lengths(path, rows):
    """Write the plan file `path` and its measured file: rows is {block name: (plan_in, measured_in or None)}.
    Returns path."""
    path = Path(path)
    plan, measured = ["level,id,plan_in,note"], ["id,measured_in,run,date,note"]
    for name, (plan_in, measured_in) in rows.items():
        ident = analyze.BLOCK_IDS[name]
        plan.append("1,%s,%s," % (ident, plan_in))
        if measured_in is not None:
            measured.append("%s,%s,loop1 laps,2026-11-08," % (ident, measured_in))
    path.write_text("\n".join(plan) + "\n")
    analyze.measured_path(path).write_text("\n".join(measured) + "\n")
    return path

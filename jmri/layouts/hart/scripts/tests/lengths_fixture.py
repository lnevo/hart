"""Test copies of the block length files the speed-match tools read (block_lengths.csv and
block_lengths_measured.csv beside it), written for blocks named as routes.json names them."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "speedmatch"))
import analyze  # noqa: E402


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

"""build_hands.py [--check]

Write jmri/layouts/hart/data/schematic/hands.csv: the hand (R or L, the diverging side seen from the points) of every
main and upper level switch, read from the AnyRail plan graph (inputs/main.json, node `hand` +1 = R, -1 = L) and
renamed to the owner's switch numbers by the relabel edit in main_upper.plan_overrides.json. The `move` edit's
`hand` (T300, owner-confirmed R, switch 223) wins over the graph. Switch 225 is the double crossover: it has no hand,
so it is left out of the file. These are plan hands (owner decision 2026-11-14), not the schematic's drawn hands:
101A/B, 103A/B, 105, 107, 109 and 111 are flipped on the sheet. Provisional until the Layout Editor import.

--check regenerates in memory and exits 1 if the file differs.
"""
import csv
import io
import json
import re
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

DATA = paths.REPO_ROOT / "jmri/layouts/hart/data/schematic"
GRAPH = DATA / "inputs/main.json"
OVERRIDES = DATA / "main_upper.plan_overrides.json"
OUT = DATA / "hands.csv"
SOURCE = "plan geometry (provisional)"


def natural(name):
    m = re.match(r"(\d+)(.*)", name)
    return int(m.group(1)), m.group(2)


def build():
    """The file's text."""
    nodes = json.loads(GRAPH.read_text())["nodes"]
    edits = json.loads(OVERRIDES.read_text())["edits"]
    relabel = next(e["map"] for e in edits if e["op"] == "relabel")
    owner_hand = {e["switch"]: e["hand"] for e in edits if e["op"] == "move" and "hand" in e}
    by_label = {n["label"]: n for n in nodes.values() if n["kind"] == "switch"}
    rows = {}
    for old, new in relabel.items():
        node = by_label.get(old)
        if node is None:
            continue  # the double crossover is kind "dx": no hand
        hand = owner_hand.get(old) or ("R" if node["hand"] > 0 else "L")
        rows[new] = hand
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["switch", "hand", "source"])
    for name in sorted(rows, key=natural):
        w.writerow([name, rows[name], SOURCE])
    return out.getvalue()


def main(argv):
    text = build()
    if "--check" in argv:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"{OUT.relative_to(paths.REPO_ROOT)} is out of date: run tools/schematic/build_hands.py")
            return 1
        print("hands.csv up to date")
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(paths.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

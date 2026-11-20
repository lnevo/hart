"""build_hands.py [--check]

Write jmri/layouts/hart/data/schematic/hands.csv: the hand (R or L, the diverging side seen from the points) of every
main and upper level switch, read from the AnyRail plan graph (inputs/main.json, node `hand` +1 = R, -1 = L) and
renamed to the owner's switch numbers by the relabel edit in plan_overrides.json's main_upper section. Switch 225
is the double crossover: it has no hand, so it is left out of the file. These are plan hands (owner decision
2026-11-14), not the schematic's drawn hands: 101A/B, 103A/B, 105, 107, 109 and 111 are flipped on the sheet. Provisional until the
Layout Editor import.

--check regenerates in memory and exits 1 if the file differs.
"""
import csv
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS and hartlib paths
from hartlib import railroad  # noqa: E402  the plan overrides, read and checked once

GRAPH = pd.GRAPHS / "main.json"
OVERRIDES = railroad.Sources.under().plan_overrides
OUT = railroad.Sources.under().hands
SOURCE = "plan geometry (provisional)"


def natural(name):
    m = re.match(r"(\d+)(.*)", name)
    return int(m.group(1)), m.group(2)


KNOWN_EDITS = {"relabel"}     # switch-changing edits this script reads; any other fails loudly


def build():
    """The file's text. Fails on anything it cannot vouch for: an edit kind it does not read (a `switch`,
    `crossover` or `remove` edit changes which switches exist), a relabel key with no plan node other than the one
    double crossover, or a graph hand that is not +1 or -1."""
    nodes = json.loads(GRAPH.read_text())["nodes"]
    # hands.csv is the hands layer: it reads the inputs only (railroad.LAYERS)
    rr = railroad.Railroad(railroad.Sources.under().but(plan_overrides=OVERRIDES), upto="inputs")
    try:
        edits, relabel = rr.plan_overrides.edits, rr.plan_overrides.relabel
    except railroad.FactsError as exc:
        raise SystemExit(f"build_hands.py: {exc}") from None
    unknown = sorted({e["op"] for e in edits} - KNOWN_EDITS)
    if unknown:
        raise SystemExit(f"build_hands.py does not read {unknown} edits yet: teach it before using hands.csv")
    by_label = {n["label"]: n for n in nodes.values() if n["kind"] == "switch"}
    by_label.update({i: n for i, n in nodes.items() if n["kind"] == "switch"})      # a switch the plan numbers no part for
    dx = {n["label"] for n in nodes.values() if n["kind"] == "dx"}
    rows = {}
    for old, new in relabel.items():
        node = by_label.get(old)
        if node is None:
            if old in dx:
                continue                    # the double crossover: no hand
            raise SystemExit(f"relabel {old!r} -> {new!r}: no switch {old!r} in {GRAPH.name}")
        if node.get("hand") in (1, -1):
            rows[new] = "R" if node["hand"] == 1 else "L"
        else:
            raise SystemExit(f"{old} ({new}): plan hand {node.get('hand')!r} is not +1 or -1")
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["switch", "hand", "source"])
    for name in sorted(rows, key=natural):
        w.writerow([name, rows[name], SOURCE])
    return out.getvalue()


def main(argv):
    if set(argv) - {"--check"}:
        print(__doc__)
        return 2
    text = build()
    if "--check" in argv:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"{OUT.relative_to(pd.REPO)} is out of date: run tools/schematic/build_hands.py")
            return 1
        print("hands.csv up to date")
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(pd.REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

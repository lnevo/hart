"""Print PLAN_LOOP_MM and PLAN_TURNOUT_MM for infer_block_lengths.py from the decoded plan.

Run in the scratch folder after parse1, parse2, graph and `anygraph.py 1` (staging level).
Plan turnout ids (Txx) are mapped to HART switches in docs/jmri/speedmatching/ANYRAIL_LENGTHS.md.
"""
import json

A = json.load(open("any_c1.json"))


def run(t, leg):
    return A[str(t)]["legs"][leg]["cm"] * 10


def through(t, leg):
    return A[str(t)]["leglen"][leg] * 10


# the 2026-11-08 test route, from Switch 5's points; (name, mm, OS sensor whose centre it is)
ROUTE = [
    ("Sw5 T106 A->B", through(106, "B"), "Switch 5"),
    ("East Main Ext + Sw7 + Main East", run(106, "B"), None),
    ("Sw33 T77 C->A", through(77, "C"), "Switch 33"),
    ("East Lead", run(77, "A"), None),
    ("Sw35 T98 A->B", through(98, "B"), "Switch 35a"),
    ("T98-T129", run(98, "B"), None),
    ("Sw37 T129 A->C", through(129, "C"), None),
    ("K loop", run(129, "C"), None),
    ("Sw39 T56 C->A", through(56, "C"), None),
    ("Sw35 T55 A->B", through(55, "B"), "Switch 35b"),
    ("West Main Ext", run(55, "B"), None),
    ("Sw23 T58 B->A", through(58, "B"), "Switch 23a"),
    ("Main West", run(58, "A"), None),
    ("T43 A->B (crossover not built)", through(43, "B"), None),
    ("T43-T116", run(43, "B"), None),
    ("Sw1 T116 A->C", through(116, "C"), "Switch 1"),
    ("Brick-Plane", run(116, "C"), None),
]

if __name__ == "__main__":
    pos, pins = 0.0, {}
    for name, mm, sensor in ROUTE:
        if sensor:
            pins[sensor] = round(pos + mm / 2)
        pos += mm
    print("PLAN_LOOP_MM = %.1f" % pos)
    print("PLAN_TURNOUT_MM =", pins)

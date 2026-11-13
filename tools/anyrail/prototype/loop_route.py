"""Print the plan constants of both test routes for infer_block_lengths.py from the decoded plan:
PLAN_LOOP_MM and PLAN_TURNOUT_MM (loop 1), PLAN_LOOP2_MM and PLAN_LOOP2_TURNOUT_MM (loop 2).

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

# loop 2: Switch 5 thrown into Scale and Barn, then Switch 15 (T52) and Track S-R (the plan's T41
# crossover is not built: counted as track), Switch 23b (T118) and 31 (T59), Switch 33 (T77), and
# on as loop 1 from East Lead. Switches 23b, 31 and the unbuilt T41 carry no pin; 7 and 13 are not
# on the plan as turnouts yet: they are what the run is for.
LOOP1_FROM_EAST_LEAD = ROUTE[3:]  # East Lead on; the same stretch as loop 1
ROUTE2 = [
    ("Sw5 T106 A->C", through(106, "C"), "Switch 5"),
    ("Scale, Switch 7, Barn, Switch 13 (T106C run)", run(106, "C"), None),
    ("Sw15 T52 A->B", through(52, "B"), "Switch 15"),
    ("T52 run to T41", run(52, "B"), None),
    ("T41 A->B (crossover not built)", through(41, "B"), None),
    ("Track S-R run T41B", run(41, "B"), None),
    ("Sw23b T118 B->A", through(118, "B"), None),
    ("T118 run to T59", run(118, "A"), None),
    ("Sw31 T59 B->A", through(59, "B"), None),
    ("T59 run to T77", run(59, "A"), None),
    ("Sw33 T77 B->A", through(77, "B"), "Switch 33"),
] + LOOP1_FROM_EAST_LEAD


def walk(route):
    pos, pins = 0.0, {}
    for name, mm, sensor in route:
        if sensor:
            pins[sensor] = round(pos + mm / 2)
        pos += mm
    return pos, pins


if __name__ == "__main__":
    for tag, route in (("", ROUTE), ("2", ROUTE2)):
        total, pins = walk(route)
        print("PLAN_LOOP%s_MM = %.1f" % (tag, total))
        print("PLAN_LOOP%s_TURNOUT_MM =" % tag if tag else "PLAN_TURNOUT_MM =", pins)

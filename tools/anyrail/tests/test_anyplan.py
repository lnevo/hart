"""tools/anyrail/anyplan.py: the record shapes on made-up bytes, the part types on made-up ends, and, where the
owner's plans are on this machine (never in CI: the .any files stay private), plan 5.3c against the graphs built
from AnyRail's own export, and the checks the owner asked of 5.3c."""
import collections
import json
import math
import io
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import anyplan as A  # noqa: E402

REPO = HERE.parents[2]
PLANS = Path.home() / "Documents/Layout"
PLAN_C = PLANS / "Lee Nevo Design Version 5.3c.any"
INPUTS = REPO / "jmri/layouts/hart/data/schematic/inputs"


def u64(n):
    return struct.pack("<Q", n)


def text(s):
    return u64(len(s)) + s.encode()


def name(cat, lib):
    return b"\x01\x02" + text(cat) + text(lib) + b"\x00" * 6


def end(x, y, z, deg, system, head=b"X\x00\x01\x00\x00\x00\x02\x00\x00\x00"):
    return head + struct.pack("<4d", x, y, z, math.radians(deg)) + text(system) + b"\x00\x00"


def curve(points, tag=b"6\x00"):
    out = u64(len(points))
    for k, (x, y) in enumerate(points):
        out += tag + struct.pack("<I", 100 + k) + struct.pack("<2d", x, y)
    return out


def plan_bytes():
    """A flex piece (first in the file, so its first end has the longer first-of-its-kind header), a right-hand
    turnout of another maker's library, a placed object and the junk shapes found in real headers."""
    return b"".join([
        b"\x00" * 16, end(0.0, 0.0, 0.0, 0.0, "PSL83"),                     # a header: (0, 0) is no place
        end(1e-320, 5e-318, 0.0, 0.0, "PSL83"),                              # subnormal junk
        name("GENERIC", "H0GENSC"), end(50.0, 50.0, 0.0, 0.0, "H0GENSC"),   # a placed object: one end
        name("FLEX-1", "ABC87"),
        end(10.0, 20.0, -38.1, 180.0, "ABC87", head=b"X\x00\x01\x04\x00\x00\x00\x83\x5a\x00\x00\x01\x00\x00\x00\x00"),
        end(40.0, 20.0, -38.1, 0.0, "ABC87"),
        curve([(10.0, 20.0), (20.0, 20.0), (30.0, 20.0), (40.0, 20.0)]),
        name("83999", "XYZ87F19"),                                           # a library longer than its system
        end(40.0, 20.0, -38.1, 180.0, "XYZ87"),
        end(63.4, 20.0, -38.1, 0.0, "XYZ87"),
        end(63.3, 22.5, -38.1, 9.5, "XYZ87"),
    ])


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        cls.tmp = Path(folder.name) / "plan.any"
        cls.tmp.write_bytes(plan_bytes())
        cls.parts = A.read(cls.tmp)

    def test_track_parts_only_in_file_order(self):
        self.assertEqual([(p["index"], p["name"]) for p in self.parts], [(0, "FLEX-1"), (1, "83999")])

    def test_the_first_end_point_with_its_longer_header_is_read(self):
        self.assertEqual([(e["x"], e["y"]) for e in self.parts[0]["ends"]], [(10.0, 20.0), (40.0, 20.0)])

    def test_a_library_is_track_when_its_name_starts_with_a_track_system(self):
        self.assertEqual((self.parts[1]["library"], self.parts[1]["system"]), ("XYZ87F19", "XYZ87"))

    def test_the_flex_curve_with_this_files_tag_gives_its_length(self):
        self.assertAlmostEqual(self.parts[0]["cm"], 30.0, places=3)
        self.assertIsNone(self.parts[1]["cm"])

    def test_the_parts_list_holds_name_and_x_y_z_only(self):
        self.assertEqual(A.parts_list(self.parts)[0],
                         {"name": "FLEX-1", "eps": [{"x": 10.0, "y": 20.0, "z": -38.1},
                                                    {"x": 40.0, "y": 20.0, "z": -38.1}]})

    def test_the_two_parts_join_and_runs_end_at_free_ends(self):
        links, free = A.joins(self.parts)
        self.assertEqual(links, [(0, 1, 1, 0)])
        self.assertEqual(sorted(free), [(0, 0), (1, 1), (1, 2)])
        self.assertEqual(sorted((r[1], r[2], round(r[4], 3)) for r in A.runs(self.parts, links)),
                         [(0, None, 30.0), (1, None, 0.0), (2, None, 0.0)])

    def test_a_one_ended_part_is_a_track_end_that_ends_a_run(self):
        stop = self.tmp.with_name("stop.any")
        stop.write_bytes(plan_bytes() + name("STOP-1", "ABC87") + end(63.4, 20.0, -38.1, 180.0, "ABC87"))
        parts = A.read(stop)
        self.assertEqual(parts[2]["kind"], "end")
        links, free = A.joins(parts)
        self.assertIn((1, 1, 2, 0), links)
        self.assertIn((1, 1, None, None, 0.0), A.runs(parts, links))

    def test_a_part_with_five_ends_stops_the_read(self):
        bad = self.tmp.with_name("bad.any")
        bad.write_bytes(plan_bytes() + name("ODD-1", "ABC87") +
                        b"".join(end(90.0 + i, 90.0, 0.0, 0.0, "ABC87") for i in range(5)))
        with self.assertRaisesRegex(A.PlanError, "more than four ends"):
            A.read(bad)

    def test_a_string_followed_by_a_printable_byte_is_still_read(self):
        """The string's length prefix decides where it ends, whatever comes after it."""
        self.assertEqual(A._names(b"\x01" + text("SL-E83") + text("PSL83") + b"A\x00\x00"), [(1, "SL-E83", "PSL83")])
        rec = struct.pack("<4d", 5.0, 6.0, 0.0, 0.0) + text("PSL83") + b"Z"
        self.assertEqual(A._end_records(rec), [(0, 5.0, 6.0, 0.0, 0.0, "PSL83")])

    def test_the_command_line_says_what_is_wrong(self):
        empty = self.tmp.with_name("empty2.any")
        empty.write_bytes(b"\x00" * 64)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(A.main([str(empty), "--report"]), 2)
        self.assertIn("no track end points", err.getvalue())

    def test_a_file_with_no_track_says_so(self):
        empty = self.tmp.with_name("empty.any")
        empty.write_bytes(b"\x00" * 64)
        with self.assertRaisesRegex(A.PlanError, "no track end points"):
            A.read(empty)


def ends(*spec):
    return [dict(x=x, y=y, z=z, a=math.radians(deg)) for x, y, z, deg in spec]


class Kinds(unittest.TestCase):
    """Ends as AnyRail stores them: y grows down the screen, a turnout's straight leg faces opposite its points."""

    def test_straight_turnouts_by_hand(self):
        right = A.classify(ends((0, 0, 0, 180), (23.4, 0, 0, 0), (23.3, 2.5, 0, 9.5)))
        left = A.classify(ends((0, 0, 0, 180), (23.4, 0, 0, 0), (23.3, -2.5, 0, -9.5)))
        self.assertEqual((right["kind"], right["hand"], right["curved"], right["points"]), ("turnout", "R", False, 0))
        self.assertEqual((left["hand"], left["straight"], left["diverging"]), ("L", 1, 2))

    def test_a_curved_turnout(self):
        k = A.classify(ends((0, 0, 0, 180), (28.0, -2.4, 0, -10.4), (27.5, -4.9, 0, -20.0)))
        self.assertEqual((k["kind"], k["hand"], k["curved"], k["straight"]), ("turnout", "L", True, 1))

    def test_four_ended_parts(self):
        self.assertEqual(A.classify(ends((0, 0, 0, 180), (20, 0, 0, 0), (20, 3, 0, 9), (20, -3, 0, -9)))["kind"],
                         "threeway")
        self.assertEqual(A.classify(ends((0, 0, 0, 180), (0, 5, 0, 180), (48, 0, 0, 0), (48, 5, 0, 0)))["kind"],
                         "double_crossover")
        self.assertEqual(A.classify(ends((0, 0, 0, 180), (0, 5, 0, 166), (48, 0, 0, 0), (48, 5, 0, -14)))["kind"],
                         "crossing")
        self.assertEqual(A.classify(ends((0, 0, 0, 180), (10, 0, 0, 0), (5, -5, 0, -90), (5, 5, 0, 90)))["kind"],
                         "crossing")                                         # a square diamond is no three-way

    def test_a_part_with_no_curve_is_measured_from_its_ends(self):
        self.assertAlmostEqual(A.fixed_length(ends((0, 0, 0, 180), (20, 0, 0, 0))), 20.0)
        r = 50.0                                                              # a quarter circle of radius 50
        self.assertAlmostEqual(A.fixed_length(ends((0, 0, 0, 180), (r, r, 0, 90))), math.pi * r / 2, places=6)


class Joins(unittest.TestCase):
    def part(self, i, *spec):
        return dict(index=i, ends=ends(*spec), cm=None, curve=None, kind="track")

    def test_a_gap_between_facing_ends_is_reported_once_and_side_by_side_ends_not_at_all(self):
        gap = [self.part(0, (0, 0, 0, 180), (10, 0, 0, 0)), self.part(1, (11, 0, 0, 180), (20, 0, 0, 0))]
        self.assertEqual(A.report(gap)[-1].split(": ", 1)[1], "[(0, 1, 1.0, 0)]")
        side = [self.part(0, (0, 0, 0, 180), (10, 0, 0, 0)), self.part(1, (0, 4, 0, 180), (10, 4, 0, 0))]
        self.assertTrue(A.report(side)[-1].endswith("none"))

    def test_ends_at_different_heights_do_not_join(self):
        links, free = A.joins([self.part(0, (0, 0, 0, 0), (10, 0, 0, 0)), self.part(1, (10, 0, 10.8, 0), (20, 0, 10.8, 0))])
        self.assertEqual((links, len(free)), ([], 4))

    def test_three_ends_on_one_spot_stop(self):
        with self.assertRaisesRegex(A.PlanError, "more than two"):
            A.joins([self.part(i, (0, 0, 0, 0), (10 + i, 5, 0, 0)) for i in range(3)])


class Cuts(unittest.TestCase):
    """A run that climbs between two levels is parted at the cut height, each side's share from its pieces' grades."""

    @staticmethod
    def rise():
        """Turnout 0 at -38 cm, two 100 cm flex pieces climbing to 0, turnout 3 at 0 cm; turnout 0's other legs free."""
        def part(i, *spec, cm=None):
            return dict(index=i, ends=ends(*spec), cm=cm, curve=None)
        return [part(0, (0, 0, -38, 180), (-10, 0, -38, 0), (-10, 2, -38, 0)),
                part(1, (0, 0, -38, 0), (100, 0, -19, 0), cm=100.0),
                part(2, (100, 0, -19, 0), (200, 0, 0, 0), cm=100.0),
                part(3, (200, 0, 0, 180), (210, 0, 0, 0), (210, 2, 0, 0))]

    def test_the_cut_parts_the_run_by_height(self):
        parts = self.rise()
        links, _ = A.joins(parts)
        (c,) = A.level_cuts(parts, links, -5.0)
        self.assertEqual((c["low"], c["high"]), ((0, 0), (3, 0)))
        self.assertAlmostEqual(c["low_cm"], 100 + 100 * 14 / 19)            # -19 to -5 of the second piece's 19 cm
        self.assertAlmostEqual(c["low_cm"] + c["high_cm"], 200.0)
        self.assertEqual(A.level_cuts(parts, links, 5.0), [])                # nothing climbs through 5 cm

    def test_each_graph_gets_a_stub_on_the_leg_it_lacks(self):
        cut = dict(low=(0, 0), high=(3, 0), low_cm=173.7, high_cm=26.3)
        g = dict(nodes={"S": dict(kind="switch", label="T0", xy=[0.0, 0.0], dirs={"B": [1.0, 0.0]}),
                        "E": dict(kind="end", label="", xy=[-50.0, 0.0])},
                 edges=[dict(id="e0", u="S", up="A", v="E", vp="E", cm=10.0),
                        dict(id="e1", u="S", up="C", v="E", vp="E", cm=10.0)])
        self.assertEqual(A.add_cut_stubs(g, [cut], -5.0), ["T0"])
        stub = g["edges"][-1]
        self.assertEqual((stub["id"], stub["u"], stub["up"], stub["v"], stub["cm"]), ("e2", "S", "B", "CUT:T0", 173.7))
        self.assertEqual((g["nodes"]["CUT:T0"]["cut"], g["nodes"]["CUT:T0"]["xy"]), (-5.0, [A.STUB_PX, 0.0]))
        with self.assertRaisesRegex(A.PlanError, "lacks none"):               # read twice: no leg left to give
            A.add_cut_stubs(g, [cut], -5.0)


@unittest.skipUnless(PLAN_C.exists(), "the owner's plan 5.3c is not on this machine")
class Plan53cGraphs(unittest.TestCase):
    """Read from the .any file, 5.3c has the same switch-to-switch runs as the graphs in inputs/, which the plugin
    built from AnyRail's JMRI export with this reader's parts list; each run through the helix is the two stubs
    up to the -5 cm cut (--cut -5 --stubs), and the export draws the three-way as two turnouts the parts cannot name."""

    def test_same_runs_as_the_export(self):
        parts = A.read(PLAN_C)
        links, _ = A.joins(parts)
        threeway = next(f"T{p['index']}" for p in parts if p["kind"] == "threeway")
        cuts = {frozenset((f"T{c['low'][0]}", f"T{c['high'][0]}")) for c in A.level_cuts(parts, links, -5.0)}

        def label(graph, n):
            d = graph["nodes"][n]
            if d["kind"] == "end":
                return "CUT" if "cut" in d else "END"
            return d["label"] if d["label"].startswith("T") else threeway

        want, stubs = collections.Counter(), collections.Counter()
        for f in ("staging.json", "main.json"):
            g = json.loads((INPUTS / f).read_text())
            for e in g["edges"]:
                u, v = label(g, e["u"]), label(g, e["v"])
                if "CUT" in (u, v):
                    stubs[u if v == "CUT" else v] += 1
                elif u != v or u != threeway:
                    want[tuple(sorted((u, v)))] += 1
        got = collections.Counter()
        for a, _, b, _, _ in A.runs(parts, links):
            u, v = f"T{a}", (f"T{b}" if b is not None else "END")
            if frozenset((u, v)) not in cuts:
                got[tuple(sorted((u, v)))] += 1
        got = collections.Counter({k: (n if "END" in k else n // 2) for k, n in got.items()})
        self.assertEqual(+(want - got), collections.Counter(), "runs in the export graphs the .any file lacks")
        self.assertEqual(+(got - want), collections.Counter(), "runs in the .any file the export graphs lack")
        self.assertEqual(stubs, collections.Counter({t: 1 for c in cuts for t in c}))      # one stub each side


@unittest.skipUnless(PLAN_C.exists(), "the owner's plan 5.3c is not on this machine")
class Plan53c(unittest.TestCase):
    """What the owner fixed in 5.3c (2026-11-19) stays fixed: one connected railroad through the helix, every switch
    level, no track end that nearly meets another, and no flat track left between the main and upper levels."""

    @classmethod
    def setUpClass(cls):
        cls.parts = A.read(PLAN_C)
        cls.links, cls.free = A.joins(cls.parts)

    def test_one_connected_piece(self):
        self.assertEqual(len(A.components(self.parts, self.links)), 1)

    def test_every_switch_is_level(self):
        self.assertEqual([p["index"] for p in self.parts if len(p["ends"]) > 2
                          and max(e["z"] for e in p["ends"]) - min(e["z"] for e in p["ends"]) > A.LEVEL_CM], [])

    def test_no_free_end_nearly_meets_another(self):
        self.assertIn("none", A.report(self.parts)[-1])

    def test_no_flat_track_between_the_levels(self):
        flat = [p["index"] for p in self.parts if all(1.5 < e["z"] < 5 for e in p["ends"])
                and max(e["z"] for e in p["ends"]) - min(e["z"] for e in p["ends"]) <= A.LEVEL_CM]     # grades pass
        self.assertEqual(flat, [])


if __name__ == "__main__":
    unittest.main()

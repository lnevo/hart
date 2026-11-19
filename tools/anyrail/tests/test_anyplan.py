"""tools/anyrail/anyplan.py: the record shapes on made-up bytes, the part types on made-up ends, and, where the
owner's plans are on this machine (never in CI: the .any files stay private), plan 5.3b against the graphs built
from AnyRail's own export, and the checks the owner asked of 5.3c."""
import collections
import json
import math
import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import anyplan as A  # noqa: E402

REPO = HERE.parents[2]
PLANS = Path.home() / "Documents/Layout"
PLAN_B = PLANS / "Lee Nevo Design Version 5.3b.any"
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
        cls.path = Path(cls.__module__.replace(".", "_") + "_plan.any")
        cls.tmp = Path(__import__("tempfile").mkdtemp()) / "plan.any"
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

    def test_a_part_with_one_end_in_a_track_library_stops_the_read(self):
        bad = self.tmp.with_name("bad.any")
        bad.write_bytes(plan_bytes() + name("FLEX-2", "ABC87") + end(90.0, 90.0, 0.0, 0.0, "ABC87"))
        with self.assertRaisesRegex(A.PlanError, "unsupported number of ends"):
            A.read(bad)

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


class Joins(unittest.TestCase):
    def part(self, i, *spec):
        return dict(index=i, ends=ends(*spec), cm=None)

    def test_ends_at_different_heights_do_not_join(self):
        links, free = A.joins([self.part(0, (0, 0, 0, 0), (10, 0, 0, 0)), self.part(1, (10, 0, 10.8, 0), (20, 0, 10.8, 0))])
        self.assertEqual((links, len(free)), ([], 4))

    def test_three_ends_on_one_spot_stop(self):
        with self.assertRaisesRegex(A.PlanError, "more than two"):
            A.joins([self.part(i, (0, 0, 0, 0), (10 + i, 5, 0, 0)) for i in range(3)])


@unittest.skipUnless(PLAN_B.exists(), "the owner's plan 5.3b is not on this machine")
class Plan53b(unittest.TestCase):
    """Read from the .any file, 5.3b has the same switch-to-switch runs as the graphs in inputs/, which the plugin
    built from AnyRail's JMRI export with the old reader's parts list (no double crossover, part 0 misread)."""

    def test_same_runs_as_the_export(self):
        parts = A.read(PLAN_B)
        old = json.loads((INPUTS / "parts.json").read_text())
        key = lambda eps: {(round(e["x"], 1), round(e["y"], 1)) for e in eps}      # noqa: E731
        new_by_key = [(p, key(p["ends"])) for p in parts]

        def new_index(o):           # the old reader dropped part 0's misread third end: match on the ends it kept
            hits = [p["index"] for p, k in new_by_key if p["name"] == o["name"] and key(o["eps"]) <= k]
            self.assertEqual(len(hits), 1, o["name"])
            return hits[0]
        old_to_new = {f"T{i}": f"T{new_index(o)}" for i, o in enumerate(old) if len(o["eps"]) >= 3}
        by_kind = {p["kind"]: f"T{p['index']}" for p in parts if p["kind"] in ("threeway", "double_crossover")}
        unmatched = {"12": f"T{new_index(old[0])}", "50": by_kind["threeway"], "51": by_kind["threeway"]}

        def label(graph, n):
            d = graph["nodes"][n]
            if d["kind"] == "end":
                return "END"
            if d["kind"] == "dx":
                return by_kind["double_crossover"]
            return old_to_new.get(d["label"]) or unmatched[d["label"]]

        want = collections.Counter()
        for f in ("staging.json", "main.json"):
            g = json.loads((INPUTS / f).read_text())
            for e in g["edges"]:
                u, v = label(g, e["u"]), label(g, e["v"])
                if u != v or u != by_kind["threeway"]:          # the export draws the three-way as two turnouts
                    want[tuple(sorted((u, v)))] += 1
        links, _ = A.joins(parts)
        got = collections.Counter()
        for a, _, b, _, _ in A.runs(parts, links):
            u, v = f"T{a}", (f"T{b}" if b is not None else "END")
            got[tuple(sorted((u, v)))] += 1
        got = collections.Counter({k: (n if "END" in k else n // 2) for k, n in got.items()})
        self.assertEqual(+(want - got), collections.Counter(), "runs in the export graphs the .any file lacks")
        self.assertEqual(+(got - want), collections.Counter(), "runs in the .any file the export graphs lack")


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

"""build_device_map.py: placeholder control points and LCOS device names for the main and upper levels."""
from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_device_map", ROOT / "tools/schematic/build_device_map.py")
BD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BD)
R = BD.railroad


def cp(name, level, *switches):
    """An in-memory control point (control_points_main_upper.csv row)."""
    return R.LevelControlPoint(0, name.lower().replace(" ", "_"), name, level, switches, "West")


def rows():
    with BD.OUT.open(newline="") as f:
        return list(csv.DictReader(f))


class Pure(unittest.TestCase):
    def test_base_drops_half_letter_and_star(self):
        self.assertEqual([BD.base(x) for x in ("129A", "135B", "223*", "105")], ["129", "135", "223", "105"])

    def test_control_point_lists_only_its_own_band_halves(self):
        cps = [cp("CP 129", 2, "129", "135"), cp("CP 223", 3, "223")]
        by_level = {2: {"129A", "135A", "105"}, 3: {"129B", "135B", "223*"}}
        got = BD.overrides_keys(cps, by_level)
        self.assertEqual(got["CP 129"]["switches"], ["129A", "135A"])
        self.assertEqual(got["CP 223"]["switches"], ["223*"])          # the moved switch keeps its star

    def test_switch_missing_from_its_band_fails(self):
        with self.assertRaises(BD.MapError):
            BD.overrides_keys([cp("CP 9", 2, "9")], {2: {"105"}})

    def test_switch_in_two_control_points_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "cps.csv"
            p.write_text("cp_id,cp_name,level,switches,area,notes\na,CP 1,2,\"1,3\",West,\nb,CP 3,2,3,West,\n")
            with self.assertRaisesRegex(BD.MapError, "switch 3 is in CP 1 and CP 3"):
                BD.load_cps(p)

    def test_every_switch_needs_a_control_point_or_a_local_row(self):
        bands = [("Main level", {"nodes": {"a": dict(kind="switch", label="101A"), "b": dict(kind="switch", label="105")},
                                 "strands": {}, "R": {"srow": {}}, "rail": {}}, {})]
        cps = [cp("CP 105", 2, "105")]
        over = {"edits": [{"op": "relabel", "map": {}}]}
        with self.assertRaisesRegex(BD.MapError, "switch 101 is in no control point"):
            BD.build(bands, {}, lambda b: [], over, cps, [])
        with self.assertRaisesRegex(BD.MapError, "switch 105 is in a control point and in"):
            BD.build(bands, {}, lambda b: [], over, cps, [], [R.LocalSwitch(0, "105", 2, "West")])

    def test_track_names(self):
        sw, hx, bump = (lambda n: ("sw", n)), (lambda h: ("helix", h)), ("bumper", None)
        found = [dict(ends=(sw("101"), sw("105")), row=2, trial=["Track e2"]),
                 dict(ends=(sw("105"), sw("101")), row=1, trial=["Track e1"]),
                 dict(ends=(sw("113"), bump), row=0, trial=["Track e3"]),
                 dict(ends=(sw("107"), sw("107")), row=0, trial=["Track e4"]),
                 dict(ends=(sw("135"), hx("H1")), row=0, trial=["Track e5"])]
        BD.track_names(found)
        self.assertEqual([t["name"] for t in found],
                         ["Track 101-105 2", "Track 101-105 1", "Track 113 Spur", "Track 107 Loop", "Track 135-H1"])

    def test_nodes_pack_lcos_ids_and_overflow_in_area_order(self):
        nodes = BD.Nodes([R.LcosNode(0, 2, "West", 33), R.LcosNode(0, 2, "West", 43)])
        n = nodes.pick(2, "West", "turnout", 8)
        self.assertEqual(n, 33)
        self.assertEqual([nodes.take(n, "turnout")[1] for _ in range(8)][::7], [3308, 3315])
        self.assertEqual(nodes.pick(2, "West", "turnout"), 43)        # node 33 is full
        self.assertEqual(nodes.take(43, "block"), (0, 4300))
        self.assertEqual(nodes.take(43, "signal"), (0, 4332))
        self.assertEqual(nodes.take(43, "sensor"), (0, 4367))
        with self.assertRaises(BD.MapError):
            nodes.pick(2, "North", "block")


class Output(unittest.TestCase):
    """The committed map against the rules it was built to (run build_device_map.py after changing inputs)."""

    def test_every_switch_has_a_turnout_two_feedbacks_and_an_os_block(self):
        have = rows()
        cp_sw = [s for c in BD.load_cps() for s in c.switches]
        local = [row.switch for row in R.read_local_switches(BD.LOCAL)]
        dx = {"225"}                            # the double crossover: an OS block and a detector per corner
        for s in cp_sw + local:
            os = [f"{s}{c}" for c in "abcd"] if s in dx else [s]
            kinds = sorted(x["layer"] for x in have if x["user_name"] in
                           [f"Switch {s}", f"DCC Switch {s}", f"FB Switch {s} N", f"FB Switch {s} R"]
                           + [f"OS Switch {o}" for o in os] + [f"BS Switch {o}" for o in os])
            want = sorted(["block"] * len(os) + ["fb", "fb"] + ["occupancy"] * len(os) + ["turnout", "turnout"])
            self.assertEqual(kinds, want, s)

    def test_dcc_continues_from_120_in_switch_order(self):
        got = [(x["user_name"], int(x["dcc"])) for x in rows() if x["layer"] == "turnout"
               and x["user_name"].startswith("Switch ")]
        got.sort(key=lambda g: int(g[0].split()[1]))
        self.assertEqual([d for _, d in got], list(range(120, 120 + len(got))))
        aliases = {x["user_name"]: x["system_name"] for x in rows() if x["user_name"].startswith("DCC Switch ")}
        self.assertEqual(aliases["DCC Switch 101"], "MTT120")

    def test_detection_only_on_the_main_line(self):
        occ = {y["user_name"]: y for y in rows() if y["layer"] == "occupancy"}
        for x in rows():
            if x["layer"] == "block" and "off the main line" in x["notes"]:
                bs = "BS " + x["user_name"].removeprefix("Track ").removeprefix("OS ")
                # a virtual sensor, but no detector planned: dark until decided
                self.assertEqual((occ[bs]["system_name"], occ[bs]["node"], occ[bs]["notes"]), ("", "", BD.NO_DETECTOR))

    def test_system_names_unique_and_in_lcos_bands(self):
        seen = set()
        for x in rows():
            if not x["system_name"] or x["layer"] == "mast":
                continue
            self.assertFalse(x["system_name"].startswith(("IS", "IT", "IH:")), x["user_name"])  # physical only
            self.assertNotIn(x["system_name"], seen)
            seen.add(x["system_name"])
            uid = int(x["system_name"][3:] if x["layer"] != "head" else x["system_name"][2:]) % 100
            if x["system_name"].startswith("MTT"):
                continue                                        # LCC alias: its number is the DCC address
            band = {"turnout": range(8, 16), "occupancy": range(0, 8), "head": range(32, 48), "fb": range(67, 100)}
            self.assertIn(uid, band[x["layer"]], x["user_name"])

    def test_no_staging_node_reused(self):
        staging = {1, 2, 3, 4, 5, 11, 12, 13}
        self.assertFalse({int(x["node"]) for x in rows() if x["node"]} & staging)

    def test_mast_names_follow_adr005(self):
        import re
        for x in rows():
            if x["layer"] == "mast":
                m = re.fullmatch(r"Mast (\d+)([LR])([AB]?)", x["user_name"])
                self.assertIsNotNone(m, x["user_name"])
                self.assertEqual(int(m.group(1)) % 2, 0)
                self.assertEqual(x["comment"].split(" | Switch ")[1], str(int(m.group(1)) - 1))

    def test_boards_follow_the_wiring_rules(self):
        import re
        have = rows()
        by_node = {}
        for x in have:
            if x["node"] and not x["system_name"].startswith("MTT"):
                by_node.setdefault(x["node"], []).append(x)
        for node, xs in by_node.items():
            turnouts = [x for x in xs if x["layer"] == "turnout"]
            n12 = -(-len(turnouts) // 4)
            detectors = any(x["layer"] == "occupancy" for x in xs)
            boards = set()
            for x in xs:
                m = re.search(r"OU: (\d+) Ports: ([\d,]+)$", x["comment"])
                if not m:
                    continue
                board, pins = int(m.group(1)), [int(p) for p in m.group(2).split(",")]
                boards.add(board)
                if x["layer"] == "turnout":
                    self.assertLessEqual(board, n12, x["user_name"])
                if x["layer"] == "head":
                    self.assertGreater(board, n12, x["user_name"])          # 5V boards follow the 12V ones
                    self.assertEqual(pins, list(range(pins[0], pins[0] + 3)), x["user_name"])
                    if detectors and board == n12 + 1:
                        self.assertNotIn(8, pins, x["user_name"])          # calibration pin
            self.assertLessEqual(max(boards, default=0), BD.MAX_OU, node)

    def test_a_loop_back_into_its_control_point_has_home_signals(self):
        loop = {x["user_name"]: x["notes"] for x in rows() if x["layer"] == "mast" and " Loop" in x["notes"]}
        self.assertEqual(loop, {"Mast 108LA": "home signal from Track 107 Loop 1",      # the balloon at CP 107
                                "Mast 108LB": "home signal from Track 107 Loop 2"})

    def test_the_balloon_loop_is_two_blocks_and_loop_1_keeps_its_detector(self):
        """Two masts facing one loop block into one OS block would be one mast to JMRI (LayoutBlockManager.
        getFacingBean returns one per block pair), so the loop is two blocks, parted halfway (owner, 2026-11-16).
        Loop 1 keeps the loop's detector (node 33 block 6); Loop 2's is not on a node yet, so no node or input moved."""
        have = {(x["layer"], x["user_name"]): x for x in rows()}
        self.assertNotIn(("block", "Track 107 Loop"), have)
        for half, leg in ((1, "B"), (2, "C")):
            block = have[("block", f"Track 107 Loop {half}")]
            self.assertEqual(block["trial_name"], f"Track e33 {half}")
            self.assertTrue(block["notes"].startswith(f"388.5 cm, half of the balloon loop from leg {leg}"))
        self.assertEqual(have[("occupancy", "BS 107 Loop 1")]["system_name"], "M2S3305")
        loop2 = have[("occupancy", "BS 107 Loop 2")]
        self.assertEqual((loop2["system_name"], loop2["node"], loop2["notes"]), ("", "", BD.NOT_WIRED))
        self.assertEqual(loop2["jmri_name"], "IS:HART:C3:B:107_Loop_2")

    def test_a_double_crossover_is_a_block_per_corner(self):
        """With one OS block, or two, JMRI 5.16 records a through path between the two legs on one side of a
        double crossover (LayoutBlock.addThroughPath) and discovery paired 226RA with 224LB across it. Each corner
        is its own block, corner a keeps the detector, and each mast protects its own corner (226RA at A, 226RB at
        D: the two legs on the west side, in different blocks)."""
        have = {(x["layer"], x["user_name"]): x for x in rows()}
        self.assertNotIn(("block", "OS Switch 225"), have)
        self.assertEqual(have[("occupancy", "BS Switch 225a")]["system_name"], "M2S2100")
        for c in "bcd":
            corner = have[("occupancy", f"BS Switch 225{c}")]
            self.assertEqual((corner["system_name"], corner["notes"]), ("", BD.NOT_WIRED))
            self.assertEqual(corner["jmri_name"], f"IS:HART:C3:B:OS225{c}")
        self.assertEqual(have[("mast", "Mast 226RA")]["notes"], "home signal from Track 223-225 1 into OS Switch 225a")
        self.assertEqual(have[("mast", "Mast 226RB")]["notes"], "home signal from Track 223-225 2 into OS Switch 225d")

    def test_every_device_has_a_virtual_name_from_its_own_name(self):
        """jmri_name (the JMRI device the panels use) of every turnout, occupancy, head and mast row comes from the
        row's user name alone, never from its draft physical name or the order rows are drawn or numbered in: moving or
        inserting a block or switch elsewhere changes no other device's virtual name (owner, 2026-11-17)."""
        from hartlib import level_masts
        have = rows()
        blocks = [x["user_name"] for x in have if x["layer"] == "block"]
        occ = {x["user_name"]: x["jmri_name"] for x in have if x["layer"] == "occupancy"}
        self.assertEqual(occ, {BD.occupancy_user(b): BD.block_sensor(b) for b in blocks})     # one per block
        heads = {x["system_name"]: x["jmri_name"] for x in have if x["layer"] == "head"}
        for x in have:
            with self.subTest(row=x["user_name"]):
                if x["layer"] == "turnout":
                    self.assertEqual(x["jmri_name"], "IT:HART:C3:" + x["user_name"].rpartition(" ")[2])
                elif x["layer"] == "head":
                    self.assertEqual(x["jmri_name"], level_masts.head_name(x["user_name"]))
                elif x["layer"] == "mast":
                    self.assertTrue(level_masts.is_level_mast(x["jmri_name"]))
                    self.assertEqual(level_masts.mast_heads(x["jmri_name"]),
                                     [heads[h] for h in level_masts.mast_heads(x["system_name"])])
                elif x["layer"] in ("fb", "block"):
                    self.assertEqual(x["jmri_name"], "")
                if x["layer"] != "fb" and x["layer"] != "block":
                    self.assertTrue(x["jmri_name"])
        self.assertEqual(len(set(occ.values())), len(occ))

    def test_virtual_names(self):
        self.assertEqual([BD.block_sensor(b) for b in ("Track 107-109", "Track 107 Loop 2", "OS Switch 225b",
                                                       "Track 135-H1", "Track 101 Spur 1")],
                         ["IS:HART:C3:B:107-109", "IS:HART:C3:B:107_Loop_2", "IS:HART:C3:B:OS225b",
                          "IS:HART:C3:B:135-H1", "IS:HART:C3:B:101_Spur_1"])
        self.assertEqual([BD.occupancy_user(b) for b in ("Track 107 Loop 2", "OS Switch 225b")],
                         ["BS 107 Loop 2", "BS Switch 225b"])
        for bad in ("Track 1/2", "Track ", "Yard"):
            with self.assertRaises(BD.MapError):
                BD.block_sensor(bad)

    def test_check_virtual_stops_on_a_block_without_occupancy_or_a_name_twice(self):
        row = lambda layer, user, jmri="": dict(level=2, layer=layer, user_name=user, jmri_name=jmri)
        ok = [row("block", "Track 1-3"), row("occupancy", "BS 1-3", "IS:HART:C3:B:1-3")]
        BD.check_virtual(ok)
        with self.assertRaisesRegex(BD.MapError, "blocks and occupancy rows differ"):
            BD.check_virtual(ok + [row("block", "Track 3-5")])
        with self.assertRaisesRegex(BD.MapError, "given twice"):
            BD.check_virtual(ok + [row("block", "Track 3-5"), row("occupancy", "BS 3-5", "IS:HART:C3:B:1-3")])

    def test_corner_blocks_need_one_corner_per_leg(self):
        self.assertEqual(BD.xover_corners("7", {"A": "C", "B": "D", "C": "A", "D": "B"}),
                         {"A": "OS Switch 7c", "B": "OS Switch 7d", "C": "OS Switch 7a", "D": "OS Switch 7b"})
        with self.assertRaisesRegex(BD.MapError, "not one corner per leg"):
            BD.xover_corners("7", {"A": "A", "B": "A", "C": "C", "D": "D"})

    def test_helix_top_crossover_tracks_are_not_loops(self):
        names = {x["user_name"] for x in rows() if x["layer"] == "block"}
        self.assertFalse({"Track 129 Loop", "Track 135 Loop"} & names)

    def test_overrides_match_the_control_point_file(self):
        over = json.loads(BD.OVERRIDES.read_text())
        names = [c.cp_name for c in BD.load_cps()]
        self.assertEqual(list(over["control_points"]), names)
        self.assertEqual({k: v["switches"] for k, v in over["stations"].items()},
                         {k: v["switches"] for k, v in over["control_points"].items()})
        self.assertTrue(all(v["tracks"] == [] for v in over["stations"].values()))


if __name__ == "__main__":
    unittest.main()

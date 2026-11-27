"""build_device_map.py: placeholder control points and LCOS device names for the main and upper levels."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_device_map", ROOT / "tools/schematic/build_device_map.py")
BD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BD)
R = BD.railroad


def cp(name, level, *switches):
    """An in-memory main or upper interlocking, its control point (an interlockings.csv row)."""
    return R.Interlocking(0, level, name, switches, "West")


def rows():
    """The main and upper rows the builder wrote into the master (hartlib.devices.device_map_lines)."""
    return [r for _n, r in BD.devices.device_map_lines(("2", "3"), BD.OUT)]


class Pure(unittest.TestCase):
    def test_base_drops_half_letter_and_star(self):
        self.assertEqual([BD.base(x) for x in ("129A", "135B", "223*", "105")], ["129", "135", "223", "105"])

    def test_a_split_track_is_named_and_its_edge_found_at_build_time(self):
        """block_overrides.csv splits tracks by level and end switches, which survive a new export; the plan edge
        each is drawn on is looked up when the map is built."""
        found = [dict(t, level=3) for t in (track("Track 227-241", "241", "227", trial=["Track e63"]),
                                            track("Track 241 Spur", "241", trial=["Track e64"]),
                                            track("Track 1-2", "1", "2", trial=["Track e1", "Track e2"]))]
        head = ",".join(BD.mast_rule.OVERRIDE_COLUMNS) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "split.csv"
            for text, want in ((head + "3,split,227,241,,,,,,\n", {"e63": "Track 227-241"}),
                               (head + "3,split,9,10,,,,,,\n", "no track runs Switch 9 to Switch 10"),
                               (head + "3,split,1,2,,,,,,\n", "drawn on Track e1, Track e2"),
                               (head + "3,split,227,241,,,,,,\n3,split,227,241,,,,,,\n", "already split on line 2"),
                               (head + "2,split,227,241,,,,,,\n", "no track runs Switch 227 to Switch 241"),
                               ("edge,track\ne63,Track 227-241\n", "columns")):
                p.write_text(text, encoding="utf-8")
                with self.subTest(text=text):
                    if isinstance(want, dict):
                        self.assertEqual(BD.split_edges(p, found=found), want)
                    else:
                        with self.assertRaisesRegex(BD.MapError, want):
                            BD.split_edges(p, found=found)


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
            p.write_text("level,interlocking,switches,area,notes\n2,CP 1,\"1,3\",West,\n2,CP 3,3,West,\n")
            with self.assertRaisesRegex(BD.MapError, "switch 3 is in CP 1 and CP 3"):
                BD.load_cps(p)

    def test_every_switch_needs_a_control_point_or_a_local_row(self):
        bands = [("Main level", {"nodes": {"a": dict(kind="switch", label="101A"), "b": dict(kind="switch", label="105")},
                                 "strands": {}, "R": {"srow": {}}, "rail": {}}, {})]
        cps = [cp("CP 105", 2, "105")]
        over = {"edits": [{"op": "relabel", "map": {}}]}
        with self.assertRaisesRegex(BD.MapError, "switch 101 is in no control point"):
            BD.build(bands, {}, lambda b: [], BD.MapInputs(over, cps, []))
        with self.assertRaisesRegex(BD.MapError, "switch 105 is in a control point and in"):
            BD.build(bands, {}, lambda b: [], BD.MapInputs(over, cps, [], [R.LocalSwitch(0, "105", 2, "West")]))

    def test_track_names(self):
        sw, hx, bump = (lambda n: ("sw", n)), (lambda h: ("helix", h)), ("bumper", None)
        # parallel tracks are numbered by their ends' plan legs (mast_rule.plan_order), not by the drawn row
        found = [dict(ends=(sw("101"), sw("105")), row=1, plan_ends=("101C", "105A"), trial=["Track e2"]),
                 dict(ends=(sw("105"), sw("101")), row=2, plan_ends=("105B", "101B"), trial=["Track e1"]),
                 dict(ends=(sw("113"), bump), row=0, trial=["Track e3"]),
                 dict(ends=(sw("107"), sw("107")), row=0, trial=["Track e4"]),
                 dict(ends=(sw("135"), hx("H1")), row=0, trial=["Track e5"])]
        BD.track_names(found)
        self.assertEqual([t["name"] for t in found],
                         ["Track 101-105 2", "Track 101-105 1", "Track 113 Spur", "Track 107 Loop", "Track 135-H1"])

    def test_a_staging_part_keeps_its_bean_names_and_a_new_one_takes_the_next_free(self):
        """A part of a level whose beans the generator writes (staging) is a JMRI block of its own (owner,
        2026-11-20): its block and layout block names stay as its row has them, and a new part takes the next number
        free for both (IB:AUTO:<n>, ILB<n>), in name order, so no name shifts."""
        taken = {"IB:AUTO:0051", "ILB51", "ILB53", "IB:AUTO:0054"}
        got = BD.part_bean_names(["Track 9-11", "Track 1-3 at 1", "Track 11-13"],
                                 {"Track 11-13": ("IB:AUTO:0060", "ILB60")}, taken)
        self.assertEqual(got, {"Track 1-3 at 1": ("IB:AUTO:0052", "ILB52"), "Track 9-11": ("IB:AUTO:0055", "ILB55"),
                               "Track 11-13": ("IB:AUTO:0060", "ILB60")})
        with self.assertRaisesRegex(BD.MapError, "Track 9-11: its row has jmri_name IB:AUTO:0051, which another "
                                                 "bean has"):
            BD.part_bean_names(["Track 9-11"], {"Track 9-11": ("IB:AUTO:0051", "ILB70")}, taken)
        with self.assertRaisesRegex(BD.MapError, "Track 9-11: its row has a jmri_name or a layout_block, not both"):
            BD.part_bean_names(["Track 9-11"], {"Track 9-11": ("IB:AUTO:0070", "")}, taken)

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
        local = [row.switch for row in R.read_local_switches(BD.SWITCHES)]
        dx = {"225"}                            # the double crossover: an OS block and a detector per corner
        for s in cp_sw + local:
            os = [f"{s}{c}" for c in "abcd"] if s in dx else [s]
            kinds = sorted(x["layer"] for x in have if x["user_name"] in
                           [f"Switch {s}", f"DCC Switch {s}", f"FB Switch {s} N", f"FB Switch {s} R"]
                           + [f"OS Switch {o}" for o in os] + [f"BS Switch {o}" for o in os])
            want = sorted(["block"] * len(os) + ["fb", "fb"] + ["occupancy"] * len(os) + ["turnout", "turnout"])
            self.assertEqual(kinds, want, s)

    def test_no_block_is_a_stop_while_the_stations_are_parked(self):
        """The Dispatcher stations are parked with the stations topic: the helix rows marked a
        stop at Switch 131A and 131B until then (docs/parked/UNPARK.md)."""
        self.assertEqual([x["user_name"] for x in rows() if x["layer"] == "block" and x["stop"]], [])
        self.assertTrue(all(x["stop"] in ("", "yes") for x in rows()))

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
        from hartlib import level_masts
        for x in rows():
            if x["layer"] == "mast" and level_masts.is_level_virtual(x["jmri_name"]):
                # a destination at a buffer stop: named from its track's switch, lettered after the visible masts
                m = re.fullmatch(r"Mast (\d+)([LR])([A-D]?)", x["user_name"])
                self.assertIsNotNone(m, x["user_name"])
                self.assertEqual(int(m.group(1)) % 2, 0)
                self.assertTrue(x["comment"].endswith(" | buffer stop"), x["user_name"])
            elif x["layer"] == "mast" and not x["comment"].endswith(" | intermediate"):
                m = re.fullmatch(r"Mast (\d+)([LR])([AB]?)", x["user_name"])
                self.assertIsNotNone(m, x["user_name"])
                self.assertEqual(int(m.group(1)) % 2, 0)
                self.assertEqual(x["comment"].split(" | Switch ")[1], str(int(m.group(1)) - 1))

    def test_boards_follow_the_wiring_rules(self):
        """The rule's boards: turnouts on the 12V boards, heads after them on three pins in a row, never on a detector
        node's calibration pin. A frozen device (wiring.csv) keeps its own pins, which may span two boards: only
        the board limit and the calibration pin hold for it."""
        import re
        have = rows()
        frozen = {w.device for w in BD.frozen_wires()}
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
                groups = [(int(b), [int(p) for p in ps.split(",")])
                          for b, ps in re.findall(r"OU: (\d+) Ports: ([\d,]+)", x["comment"])]
                if not groups:
                    continue
                boards.update(b for b, _ps in groups)
                if detectors:
                    self.assertNotIn((n12 + 1, 8), [(b, p) for b, ps in groups for p in ps], x["user_name"])
                if x["user_name"] in frozen:
                    continue
                [(board, pins)] = groups                                       # the rule's: one board
                if x["layer"] == "turnout":
                    self.assertLessEqual(board, n12, x["user_name"])
                if x["layer"] == "head":
                    self.assertGreater(board, n12, x["user_name"])          # 5V boards follow the 12V ones
                    self.assertEqual(pins, list(range(pins[0], pins[0] + 3)), x["user_name"])
            self.assertLessEqual(max(boards, default=0), BD.MAX_OU, node)

    def test_a_loop_back_into_its_control_point_has_home_signals(self):
        loop = {x["user_name"]: x["notes"] for x in rows() if x["layer"] == "mast" and " Loop" in x["notes"]
                and x["notes"].startswith("home signal")}
        self.assertEqual(loop, {"Mast 108LA": "home signal from Track 107 Loop 1",      # the balloon at CP 107
                                "Mast 108LB": "home signal from Track 107 Loop 2"})

    def test_the_balloon_loop_is_two_blocks_and_loop_1_keeps_its_detector(self):
        """Two masts facing one loop block into one OS block would be one mast to JMRI (LayoutBlockManager.
        getFacingBean returns one per block pair), so the loop is two blocks, parted halfway.
        Loop 1 keeps the loop's detector (node 33 block 6); Loop 2's is not on a node yet, so no node or input moved."""
        have = {(x["layer"], x["user_name"]): x for x in rows()}
        self.assertNotIn(("block", "Track 107 Loop"), have)
        for half, leg in ((1, "B"), (2, "C")):
            block = have[("block", f"Track 107 Loop {half}")]
            self.assertEqual(block["trial_name"], f"Track 107B-107C #{half}")      # piece 1 from leg B
            self.assertTrue(block["notes"].startswith(f"388.1 cm, half of the balloon loop from leg {leg}"))
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
        inserting a block or switch elsewhere changes no other device's virtual name."""
        from hartlib import level_masts
        have = rows()
        blocks = [x["user_name"] for x in have if x["layer"] == "block"]
        occ = {x["user_name"]: x["jmri_name"] for x in have if x["layer"] == "occupancy"}
        self.assertEqual(occ, {BD.occupancy_user(b): BD.block_sensor(b) for b in blocks})     # one per block
        heads = {x["system_name"]: x["jmri_name"] for x in have if x["layer"] == "head" and x["system_name"]}
        unwired = {x["jmri_name"]: x["notes"] for x in have if x["layer"] == "head" and not x["system_name"]}
        for x in have:
            with self.subTest(row=x["user_name"]):
                if x["layer"] == "turnout":
                    self.assertEqual(x["jmri_name"], "IT:HART:C3:" + x["user_name"].rpartition(" ")[2])
                elif x["layer"] == "head":
                    self.assertEqual(x["jmri_name"], level_masts.head_name(x["user_name"], int(x["level"])))
                elif x["layer"] == "mast" and level_masts.is_level_virtual(x["jmri_name"]):
                    self.assertEqual(x["system_name"], x["jmri_name"])        # a hidden virtual mast, no heads
                elif x["layer"] == "mast":
                    self.assertTrue(level_masts.is_level_mast(x["jmri_name"]))
                    if x["system_name"]:
                        self.assertEqual(level_masts.mast_heads(x["jmri_name"]),
                                         [heads[h] for h in level_masts.mast_heads(x["system_name"])])
                    else:                       # heads not placed on a board yet: virtual heads only
                        self.assertTrue(level_masts.mast_heads(x["jmri_name"]))
                        for h in level_masts.mast_heads(x["jmri_name"]):
                            self.assertEqual(unwired.get(h), BD.HEAD_NOT_WIRED, h)
                elif x["layer"] == "fb" or (x["layer"] == "block" and x["role"] == "helix"):
                    self.assertEqual(x["jmri_name"], "")        # DIRECT feedback; a helix block's beans are staging's
                elif x["layer"] == "block":
                    # a block's: today's number, block_numbering.csv's (owner, 2026-11-23; naming-layers step 8,
                    # hartlib.block_numbering, whose tests pin the order and the layout block beside it)
                    self.assertRegex(x["jmri_name"], r"^IB:C3:\d{4}$")
                if x["layer"] != "fb" and x["layer"] != "block":
                    self.assertTrue(x["jmri_name"])
        self.assertEqual(len(set(occ.values())), len(occ))

    def test_apb_intermediates_are_named_from_the_milepost(self):
        """A pair at the turnback of the 107 balloon loop (line A) and of the split Track 227-241 (line B), named from
        the sheets' milepost count: odd westbound, even eastbound, one head each."""
        got = {x["user_name"]: (x["cp"], x["notes"]) for x in rows()
               if x["layer"] == "mast" and x["comment"].endswith(" | intermediate")}
        self.assertEqual(got, {
            "Mast A83": ("CP 107", "intermediate signal from Track 107 Loop 2 into Track 107 Loop 1 at MP A 8.39"),
            "Mast A84": ("CP 107", "intermediate signal from Track 107 Loop 1 into Track 107 Loop 2 at MP A 8.39"),
            "Mast B92": ("CP 225", "intermediate signal from Track 227-241 2 into Track 227-241 1 at MP B 9.27"),
            "Mast B93": ("CP 225", "intermediate signal from Track 227-241 1 into Track 227-241 2 at MP B 9.27")})
        self.assertEqual({x["user_name"]: x["dir"] for x in rows()
                          if x["layer"] == "mast" and x["comment"].endswith(" | intermediate")},
                         {"Mast A83": "west", "Mast A84": "east", "Mast B92": "east", "Mast B93": "west"})
        for name in got:
            self.assertTrue(next(x for x in rows() if x["user_name"] == name)["jmri_name"]
                            .startswith("IF$shsm:basic:one-searchlight("), name)
        self.assertEqual([BD.mast_plan.signal_number(8.49, w, "A") for w in (True, False)], [85, 84])
        self.assertEqual([BD.mast_plan.signal_number(9.19, w, "B") for w in (True, False)], [91, 92])
        self.assertEqual([BD.mast_plan.signal_number(9.2, w, "B") for w in (True, False)], [93, 92])

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
        row = lambda layer, user, jmri="": dict(level=2, layer=layer, user_name=user, jmri_name=jmri, role="track")
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

    def test_a_line_blocks_role_comes_from_its_ends_never_its_name(self):
        """build() states each row's role (hand-off row 8): a line block's from its track's ends and loop flag, so a
        name that reads like another kind gives no role."""
        t = lambda name, *ends, loop=False: dict(name=name, ends=list(ends), loop=loop)    # noqa: E731
        self.assertEqual(BD.line_role(t("Track 1-3", ("sw", "1"), ("sw", "3")), None), "track")
        self.assertEqual(BD.line_role(t("Track 1-3", ("sw", "1"), ("sw", "3")), 2), "track")       # a split half
        self.assertEqual(BD.line_role(t("Track Helix", ("bumper", None), ("sw", "1")), None), "spur")
        self.assertEqual(BD.line_role(t("Track 1 Spur", ("sw", "1"), ("helix", "H")), None), "helix")
        self.assertEqual(BD.line_role(t("Track 1-1", ("sw", "1"), ("sw", "1"), loop=True), 1), "loop_half")
        with self.assertRaisesRegex(BD.MapError, "a balloon loop is two blocks"):
            BD.line_role(t("Track 1 Loop", ("sw", "1"), ("sw", "1"), loop=True), None)
        for ends, said in ((((("bumper", None), ("bumper", None))), "bumper and bumper"),
                           ((("sw", "1"),), "sw"), ((("sw", "1"), ("link", "x")), "link and sw"), ((), "nothing")):
            with self.subTest(ends=ends), self.assertRaisesRegex(BD.MapError, f"Track X: a line block ends at {said};"):
                BD.line_role(t("Track X", *ends), None)

    def test_helix_top_crossover_tracks_are_not_loops(self):
        names = {x["user_name"] for x in rows() if x["layer"] == "block"}
        self.assertFalse({"Track 129 Loop", "Track 135 Loop"} & names)

    def test_generated_keys_match_the_control_point_file(self):
        over = BD.layer_files.read("plan_generated", "main_upper", BD.OVERRIDES.parent)
        names = [c.name for c in BD.load_cps()]
        self.assertEqual(list(over["control_points"]), names)
        self.assertEqual({k: v["switches"] for k, v in over["stations"].items()},
                         {k: v["switches"] for k, v in over["control_points"].items()})
        self.assertTrue(all(v["tracks"] == [] for v in over["stations"].values()))


class FacingOnRoute(unittest.TestCase):
    """mast_rule.facing_on_route: the facing points a home mast's routes meet inside its control point."""

    @staticmethod
    def band(inner_cm=20.0):
        """Bumper X - (A) switch 1 (B) - (A) switch 3, with switch 1's C leg and switch 3's B and C legs to bumpers."""
        nodes = {k: dict(kind="bumper", ins={}, outs={}) for k in "XWYZ"}
        nodes["S1"] = dict(kind="switch", label="1", ins={}, outs={})
        nodes["S3"] = dict(kind="switch", label="3", ins={}, outs={})
        strands = {}
        for sid, (a, pa), (b, pb), cm in (("e0", ("X", "A"), ("S1", "A"), 200.0), ("e1", ("S1", "B"), ("S3", "A"), inner_cm),
                                          ("e2", ("S1", "C"), ("W", "A"), 200.0), ("e3", ("S3", "B"), ("Y", "A"), 200.0),
                                          ("e4", ("S3", "C"), ("Z", "A"), 200.0)):
            strands[sid] = dict(src=(a, pa), dst=(b, pb), cm=cm)
            nodes[a]["outs"][pa] = sid
            nodes[b]["ins"][pb] = sid
        return dict(nodes=nodes, strands=strands)

    def test_routes_through_the_interlocking(self):
        import mast_rule as mr                  # on sys.path once build_device_map is loaded
        one_cp = {"1": "CP 1", "3": "CP 1"}
        self.assertEqual(mr.facing_on_route(self.band(), "S1", "A", one_cp), ["1", "3"])
        self.assertEqual(mr.facing_on_route(self.band(), "S3", "B", one_cp), [])           # trailing all the way
        self.assertEqual(mr.facing_on_route(self.band(), "S1", "A", {"1": "CP 1", "3": "CP 3"}), ["1"])
        self.assertEqual(mr.facing_on_route(self.band(mr.LONG_CM + 1), "S1", "A", one_cp), ["1"])  # own signals

    def test_a_double_crossover_is_facing_from_any_leg(self):
        import mast_rule as mr
        b = self.band()
        b["nodes"]["S3"]["kind"] = "dx"         # a route into it from its B leg still has a choice
        self.assertEqual(mr.facing_on_route(b, "S3", "B", {"3": "CP 3"}), ["3"])


class ReachesSignal(unittest.TestCase):
    """mast_rule.reaches_signal: a home mast is placed only when a route it governs reaches another signal (owner,
    2026-11-19), as Mast 126L into Switch 129's dark spurs is not."""

    band = staticmethod(FacingOnRoute.band)      # X - (A) 1 (B) - (A) 3, 1's C and 3's B and C to bumpers

    @staticmethod
    def reaches(b, node, leg, posts, joined=None, bands=None):
        import mast_rule as mr
        return mr.reaches_signal(bands or [("Main level", b, {})], 0, node, leg, {0: set(posts)}, joined or {})

    def test_a_mast_into_dark_spurs_is_not_kept(self):
        # entering 1 at A: on to 3 and its two spurs, or 1's own spur; no mast faces on anywhere
        self.assertFalse(self.reaches(self.band(), "S1", "A", {("S1", "A")}))

    def test_a_mast_with_a_signal_beyond_it_is_kept(self):
        b = self.band()
        # a mast on 3's B leg faces a train coming back from it, not one going out: still dark that way
        self.assertFalse(self.reaches(b, "S1", "A", {("S1", "A"), ("S3", "B")}))
        # a train from bumper Y entering 3 at B trails to 1 at B, where a mast stands: a signal beyond
        self.assertTrue(self.reaches(b, "S3", "B", {("S3", "B"), ("S1", "B")}))

    def test_ends_that_run_on_reach_a_signal_and_bumpers_do_not(self):
        b = self.band()
        for sub, want in (("helix", True), ("open", True), ("bumper", False), ("link", False)):
            with self.subTest(end=sub):
                b["nodes"]["Z"].update(kind="end", sub=sub)
                self.assertEqual(self.reaches(b, "S1", "A", {("S1", "A")}), want)

    def test_a_joined_connector_is_followed_to_the_other_band(self):
        # Z on band 0 is a connector joined to band 1's connector L, whose track runs to band 1's switch 5 at A
        b = self.band()
        b["nodes"]["Z"].update(kind="end", sub="link")
        other = dict(nodes={"L": dict(kind="end", sub="link", ins={}, outs={"E": "f0"}),
                            "S5": dict(kind="switch", label="5", ins={"A": "f0"}, outs={})},
                     strands={"f0": dict(src=("L", "E"), dst=("S5", "A"), cm=50.0)})
        bands = [("Main level", b, {}), ("Upper level", other, {})]
        import mast_rule as mr
        joined = {(0, "Z"): (1, "L"), (1, "L"): (0, "Z")}
        self.assertTrue(mr.reaches_signal(bands, 0, "S1", "A", {0: {("S1", "A")}, 1: {("S5", "A")}}, joined))
        self.assertFalse(mr.reaches_signal(bands, 0, "S1", "A", {0: {("S1", "A")}, 1: set()}, joined))

    def test_a_turnback_is_followed(self):
        b = self.band()
        # 1's C leg runs to a turnback and on round to 3's C leg, entered there with a mast facing on
        b["nodes"]["T"] = dict(kind="turnL", ins={0: "e2"}, outs={1: "e4"})
        b["strands"]["e2"] = dict(src=("S1", "C"), dst=("T", 0), cm=100.0)
        b["strands"]["e4"] = dict(src=("T", 1), dst=("S3", "C"), cm=100.0)
        b["nodes"]["S1"]["outs"]["C"], b["nodes"]["S3"]["outs"]["C"] = "e2", "e4"
        self.assertTrue(self.reaches(b, "S1", "A", {("S1", "A"), ("S3", "C")}))


class MastsLeaveOutDarkMasts(unittest.TestCase):
    """mast_rule.masts leaves out every home mast no route of which reaches another signal, again and again until
    none is left out, and never counts a mast as its own signal beyond (code review, 2026-11-19)."""

    @staticmethod
    def build(tracks, ends=None):
        """A main band from `tracks` [(id, (node, port), (node, port), cm)], every switch in CP 1 but 3 (CP 3) and 7
        (local); `ends` {node: sub} for the track ends (bumper by default)."""
        nodes = {}
        for sid, (a, pa), (b, pb), _cm in tracks:
            for n in (a, b):
                if n not in nodes:
                    if n.startswith("S"):
                        nodes[n] = dict(kind="switch", label=n[1:], ins={}, outs={})
                    else:
                        nodes[n] = dict(kind="end", sub=(ends or {}).get(n, "bumper"), ins={}, outs={})
            nodes[a]["outs"][pa] = sid
            nodes[b]["ins"][pb] = sid
        strands = {sid: dict(src=a, dst=b, cm=cm, main=False) for sid, a, b, cm in tracks}
        band = dict(nodes=nodes, strands=strands, rail={n: 1 for n in nodes if n.startswith("S")}, R=dict(srow={}))
        found = []
        for sid, (a, pa), (b, pb), cm in tracks:
            ref = lambda n: ("sw", n[1:]) if n.startswith("S") else ("bumper", None)       # noqa: E731
            found.append(dict(level=2, ends=(ref(a), ref(b)), legs=[(a, pa), (b, pb)], band=0, cm=cm, loop=False,
                              main=False, row=0, strands=[sid], trial=[f"Track {sid}"], name=f"Track {sid}",
                              plan_ends=tuple(f"{n[1:]}{p}" if n.startswith("S") else "end" for n, p in ((a, pa), (b, pb)))))
        return [("Main level", band, {})], found

    def masts(self, tracks, cp_of, ends=None):
        import mast_rule as mr
        bands, found = self.build(tracks, ends)
        return sorted((m["node"], m["leg"]) for m in mr.masts(bands, None, found, cp_of, joined={}, levels={"Main level": 2}))

    def test_two_masts_in_a_row_into_dark_track_both_go(self):
        # X (200 cm) - 1 - (200 cm) - 3, 1's C and 3's B and C short spurs to bumpers: 1's mast at A sees 3's mast
        # at A beyond it, but 3's routes end at bumpers, so 3's goes, and then 1's has nothing beyond it either
        tracks = [("e0", ("X", "E"), ("S1", "A"), 200.0), ("e1", ("S1", "B"), ("S3", "A"), 200.0),
                  ("e2", ("S1", "C"), ("W", "E"), 20.0), ("e3", ("S3", "B"), ("Y", "E"), 20.0),
                  ("e4", ("S3", "C"), ("Z", "E"), 20.0)]
        self.assertEqual(self.masts(tracks, {"1": "CP 1", "3": "CP 3"}), [])
        # with X a helix end, 1's mast at B (a train from 3 heading for X) runs on to another level and stays
        self.assertEqual(self.masts(tracks, {"1": "CP 1", "3": "CP 3"}, {"X": "helix"}), [("S1", "B")])

    def test_a_route_back_to_its_own_mast_is_no_signal_beyond(self):
        # 1 (CP 1) and local 7 joined twice, 1's A to 7's B and 1's B to 7's A: a reversing loop through 7 that
        # brings a train back to the mast it started at; 1's C and 7's C are dark spurs, so both of 1's masts go
        tracks = [("e0", ("S1", "A"), ("S7", "B"), 200.0), ("e1", ("S1", "B"), ("S7", "A"), 200.0),
                  ("e2", ("S1", "C"), ("Z", "E"), 20.0), ("e3", ("S7", "C"), ("W", "E"), 20.0)]
        self.assertEqual(self.masts(tracks, {"1": "CP 1"}), [])


class NoBoardRoomOnly(unittest.TestCase):
    """Only the draft plant's lack of board room leaves a mast's heads unplaced; any other plant error stops."""

    def test_no_board_room_is_its_own_error(self):
        self.assertTrue(issubclass(BD.NoBoardRoom, BD.MapError))
        nodes = BD.Nodes([])
        with self.assertRaises(BD.NoBoardRoom):
            nodes.pick_mast(2, "Nowhere", 1)

    def test_a_one_head_mast_takes_free_pins_on_any_board(self):
        # first fit over every 5V board, not only the last (owner, 2026-11-19: no head left out while room exists)
        nodes = BD.Nodes([R.LcosNode(0, 2, "North", 52)])
        place = lambda heads: [(board, pin) for _k, _p, board, pin in nodes.place_mast(  # noqa: E731
            nodes.pick_mast(2, "North", heads), heads)]
        self.assertEqual(place(1), [(1, 1)])
        self.assertEqual(place(2), [(2, 1), (2, 4)])            # six pins: not after the one head on board 1
        self.assertEqual(place(1), [(1, 4)])                    # back on board 1, not a third board
        self.assertEqual(place(2), [(3, 1), (3, 4)])
        self.assertEqual(place(2), [(4, 1), (4, 4)])
        with self.assertRaises(BD.NoBoardRoom):                 # four boards, two heads each: really full
            nodes.pick_mast(2, "North", 1)

    def test_the_committed_map_places_two_head_masts_before_one_head_ones(self):
        # North holds 12 heads (node 42: two 5V boards, node 52: four) for 16 (eight two-head masts since the rule
        # left out 126L): every board takes a two-head mast, so 128LB has outputs and 132RA and 132RB wait
        heads = {r["user_name"]: r for r in rows() if r["layer"] == "head"}
        self.assertNotIn("Head 126L", heads)                    # no route past it reaches a signal (reaches_signal)
        self.assertEqual(heads["Head 132RA Top"]["notes"], BD.HEAD_NOT_WIRED)
        self.assertTrue(heads["Head 128LB Top"]["system_name"] and heads["Head 128LB Bottom"]["system_name"])
        north = [r for r in heads.values() if r["node"] in ("42", "52")]
        self.assertEqual(len(north), 12)


def track(name, a, b=None, row=0, trial=None, loop=False, legs=("B", "A")):
    """An in-memory track entry as mast_rule.tracks gives them: between switches a and b, or a spur when b is None;
    `legs` the legs it leaves a and b by (its plan_ends, which order parallel tracks)."""
    return dict(name=name, ends=(("sw", a), ("sw", b) if b else ("bumper", None)), row=row,
                plan_ends=(a + legs[0], b + legs[1] if b else "end"), trial=trial or [f"Track e{row}"], loop=loop)


class SwitchPairLists(unittest.TestCase):
    """Hand lists (block_overrides.csv) name a track by its end switches, so a renumber does not break them (source
    data row 5). The rows below are level 2 rows; the tracks are level 2 tracks."""
    HEAD = ",".join(BD.mast_rule.OVERRIDE_COLUMNS) + "\n"

    def names(self, text, found):
        """read_block_splits over block_overrides.csv split rows of level 2, one per line of `text` (switch_a,
        switch_b, parallel, notes)."""
        text = "".join("2,split," + line.rsplit(",", 1)[0] + ",,,,," + line.rsplit(",", 1)[1] + "\n"
                       for line in text.splitlines())
        found = [dict(t, level=2) for t in found]
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "list.csv"
            p.write_text(self.HEAD + text, encoding="utf-8")
            return BD.mast_rule.read_block_splits(p, found, BD.LEVELS)

    def test_a_pair_names_its_track_whichever_way_the_ends_are_stored(self):
        found = [track("Track 119-121", "121", "119"), track("Track 121-123", "121", "123", row=1)]
        self.assertEqual(self.names("119,121,,\n", found), {"Track 119-121"})

    def test_a_spur_has_no_second_switch(self):
        found = [track("Track 241 Spur", "241"), track("Track 227-241", "241", "227", row=1)]
        self.assertEqual(self.names("241,,,\n", found), {"Track 241 Spur"})

    def test_two_tracks_between_one_pair_need_parallel(self):
        found = [track("Track 211-217 2", "211", "217", row=5, legs=("C", "A")),
                 track("Track 211-217 1", "211", "217", row=6, legs=("B", "B"))]
        with self.assertRaisesRegex(BD.MapError, r"list.csv: line 2: level 2: 2 tracks run Switch 211 to Switch 217 "
                                                  r"\(Track 211-217 1, Track 211-217 2\): give parallel"):
            self.names("211,217,,\n", found)
        self.assertEqual(self.names("211,217,2,\n", found), {"Track 211-217 2"})
        with self.assertRaisesRegex(BD.MapError, "parallel 3 of Switch 211 to Switch 217, but 2 tracks"):
            self.names("211,217,3,\n", found)

    def test_a_pair_with_no_track_names_the_tracks_at_its_switches(self):
        found = [track("Track 119-121", "119", "121")]
        with self.assertRaisesRegex(BD.MapError, r"line 3: level 2: no track runs Switch 119 to Switch 123 \(tracks at those "
                                                  r"switches: Track 119-121\)"):
            self.names("119,121,,\n119,123,,\n", found)

    def test_one_track_named_twice_and_bad_rows_stop(self):
        found = [track("Track 119-121", "119", "121")]
        for text, msg in (("119,121,,\n119,121,,\n", "already split on line 2"),
                          ("121,119,,\n", "lower first"),
                          ("x,121,,\n", "are switch numbers"),
                          ("119,121,5,\n", "parallel '5'")):
            with self.subTest(text=text), self.assertRaisesRegex(BD.MapError, msg):
                self.names(text, found)

    def test_a_renumber_leaves_the_row_resolving(self):
        """The same hand row follows its track when the generated name changes with a switch renumber, which the old
        name-keyed rows did not ("was Track 123-125")."""
        before = [track("Track 121-123", "121", "123", row=2)]
        after = [track("Track 125-127", "125", "127", row=2)]
        self.assertEqual(self.names("121,123,,\n", before), {"Track 121-123"})
        with self.assertRaisesRegex(BD.MapError, "no track runs Switch 121 to Switch 123"):
            self.names("121,123,,\n", after)               # the row is retyped with the switches, not a name
        self.assertEqual(self.names("125,127,,\n", after), {"Track 125-127"})

    def test_a_loop_is_keyed_by_its_one_switch_twice(self):
        found = [track("Track 107 Loop", "107", "107", loop=True)]
        self.assertEqual(self.names("107,107,,\n", found), {"Track 107 Loop"})

    def test_the_committed_splits_resolve_in_the_plan(self):
        found = BD.named_tracks()
        self.assertEqual(BD.split_tracks(found=found), {"Track 227-241"})


if __name__ == "__main__":
    unittest.main()

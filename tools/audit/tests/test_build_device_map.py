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


def rows():
    with BD.OUT.open(newline="") as f:
        return list(csv.DictReader(f))


class Pure(unittest.TestCase):
    def test_base_drops_half_letter_and_star(self):
        self.assertEqual([BD.base(x) for x in ("129A", "135B", "223*", "105")], ["129", "135", "223", "105"])

    def test_control_point_lists_only_its_own_band_halves(self):
        cps = [dict(cp_name="CP 129", level=2, switches=["129", "135"]),
               dict(cp_name="CP 223", level=3, switches=["223"])]
        by_level = {2: {"129A", "135A", "105"}, 3: {"129B", "135B", "223*"}}
        got = BD.overrides_keys(cps, by_level)
        self.assertEqual(got["CP 129"]["switches"], ["129A", "135A"])
        self.assertEqual(got["CP 223"]["switches"], ["223*"])          # the moved switch keeps its star

    def test_switch_missing_from_its_band_fails(self):
        with self.assertRaises(BD.MapError):
            BD.overrides_keys([dict(cp_name="CP 9", level=2, switches=["9"])], {2: {"105"}})

    def test_switch_in_two_control_points_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "cps.csv"
            p.write_text("cp_id,cp_name,level,switches,area,notes\na,CP 1,2,\"1,3\",West,\nb,CP 3,2,3,West,\n")
            with self.assertRaisesRegex(BD.MapError, "switch 3 is in CP 1 and CP 3"):
                BD.load_cps(p)

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
        nodes = BD.Nodes([dict(level="2", area="West", node="33"), dict(level="2", area="West", node="43")])
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
        r = rows()
        cps = BD.load_cps()
        for cp in cps:
            for s in cp["switches"]:
                kinds = sorted(x["layer"] for x in r if x["user_name"] in
                               (f"Switch {s}", f"FB Switch {s} N", f"FB Switch {s} R", f"OS Switch {s}",
                                f"BS Switch {s}"))
                self.assertEqual(kinds, ["block", "fb", "fb", "occupancy", "turnout"], s)

    def test_system_names_unique_and_in_lcos_bands(self):
        seen = set()
        for x in rows():
            if not x["system_name"] or x["layer"] == "mast":
                continue
            self.assertNotIn(x["system_name"], seen)
            seen.add(x["system_name"])
            uid = int(x["system_name"][3:] if x["layer"] != "head" else x["system_name"][2:]) % 100
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

    def test_overrides_match_the_control_point_file(self):
        over = json.loads(BD.OVERRIDES.read_text())
        names = [cp["cp_name"] for cp in BD.load_cps()]
        self.assertEqual(list(over["control_points"]), names)
        self.assertNotIn("stations", over)


if __name__ == "__main__":
    unittest.main()

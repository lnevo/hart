"""device_map_staging.py and device_map_staging_switches.py: the bean numbering of staging's parts, the helix ends, the
switch rows' steps over fake wiring rows, and the one-row-per-device check every built set of staging rows keeps.
None needs the schematic plugin."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import device_map_staging as staging  # noqa: E402
import device_map_staging_switches as switches  # noqa: E402
from hartlib import devices  # noqa: E402
from map_error import MapError  # noqa: E402


def wire(address: str, node: int = 4, text: str = "Node: 4 Turnout: 0") -> SimpleNamespace:
    """A wiring.csv row as the switch steps read it: its address, node and wiring text."""
    return SimpleNamespace(address=address, node=node, wiring_text=text, line=2)


def field(**cells: str) -> dict[str, str]:
    return dict({c: "" for c in devices.COLUMNS}, **cells)


class BeanNumbers(unittest.TestCase):
    """part_bean_names: the names a row has stand, a new part takes the next number free everywhere."""

    def test_a_named_part_keeps_its_names_and_a_new_one_takes_the_next_free_number(self):
        got = staging.part_bean_names(["P2", "P1"], {"P1": ("IB:AUTO:0052", "ILB52")}, {"IB:AUTO:0053", "ILB54"})
        self.assertEqual(got, {"P1": ("IB:AUTO:0052", "ILB52"), "P2": ("IB:AUTO:0055", "ILB55")})
        self.assertIsInstance(got["P2"], staging.Beans)
        self.assertEqual(got["P2"].layout_block, "ILB55")

    def test_numbers_are_given_in_name_order(self):
        got = staging.part_bean_names(["P10", "P9"], {}, set())
        self.assertEqual([got["P9"].jmri_name, got["P10"].jmri_name], ["IB:AUTO:0052", "IB:AUTO:0053"])

    def test_a_row_with_one_name_or_a_taken_name_stops(self):
        with self.assertRaisesRegex(MapError, "P1: its row has a jmri_name or a layout_block, not both"):
            staging.part_bean_names(["P1"], {"P1": ("IB:AUTO:0052", "")}, set())
        with self.assertRaisesRegex(MapError, "P1: its row has layout_block ILB52, which another bean has"):
            staging.part_bean_names(["P1"], {"P1": ("IB:AUTO:0052", "ILB52")}, {"ILB52"})


class TrackEnds(unittest.TestCase):

    def test_end_switches_are_the_switch_ends_in_number_order_once(self):
        track = {"ends": (("sw", "23"), ("sw", "7"))}
        self.assertEqual(staging.end_switches(track), ["7", "23"])
        self.assertEqual(staging.end_switches({"ends": (("sw", "5"), ("sw", "5"))}), ["5"])
        self.assertEqual(staging.end_switches({"ends": (("sw", "5"), ("bumper", None))}), ["5"])

    def test_a_switch_end_with_no_number_stops(self):
        with self.assertRaisesRegex(MapError, "a switch end with no number"):
            staging.end_switches({"ends": (("sw", None), ("sw", "5"))})

    def test_helix_ends_are_both_switch_numbers(self):
        helix = {"Helix Outer": {"block": "Track Helix Outer", "staging_switch": "39", "level_switch": "131A"}}
        self.assertEqual(staging.helix_ends(helix), {"Track Helix Outer": {"39", "131"}})

    def test_a_level_switch_with_no_number_stops(self):
        with self.assertRaisesRegex(MapError, "helix track Helix Inner: level_switch 'A1' is no switch number"):
            staging.helix_ends({"Helix Inner": {"block": "B", "staging_switch": "40", "level_switch": "A1"}})


class OneRowPerDevice(unittest.TestCase):

    def test_unique_rows_pass(self):
        switches.check_unique([{"layer": "fb", "id": "fb:1:N"}, {"layer": "fb", "id": "fb:1:R"}], "rows")

    def test_a_device_given_twice_or_a_row_with_no_id_stops(self):
        rows = [{"layer": "fb", "id": "fb:1:N"}, {"layer": "fb", "id": "fb:1:N"}, {"layer": "block", "id": ""}]
        with self.assertRaisesRegex(MapError, r"^rows: block \(no id\), fb fb:1:N given by no row or by more than "):
            switches.check_unique(rows, "rows")


class SwitchSteps(unittest.TestCase):
    """The steps of staging_wired_rows for one switch, over fake wiring rows and field rows."""

    def inputs(self, by=None, owner=None) -> switches._WiredInputs:
        return switches._WiredInputs(dict(by or {}), dict(owner or {}), {"5": "CP Yard"}, [])

    @staticmethod
    def wired(n: str = "5") -> dict:
        return {("turnout", f"switch:{n}"): wire("M2T400"), ("fb", f"fb:{n}:N"): wire("M2S410"),
                ("fb", f"fb:{n}:R"): wire("M2S411")}

    def test_a_device_with_no_wiring_row_is_named_by_the_owners_name(self):
        w = self.inputs({("turnout", "switch:5"): wire("M2T400")})
        got = switches._switch_wires(w, "5", "switch:5", {"N": "fb:5:N", "R": "fb:5:R"}, None,
                                     {"N": field(user_name="Yard lead N"), "R": None})
        self.assertIsNone(got)
        self.assertEqual(w.bad, ["staging fb Yard lead N: no fb row for fb:5:N in wiring.csv",
                                 "staging fb FB Switch 5 R: no fb row for fb:5:R in wiring.csv"])

    def test_a_wired_switch_gives_its_turnout_and_feedback_rows(self):
        w = self.inputs(self.wired())
        got = switches._switch_rows(w, "5", ["5"])
        self.assertEqual(w.bad, [])
        self.assertEqual([(r["layer"], r["id"], r["jmri_name"]) for r in got],
                         [("turnout", "switch:5", "M2T400"), ("fb", "fb:5:N", "M2S410"), ("fb", "fb:5:R", "M2S411")])
        self.assertEqual([r["cp"] for r in got[1:]], ["CP Yard", "CP Yard"])      # the feedback: its interlocking
        self.assertTrue(all(r["description"] and r["written_by"] == switches.WRITER for r in got))

    def test_the_owners_dcc_address_gives_an_alias_row(self):
        w = self.inputs(self.wired(), {("turnout", "switch:5"): field(dcc="23")})
        got = switches._switch_rows(w, "5", ["5"])
        alias = [r for r in got if r["id"] == "dcc:5"]
        self.assertEqual(len(alias), 1)
        self.assertEqual(alias[0]["notes"], "LCC alias of Switch 5 (M2T400)")
        self.assertEqual(w.owner, {})

    def test_an_alias_row_with_no_dcc_address_stops_the_switch(self):
        w = self.inputs(self.wired(), {("turnout", "dcc:5"): field(user_name="DCC Switch 5")})
        self.assertIsNone(switches._switch_rows(w, "5", ["5"]))
        self.assertEqual(len(w.bad), 1)
        self.assertIn("staging turnout DCC Switch 5 (id dcc:5): an LCC alias needs a DCC address", w.bad[0])

    def test_a_turnout_bound_by_an_old_user_name_stops_the_switch(self):
        w = self.inputs(self.wired(), {("turnout", "switch:5"): field(user_name="Yard lead", jmri_name="Switch 5")})
        self.assertIsNone(switches._switch_rows(w, "5", ["5"]))
        self.assertEqual(len(w.bad), 1)
        self.assertIn("staging turnout Yard lead (id switch:5): its jmri_name 'Switch 5' binds it by its old user "
                      "name", w.bad[0])

    def test_an_alias_note_needs_the_turnouts_address(self):
        with self.assertRaisesRegex(MapError, "LCC alias DCC Switch 5: Switch 5 has no turnout row in wiring.csv"):
            switches.alias_note("Switch 5", "")


class CommittedRows(unittest.TestCase):
    """staging_wired_rows over the committed files: one row per device, in layer then name order."""

    def test_the_committed_switch_rows_are_one_per_device(self):
        rows = staging.staging_wired_rows()
        switches.check_unique(rows, "staging's turnout and feedback rows")
        order = [(devices.LAYERS.index(r["layer"]), staging.natural(r["user_name"])) for r in rows]
        self.assertEqual(order, sorted(order))
        self.assertEqual({r["layer"] for r in rows}, {"turnout", "fb"})


class TheSplit(unittest.TestCase):

    def test_device_map_staging_re_exports_the_switch_rows(self):
        for name in ("STAGING_LEVEL", "WRITER", "alias_note", "check_unique", "field_row", "staging_cps",
                     "staging_field", "staging_switches", "staging_wired_rows"):
            with self.subTest(name=name):
                self.assertIs(getattr(staging, name), getattr(switches, name))

    def test_the_switch_module_does_not_load_the_builder_at_import(self):
        code = "import sys; import device_map_staging_switches; sys.exit('build_device_map' in sys.modules)"
        got = subprocess.run([sys.executable, "-c", code], cwd=HERE.parent, capture_output=True, text=True)
        self.assertEqual(got.returncode, 0, got.stderr)


if __name__ == "__main__":
    unittest.main()

"""Each main and upper bean's comment, in staging's form (owner, 2026-11-23, naming-layers step 11): a head's and a
mast's name its planned physical device, or nothing after the place when the draft plant has no board room for it
(ADR-024), never "planned ?". build_device_map.py writes the text into each row's bean_comment
(device_map_rows.bean_cells, naming-layers steps 9 and 11); hartlib.tables_build.master_beans puts it on the bean."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
import device_map_rows as DR  # noqa: E402
from hartlib import devices  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402

V = "IH:HART:C3:"


def master(**cells) -> dict:
    return {**dict.fromkeys(devices.COLUMNS, ""), "level": "3", "cp": "CP 107", **cells}


def rows(mast, heads, device):
    """A home mast's master row and its heads' (`heads`: the head keys after Head <mast>, its planned `device`)."""
    mid = f"mast:119:B:{mast}"
    out = [master(layer="mast", role="home", id=mid, user_name=f"Mast {mast}", switch="119", dir="west",
                  assignment="virtual", system_name=device,
                  jmri_name="IF$shsm:basic:two-searchlight" + "".join(f"({V}{h})" for h in heads))]
    out += [master(layer="head", role="head", id=f"{mid}:{'top' if i == 0 else 'bottom'}", user_name=f"Head {h}",
                   assignment="virtual", jmri_name=V + h) for i, h in enumerate(heads)]
    return out


def comments(made):
    return {r["user_name"]: r["bean_comment"] for r in DR.bean_cells(made)}


class Comments(unittest.TestCase):
    def test_a_planned_device_is_named_and_a_missing_one_is_not_on_a_node_yet(self):
        got = comments(rows("120RA", ["120RA_Top", "120RA_Bottom"], "IF$shsm:basic:two-searchlight(IH4338)(IH4339)")
                       + rows("120RB", ["120RB_Top", "120RB_Bottom"], ""))
        self.assertEqual(got["Head 120RA_Bottom"], "CP 107 | Switch 119 | internal, not wired | planned IH4339 (draft)")
        self.assertEqual(got["Mast 120RA"], "CP 107 | Switch 119 | West | planned "
                                            "IF$shsm:basic:two-searchlight(IH4338)(IH4339) (draft)")
        for name in ("Head 120RB_Top", "Head 120RB_Bottom"):
            self.assertEqual(got[name], "CP 107 | Switch 119 | internal, not wired | not on a node yet")
        # a mast names the way it faces after its place; its heads do not
        self.assertEqual(got["Mast 120RB"], "CP 107 | Switch 119 | West | not on a node yet")
        self.assertFalse([c for c in got.values() if "?" in c or c.endswith("planned ")])

    def test_the_place_is_the_rows_jmri_comment_when_it_has_one(self):
        """As on staging's masts: the row's jmri_comment ("Peninsula | buffer stop" for a hidden mast with no cp)."""
        made = rows("120RA", ["120RA_Top"], "")
        made[0]["jmri_comment"] = "Peninsula | Switch 119"
        got = comments(made)
        self.assertEqual(got["Mast 120RA"], "Peninsula | Switch 119 | West | not on a node yet")
        self.assertEqual(got["Head 120RA_Top"], "Peninsula | Switch 119 | internal, not wired | not on a node yet")

    def test_each_kind_in_stagings_form(self):
        """A turnout: its cp, its switch, the note and its planned turnout; a detector: the note and its planned
        detector or why there is none; a block: its detector first, then its place, a part the block it is part of."""
        made = [master(level="2", layer="turnout", role="turnout", id="switch:107", user_name="Switch 107",
                       assignment="virtual", system_name="M2T3308", jmri_name="IT:HART:C3:107"),
                master(level="2", layer="occupancy", role="os", id="det:os:107", user_name="BS Switch 107",
                       assignment="virtual", system_name="M2S3300", jmri_name="IS:HART:C3:B:OS107",
                       blocks="OS Switch 107"),
                master(level="2", layer="occupancy", role="os", id="det:os:101", user_name="BS Switch 101",
                       assignment="virtual", jmri_name="IS:HART:C3:B:OS101", blocks="OS Switch 101",
                       notes="no detector planned: dark until decided"),
                master(level="2", layer="block", role="os", id="os:107", user_name="OS Switch 107",
                       assignment="virtual", jmri_name="IB:C3:0004", jmri_comment="CP 107"),
                master(level="2", layer="block", role="part", id="block:105A-109B", user_name="Track 105-109",
                       assignment="virtual", jmri_name="IB:C3:0077", part_of="OS Switch 101")]
        got = comments(made)
        self.assertEqual(got["Switch 107"], "CP 107 | Switch 107 | internal, not wired | planned M2T3308 (draft)")
        self.assertEqual(got["BS Switch 107"], "internal, not wired | planned M2S3300 (draft)")
        self.assertEqual(got["BS Switch 101"], "internal, not wired | no detector planned: dark until decided")
        self.assertEqual(got["OS Switch 107"], "BS Switch 107 / IS:HART:C3:B:OS107; CP 107")
        self.assertEqual(got["Track 105-109"], "BS Switch 101 / IS:HART:C3:B:OS101; part of OS Switch 101")
        with self.assertRaisesRegex(DR.MapError, "OS Switch 107 .*no detector row names it"):
            DR.bean_cells(made[:1] + made[3:4])

    def test_a_head_with_no_mast_row_stops(self):
        with self.assertRaises(DR.MapError):
            DR.bean_cells(rows("120RA", ["120RA_Top"], "")[1:])

    def test_only_rows_the_build_makes_a_bean_for_get_cells(self):
        """A spare detector, a helix block (even one given a jmri_name), an LCC alias, a feedback row, a row with
        assignment none and a staging row get no cells (makes_bean); a main turnout and detector do."""
        made = [master(level="2", layer="turnout", role="turnout", id="switch:101", user_name="Switch 101",
                       assignment="virtual", jmri_name="IT:HART:C3:101"),
                master(level="2", layer="turnout", role="lcc_alias", id="dcc:101", user_name="DCC Switch 101",
                       assignment="virtual", jmri_name="IT:HART:C3:101"),
                master(level="2", layer="fb", role="fb", id="fb:101:N", user_name="FB Switch 101 N"),
                master(level="2", layer="occupancy", role="os", id="det:os:101", user_name="BS Switch 101",
                       assignment="virtual", jmri_name="IS:HART:C3:B:OS101", notes="no detector"),
                master(level="2", layer="occupancy", role="spare", id="spare:M2S1", user_name="Spare 1",
                       assignment="spare", system_name="M2S1", jmri_name="M2S1"),
                master(level="2", layer="block", role="helix", id="block:131A-helix", user_name="Track Helix Outer",
                       assignment="virtual", jmri_name="IB:C3:0999"),
                master(level="1", layer="turnout", role="turnout", id="switch:1", user_name="Switch 1",
                       assignment="field", jmri_name="Switch 1")]
        got = {r["user_name"]: (r["start"], bool(r["bean_comment"])) for r in DR.bean_cells(made)}
        self.assertEqual(got, {"Switch 101": ("closed", True), "DCC Switch 101": ("", False),
                               "FB Switch 101 N": ("", False), "BS Switch 101": ("inactive", True),
                               "Spare 1": ("", False), "Track Helix Outer": ("", False), "Switch 1": ("", False)})
        self.assertEqual(DR.bean_cells(made, frozenset({"101"}))[0]["start"], "thrown")

    def test_a_thrown_switch_with_no_turnout_row_stops(self):
        made = [master(level="2", layer="turnout", role="turnout", id="switch:101", user_name="Switch 101",
                       assignment="virtual", jmri_name="IT:HART:C3:101")]
        with self.assertRaisesRegex(DR.MapError, "switches 999 start Thrown"):
            DR.bean_cells(made, frozenset({"101", "999"}))

    def test_a_swapped_device_says_neither_unwired_nor_planned(self):
        """A row swapped to its physical device (assignment field, ADR-028) carries its wiring after its place, as
        staging's do, and no start; a mast whose planned name is its own is not "not on a node yet"."""
        turnout = master(level="2", layer="turnout", role="turnout", id="switch:107", user_name="Switch 107",
                         assignment="field", system_name="M2T3308", jmri_name="M2T3308",
                         wiring="Node: 33 Turnout: 0 | OU: 1 Ports: 1,2")
        made = rows("120RA", ["120RA_Top"], "IF$shsm:basic:one-searchlight(IH4338)")
        made[0].update(assignment="field", jmri_name="IF$shsm:basic:one-searchlight(IH4338)")
        made[1].update(assignment="field", jmri_name="IH4338", wiring="Node: 33 Signal: 0 | OU: 3 Ports: 1,2,3")
        cells = {r["user_name"]: (r["start"], r["bean_comment"]) for r in DR.bean_cells([turnout] + made)}
        self.assertEqual(cells["Switch 107"], ("", "CP 107 | Switch 107 | Node: 33 Turnout: 0 | OU: 1 Ports: 1,2"))
        self.assertEqual(cells["Mast 120RA"], ("", "CP 107 | Switch 119 | West"))
        self.assertEqual(cells["Head 120RA_Top"], ("", "CP 107 | Switch 119 | Node: 33 Signal: 0 | OU: 3 Ports: 1,2,3"))
        virtual = rows("120RB", ["120RB_Top"], "")
        virtual[0]["system_name"] = virtual[0]["jmri_name"]           # its planned name is its own
        self.assertEqual(comments(virtual)["Mast 120RB"], "CP 107 | Switch 119 | West")

    def test_master_beans_puts_each_rows_comment_on_its_bean(self):
        made = [dict(r, bean_comment=w) for r, w in zip(rows("120RA", ["120RA"], ""), ("mast words", "head words"))]
        beans = tb.master_beans(made, {}, ("3",))
        got = {e.findtext("userName"): e.findtext("comment") for els in beans.values() for e in els}
        self.assertEqual(got, {"Mast 120RA": "mast words", "Head 120RA": "head words"})


if __name__ == "__main__":
    unittest.main()

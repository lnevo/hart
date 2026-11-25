"""Each main and upper head's and mast's comment names its planned physical device, or says it is not on a node yet
when the draft plant has no board room for it (ADR-024), never "planned ?". build_device_map.py writes the text into
each row's bean_comment (device_map_rows.bean_cells, naming-layers step 9); le_tables.add_level_signals puts the
row's text on the bean."""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
import device_map_rows as DR  # noqa: E402
import le_tables as T  # noqa: E402
from hartlib import devices  # noqa: E402

V = "IH:HART:C3:"


def master(**cells) -> dict:
    return dict(dict.fromkeys(devices.COLUMNS, ""), level="3", cp="CP 107", **cells)


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
        self.assertEqual(got["Head 120RA_Bottom"], "CP 107 | Switch 119 | virtual (device map); planned IH4339")
        self.assertEqual(got["Mast 120RA"], "CP 107 | Switch 119 | West | virtual (device map); planned "
                                            "IF$shsm:basic:two-searchlight(IH4338)(IH4339)")
        for name in ("Head 120RB_Top", "Head 120RB_Bottom"):
            self.assertEqual(got[name], "CP 107 | Switch 119 | virtual (device map); not on a node yet")
        # a mast names the way it faces after its place; its heads do not (owner, 2026-11-22)
        self.assertEqual(got["Mast 120RB"], "CP 107 | Switch 119 | West | virtual (device map); not on a node yet")
        self.assertFalse([c for c in got.values() if "?" in c or c.endswith("planned ")])

    def test_a_head_with_no_mast_row_stops(self):
        with self.assertRaises(DR.MapError):
            DR.bean_cells(rows("120RA", ["120RA_Top"], "")[1:])

    def test_add_level_signals_puts_each_rows_comment_on_its_bean(self):
        root = ET.Element("layout-config")
        ET.SubElement(root, "signalheads")
        ET.SubElement(root, "signalmasts")
        mast = dict(cp="CP 107", switch="119", dir="west", mast="Mast 120RA", device_system_name="",
                    system_name=f"IF$shsm:basic:one-searchlight({V}120RA)", heads=[(V + "120RA", "Head 120RA")])
        cells = {("mast", "Mast 120RA"): ("", "mast words"), ("head", "Head 120RA"): ("", "head words")}
        T.add_level_signals(root, [mast], cells)
        got = {e.findtext("userName"): e.findtext("comment") for e in root.iter() if e.find("comment") is not None}
        self.assertEqual(got, {"Mast 120RA": "mast words", "Head 120RA": "head words"})
        with self.assertRaisesRegex(T.BuildError, "has no bean_comment"):
            T.add_level_signals(root, [dict(mast, mast="Mast 122RA")], cells)


if __name__ == "__main__":
    unittest.main()

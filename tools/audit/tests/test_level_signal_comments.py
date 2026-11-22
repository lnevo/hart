"""le_tables.add_level_signals: each main and upper head's and mast's comment names its planned physical device, or says
it is not on a node yet when the draft plant has no board room for it (ADR-024), never "planned ?"."""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
import le_tables as T  # noqa: E402

V = "IH:HART:C3:"


def row(mast, heads, device):
    return dict(cp="CP 107", switch="119", dir="west", mast=f"Mast {mast}", device_system_name=device,
                system_name="IF$shsm:basic:two-searchlight" + "".join(f"({V}{h})" for h in heads),
                heads=[(V + h, f"Head {h}") for h in heads])


def comments(rows):
    root = ET.Element("layout-config")
    ET.SubElement(root, "signalheads")
    ET.SubElement(root, "signalmasts")
    T.add_level_signals(root, rows)
    return {e.findtext("userName"): e.findtext("comment") for e in root.iter() if e.find("comment") is not None}


class Comments(unittest.TestCase):
    def test_a_planned_device_is_named_and_a_missing_one_is_not_on_a_node_yet(self):
        got = comments([row("120RA", ["120RA_Top", "120RA_Bottom"], "IF$shsm:basic:two-searchlight(IH4338)(IH4339)"),
                        row("120RB", ["120RB_Top", "120RB_Bottom"], "")])
        self.assertEqual(got["Head 120RA_Bottom"], "CP 107 | Switch 119 | virtual (device map); planned IH4339")
        self.assertEqual(got["Mast 120RA"], "CP 107 | Switch 119 | West | virtual (device map); planned "
                                            "IF$shsm:basic:two-searchlight(IH4338)(IH4339)")
        for name in ("Head 120RB_Top", "Head 120RB_Bottom"):
            self.assertEqual(got[name], "CP 107 | Switch 119 | virtual (device map); not on a node yet")
        # a mast names the way it faces after its place; its heads do not (owner, 2026-11-22)
        self.assertEqual(got["Mast 120RB"], "CP 107 | Switch 119 | West | virtual (device map); not on a node yet")
        self.assertFalse([c for c in got.values() if "?" in c or c.endswith("planned ")])


if __name__ == "__main__":
    unittest.main()

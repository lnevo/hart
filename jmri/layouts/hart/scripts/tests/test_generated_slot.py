"""le_signal_boundaries.csv's generated_slot: on a generated panel (build_layout_le.py --as-live) a switch drawn with
legs B and C swapped (Switch 13, TO1) has its mast in the other slot, and every script that binds or checks masts by
slot reads that column there (hartlib.tables.boundary_slot), never the hand-drawn panel's slot."""
from __future__ import annotations

import importlib.util
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[3]
sys.path.insert(0, str(REPO / "tools/hartlib/src"))
from hartlib import paths, tables  # noqa: E402

CSV = paths.LAYOUT_DATA / "le_signal_boundaries.csv"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class GeneratedSlot(unittest.TestCase):
    def test_boundary_slot(self) -> None:
        row = {"slot": "B", "generated_slot": "C"}
        self.assertEqual(tables.boundary_slot(row, False), "B")
        self.assertEqual(tables.boundary_slot(row, True), "C")
        self.assertEqual(tables.boundary_slot({"slot": "west", "generated_slot": ""}, True), "west")
        self.assertEqual(tables.boundary_slot({"slot": "A"}, True), "A")      # an older CSV with no column

    def test_apply_le_sml_facing_binds_14r_on_the_generated_leg(self) -> None:
        mod = load("apply_le_sml_facing")
        hand, _ = mod.load_assignments(CSV)
        gen, _ = mod.load_assignments(CSV, generated=True)
        self.assertEqual(hand["TO1"].get("B"), "Mast 14R")
        self.assertNotIn("C", hand["TO1"])
        self.assertEqual(gen["TO1"].get("C"), "Mast 14R")
        self.assertNotIn("B", gen["TO1"])

    def test_validate_le_signalling_checks_the_generated_leg(self) -> None:
        mod = load("validate_le_signalling")
        rows = mod.load_boundary_csv(CSV)
        self.assertIn((("turnout", "TO1", "B"), "Mast 14R"), mod.csv_bindings(rows, False))
        self.assertIn((("turnout", "TO1", "C"), "Mast 14R"), mod.csv_bindings(rows, True))
        self.assertNotIn((("turnout", "TO1", "B"), "Mast 14R"), mod.csv_bindings(rows, True))

    def test_audit_panel_contracts_takes_the_generated_slot_only_on_a_generated_panel(self) -> None:
        audit_mod = load("audit_panel_contracts")
        b = audit_mod.Boundary("turnout", "TO1", "B", "Mast 14R", generated_slot="C")
        on_c = ET.fromstring('<LayoutEditor><layoutturnout ident="TO1" signalCMast="Mast 14R"/></LayoutEditor>')
        on_b = ET.fromstring('<LayoutEditor><layoutturnout ident="TO1" signalBMast="Mast 14R"/></LayoutEditor>')
        for panel, generated, ok in ((on_c, True, True), (on_c, False, False), (on_b, False, True),
                                     (on_b, True, False)):
            audit = audit_mod.Audit("t", Path("t"))
            audit_mod.audit_bindings(panel, [b], audit, generated=generated)
            with self.subTest(generated=generated, panel="C" if panel is on_c else "B"):
                self.assertEqual(not audit.errors, ok, audit.errors)


if __name__ == "__main__":
    unittest.main()

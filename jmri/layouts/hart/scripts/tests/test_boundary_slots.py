"""le_signal_boundaries.csv: every script that binds or checks masts by slot reads each row's own slot. Switch 13's
facts hold the Barn on its diverging leg C since 2026-11-18, so Mast 14R's row records C."""
from __future__ import annotations

import csv
import importlib.util
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[3]
sys.path.insert(0, str(REPO / "tools/hartlib/src"))
from hartlib import paths  # noqa: E402

CSV = paths.LAYOUT_DATA / "le_signal_boundaries.csv"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class BoundarySlots(unittest.TestCase):
    def test_apply_le_sml_facing_binds_14r_on_leg_c(self) -> None:
        mod = load("apply_le_sml_facing")
        turnouts, _ = mod.load_assignments(CSV)
        self.assertEqual(turnouts["TO1"].get("C"), "Mast 14R")
        self.assertNotIn("B", turnouts["TO1"])

    def test_audit_panel_contracts_checks_the_rows_slot(self) -> None:
        audit_mod = load("audit_panel_contracts")
        b = audit_mod.Boundary("turnout", "TO1", "C", "Mast 14R")
        on_c = ET.fromstring('<LayoutEditor><layoutturnout ident="TO1" signalCMast="Mast 14R"/></LayoutEditor>')
        on_b = ET.fromstring('<LayoutEditor><layoutturnout ident="TO1" signalBMast="Mast 14R"/></LayoutEditor>')
        for panel, ok in ((on_c, True), (on_b, False)):
            audit = audit_mod.Audit("t", Path("t"))
            audit_mod.audit_bindings(panel, [b], audit)
            with self.subTest(panel="C" if panel is on_c else "B"):
                self.assertEqual(not audit.errors, ok, audit.errors)


class ReadersAgree(unittest.TestCase):
    """The audit, the facing script and the LE build's check read the committed file as the same rows."""

    def test_same_rows(self) -> None:
        with CSV.open(newline="", encoding="utf-8") as fh:   # the file as written, each value stripped
            build = {(r["kind"].strip(), r["ident"].strip(), r["slot"].strip(), r["mast_user_name"].strip())
                     for r in csv.DictReader(fh)}
        audit = {(b.kind, b.ident, b.slot, b.mast) for b in load("audit_panel_contracts").load_boundaries(CSV)}
        turnouts, anchors = load("apply_le_sml_facing").load_assignments(CSV)
        facing = {(kind, ident, slot, mast) for kind, by in (("turnout", turnouts), ("anchor", anchors))
                  for ident, slots in by.items() for slot, mast in slots.items()}
        self.assertEqual(audit, build)
        self.assertEqual(facing, build)


if __name__ == "__main__":
    unittest.main()

"""audit_panel_contracts.audit_bindings holds every staging mast (staging_masts.csv) to one slot that resolves to its
facing and protected blocks, by the plugin's slot index, the rule the LE build places masts by. It replaces the
recorded idents and slots of le_signal_boundaries.csv (retired)."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class AuditBindings(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.apc = load("audit_panel_contracts")
        cls.staging = cls.apc.load_staging_masts()

    def panel(self):
        root = tables.read(paths.TABLES_XML)
        audit = self.apc.Audit("t", Path("t"))
        return self.apc.select_panel(root, audit)

    def run_audit(self, panel, staging=None):
        audit = self.apc.Audit("t", Path("t"))
        self.apc.audit_bindings(panel, self.staging if staging is None else staging, audit)
        return audit

    def test_the_repo_panel_binds_every_staging_mast_where_it_belongs(self) -> None:
        audit = self.run_audit(self.panel())
        self.assertEqual([], audit.errors)
        self.assertLessEqual({m.mast for m in self.staging}, {b[3] for b in audit.facts["bindings"]})

    def test_a_mast_moved_to_a_slot_facing_another_block_is_an_error(self) -> None:
        panel = self.panel()
        turnout = next(t for t in panel.iter("layoutturnout") if t.find("signalCMast") is not None)
        mast = turnout.find("signalCMast")
        text = mast.text
        turnout.remove(mast)
        other = next(L for L in "ABD" if turnout.get(f"connect{L.lower()}name") and turnout.find(f"signal{L}Mast") is None)
        import xml.etree.ElementTree as ET
        ET.SubElement(turnout, f"signal{other}Mast").text = text
        errors = self.run_audit(panel).errors
        self.assertTrue(any(text in e for e in errors), errors)

    def test_a_staging_mast_missing_from_the_panel_is_an_error(self) -> None:
        panel = self.panel()
        turnout = next(t for t in panel.iter("layoutturnout") if t.find("signalCMast") is not None)
        gone = turnout.find("signalCMast")
        name = gone.text
        turnout.remove(gone)
        errors = self.run_audit(panel).errors
        self.assertTrue(any(name in e and "found 0" in e for e in errors), errors)

    def test_a_bound_mast_no_file_names_is_an_error(self) -> None:
        errors = self.run_audit(self.panel(), self.staging[1:]).errors
        self.assertTrue(any("no mast file names" in e and self.staging[0].mast in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()

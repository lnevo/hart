"""audit_panel_contracts.audit_bindings holds every staging mast (masts.csv) to one slot that resolves to its
facing and protected blocks, by the plugin's slot index, the rule the LE build places masts by. It replaces the
recorded idents and slots of le_signal_boundaries.csv (retired)."""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import importlib.util
import io
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class AuditBindings(unittest.TestCase):
    apc: ClassVar[ModuleType]
    staging: ClassVar[Any]

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
        self.apc.audit_bindings(panel, self.staging if staging is None else staging, audit,
                                levels=self.apc.draws_levels(panel))
        return audit

    def test_the_repo_panel_binds_every_staging_mast_where_it_belongs(self) -> None:
        audit = self.run_audit(self.panel())
        self.assertEqual([], audit.errors)
        self.assertLessEqual({m.mast for m in self.staging}, {b[3] for b in audit.facts["bindings"]})

    def test_a_mast_moved_to_a_slot_facing_another_block_is_an_error(self) -> None:
        panel = self.panel()
        ix = self.apc.slots_index(panel)
        pick = None
        for t in panel.iter("layoutturnout"):
            for src in "ABCD":
                el = t.find(f"signal{src}Mast")
                if el is None or not (el.text or "").strip():
                    continue
                for dst in "ABCD":
                    if dst != src and t.get(f"connect{dst.lower()}name") and t.find(f"signal{dst}Mast") is None \
                            and ix.blocks("turnout", t.get("ident"), dst) != ix.blocks("turnout", t.get("ident"), src):
                        pick = (t, el, dst)
                        break
                if pick:
                    break
            if pick:
                break
        self.assertIsNotNone(pick, "no turnout mast has a free leg that faces another block: the test cannot move one")
        turnout, el, dst = pick
        text = el.text
        turnout.remove(el)
        ET.SubElement(turnout, f"signal{dst}Mast").text = text
        errors = self.run_audit(panel).errors
        self.assertTrue(any(text in e and "faces" in e for e in errors), errors)

    def test_a_repeated_ident_is_an_error(self) -> None:
        panel = self.panel()
        first = next(iter(panel.iter("positionablepoint")))
        panel.append(ET.fromstring(f'<positionablepoint ident="{first.get("ident")}" x="0" y="0"/>'))
        errors = self.run_audit(panel).errors
        self.assertTrue(any("is used 2 times" in e for e in errors), errors)

    def test_main_upper_protects_split_on_semicolons(self) -> None:
        self.assertEqual(["OS A", "OS B"], self.apc.split_protects("OS A;OS B"))
        self.assertEqual([], self.apc.split_protects(""))

    def test_a_missing_plugin_is_a_setup_error_main_reports_in_one_line(self) -> None:
        with mock.patch.dict(os.environ, {"SCHEMATIC_PLUGIN": "/nonexistent"}):
            with self.assertRaises(self.apc.SetupError):
                self.apc.slots_index(self.panel())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = self.apc.main(["--strict"])
        self.assertEqual(1, code)
        self.assertEqual(1, len(out.getvalue().strip().splitlines()), out.getvalue())

    def test_load_staging_masts_follows_a_patch_of_its_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "masts.csv"
            lines = self.apc.MASTS.read_text(encoding="utf-8").splitlines(keepends=True)
            path.write_text("".join(lines[:3]), encoding="utf-8")         # the header and two staging rows
            with mock.patch.object(self.apc, "MASTS", path):
                rows = self.apc.load_staging_masts()
        self.assertEqual([("Mast 2L", 1, ("OS Switch 1",)), ("Mast 2R", 1, ("OS Switch 1",))],
                         [(m.mast, m.level, m.protects) for m in rows])


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


class AuditSettings(unittest.TestCase):
    apc: ClassVar[ModuleType]
    root: ClassVar[ET.Element]

    @classmethod
    def setUpClass(cls) -> None:
        cls.apc = load("audit_panel_contracts")
        cls.root = tables.read(paths.TABLES_XML)

    def errors(self, root):
        audit = self.apc.Audit("t", Path("t"))
        self.apc.audit_generated_settings(root, audit)
        return audit.errors

    def test_the_repo_tables_hold_the_settings(self) -> None:
        self.assertEqual([], self.errors(self.root))

    def test_continuing_one_on_a_princess_turnout_is_an_error(self) -> None:
        root = copy.deepcopy(self.root)
        t = next(t for t in root.iter("layoutturnout") if t.get("ident") == "TOL29")
        t.set("continuing", "1")
        self.assertTrue(any("TOL29" in e for e in self.errors(root)))

    def test_the_continuing_turnouts_are_switches_csvs_idents(self) -> None:
        self.assertEqual(self.apc.continuing_closed_idents(), ("TOL29", "TOR36", "TO111", "TO113", "TO117"))

    def test_a_continuing_switch_without_an_ident_is_an_audit_error(self) -> None:
        source = self.apc.railroad_facts.Sources.under().switches
        lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
        header = lines[0].rstrip("\n").split(",")
        col, sw = header.index("le_ident"), header.index("switch")
        out = []
        for line in lines:
            cells = line.rstrip("\n").split(",")
            if cells[sw] == "39" and cells[col]:
                cells[col] = ""
            out.append(",".join(cells) + "\n")
        with tempfile.TemporaryDirectory() as tmp:
            copy_path = Path(tmp) / source.name
            copy_path.write_text("".join(out), encoding="utf-8")
            with self.assertRaisesRegex(self.apc.railroad_facts.FactsError, "no staging le_ident for Switch 39"):
                self.apc.continuing_closed_idents(copy_path)
            audit = self.apc.Audit("t", Path("t"))
            self.apc.audit_generated_settings(self.root, audit, switches=copy_path)
        self.assertEqual(audit.errors, ["continuing turnouts: switches.csv gives no staging le_ident for Switch 39"])

    def test_blockrouting_off_is_an_error(self) -> None:
        root = copy.deepcopy(self.root)
        next(root.iter("layoutblocks")).set("blockrouting", "no")
        self.assertTrue(any("blockrouting" in e for e in self.errors(root)))

    def test_an_aar_two_head_mast_must_disable_restricting(self) -> None:
        root = ET.fromstring('<r><signalmast><systemName>IF$shsm:AAR-1946:SL-2-high-abs(x)</systemName>'
                             '<disabledAspects><disabledAspect>Clear Alt</disabledAspect></disabledAspects>'
                             '</signalmast><layoutblocks blockrouting="yes"/></r>')
        self.assertTrue(any("Restricting" in e for e in self.errors(root)))

    def test_virtual_masts_must_agree_with_devices_csv(self) -> None:
        root = tables.read(paths.TABLES_XML)
        staging = self.apc.load_staging_masts()
        flipped = [dataclasses.replace(m, system_name="") if m.system_name.startswith("IF$vsm:") else m
                   for m in staging]
        audit = self.apc.Audit("t", Path("t"))
        self.apc.audit_masts(root, flipped, audit)
        self.assertTrue(any("differ between masts.csv and the device master" in e for e in audit.errors))


if __name__ == "__main__":
    unittest.main()

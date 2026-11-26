"""The generated CATS desks and the USS CTC board build from committed data alone (CATS cut-over, 2026-11-15).

Each build runs in a child process that may not open the hand-wired Designer panel (archive/data/panels/HART_Digicon.xml), the checkout's
tables.xml or the desks themselves (cats/panels/HART_CTC.xml, HART_ABS.xml and the bindings, generated since the
CATS cut-over): an audit hook stops any open of them. The desk build is let read its own outputs only once
generate() has returned, for --check's comparison, so it never reads them as a source. The tables it reads are a
temporary copy with every Layout Editor panel taken out (HART_TABLES points at it). Then
  - build_cats_panel.py --check finds both desks and the bindings current (byte-identical to the committed files);
  - gen_ctc_track_plan.py --xml-only, run on copies of GUIObjects.xml and tables.xml, leaves them byte-identical.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import parked  # noqa: E402
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
GUI = ROOT / "jmri/layouts/hart/ctc/GUIObjects.xml"
DESKS = [ROOT / "cats/panels" / n for n in ("HART_CTC.xml", "HART_ABS.xml", "HART_CTC.bindings.json")] + [
    ROOT / "archive/data/panels/HART_Digicon.xml"]

# The child: refuse to open the forbidden files, then run the script as __main__ with the given arguments.
GUARD = """
import os, runpy, sys
forbidden = {os.path.realpath(p) for p in sys.argv[1].split(os.pathsep)}
def hook(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        p = os.path.realpath(os.fsdecode(args[0]))
        if p in forbidden:
            raise PermissionError(f"from-scratch build opened {p}")
sys.addaudithook(hook)
script = sys.argv[2]
sys.argv = [script] + sys.argv[3:]
if script.endswith("build_cats_panel.py"):
    # its outputs are forbidden until generate() has returned: then --check may read them to compare
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_cats_panel", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_cats_panel"] = mod
    spec.loader.exec_module(mod)
    outputs = {os.path.realpath(str(p)) for p in (mod.OUT, mod.OUT_ABS, mod.BINDINGS)}
    generate = mod.generate
    def generated(*a, **k):
        result = generate(*a, **k)
        forbidden.difference_update(outputs)
        return result
    mod.generate = generated
    sys.exit(mod.main(sys.argv[1:]))
runpy.run_path(script, run_name="__main__")
"""


def run(script: str, *args: str, tables: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, HART_TABLES=str(tables))
    env.pop("SCHEMATIC_REQUIRED", None)
    forbidden = os.pathsep.join(str(p) for p in DESKS + [TABLES])
    return subprocess.run([sys.executable, "-c", GUARD, forbidden, str(ROOT / script), *args],
                          capture_output=True, text=True, env=env, cwd=ROOT)


class FromScratch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp())
        tree = ET.parse(TABLES)
        root = tree.getroot()
        for panel in root.findall("LayoutEditor"):
            root.remove(panel)
        cls.tables = cls.tmp / "tables.xml"
        tree.write(cls.tables, encoding="UTF-8", xml_declaration=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp)

    def test_the_tables_copy_has_no_layout_editor_panel(self):
        self.assertEqual(ET.parse(self.tables).getroot().findall("LayoutEditor"), [])

    def test_the_guard_stops_a_desk_read(self):
        probe = self.tmp / "probe.py"
        probe.write_text(f"open({str(DESKS[0])!r}).read()\n", encoding="utf-8")
        out = run(str(probe), tables=self.tables)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("from-scratch build opened", out.stderr)

    def test_the_generated_desks_are_current(self):
        out = run("tools/schematic/build_cats_panel.py", "--check", tables=self.tables)
        if "SKIPPED" in out.stdout:
            self.skipTest(out.stdout.strip().splitlines()[-1])
        self.assertEqual(out.returncode, 0, out.stdout[-3000:] + out.stderr[-3000:])
        for name in ("HART_CTC.xml", "HART_ABS.xml", "HART_CTC.bindings.json"):
            self.assertIn(f"cats/panels/{name} is current", out.stdout)

    def test_the_uss_board_is_unchanged(self):
        gui, tables = self.tmp / "GUIObjects.xml", self.tmp / "uss_tables.xml"
        shutil.copyfile(GUI, gui)
        # the USS CTC machine parked (hartlib.parked): its panel is rebuilt in a copy of the tables with it put back
        shutil.copyfile(parked.with_parked_file({"uss"}, TABLES), tables)
        before = tables.read_bytes()
        out = run("jmri/layouts/hart/scripts/gen_ctc_track_plan.py", "--xml-only", "--gui", str(gui),
                  "--tables", str(tables), tables=self.tables)
        self.assertEqual(out.returncode, 0, out.stdout[-3000:] + out.stderr[-3000:])
        self.assertEqual(gui.read_bytes(), GUI.read_bytes())
        if "uss" in parked.PARKED:
            self.assertEqual(uss_panel(tables.read_bytes()), uss_panel(before))
        else:
            self.assertEqual(tables.read_bytes(), TABLES.read_bytes())


def uss_panel(data: bytes) -> str:
    """The USS CTC panel of a tables file, canonical (whitespace between elements dropped)."""
    pe = next(p for p in ET.fromstring(data).iter("paneleditor") if p.get("name") == "USS CTC")
    return ET.canonicalize(ET.tostring(pe, encoding="unicode"), strip_text=True)


if __name__ == "__main__":
    unittest.main()

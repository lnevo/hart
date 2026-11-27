"""panel_window_sizes.py: a profile's saved panel windows take tables.xml's size; position, zoom, other windows and
the rest of the file stay as JMRI wrote them. hartlib.jmri_profile's own tests cover the edit."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import panel_window_sizes as pws  # noqa: E402

TABLES = """<?xml version="1.0" encoding="UTF-8"?>
<layout-config>
  <LayoutEditor class="x" name="HART Railroad" windowwidth="1920" windowheight="1032" panelheight="1272"/>
  <LayoutEditor class="x" name="Main Level" windowwidth="1920" windowheight="385" panelheight="325"/>
  <LayoutEditor class="x" name="New Level" windowwidth="1920" windowheight="400" panelheight="340"/>
</layout-config>
"""
UI = """<?xml version="1.0" encoding="UTF-8"?>
<auxiliary-configuration>
    <windowDetails xmlns="http://jmri.org/xml/schema/auxiliary-configuration/window-details-4-3-5.xsd">
        <window xmlns="" class="jmri.jmrit.display.layoutEditor.LayoutEditor:Main Level" height="408.0" locX="-69.0" locY="406.0" width="1920.0">
            <properties><property><key>zoom</key><value class="java.lang.Double">0.79</value></property></properties>
        </window>
        <window xmlns="" class="jmri.jmrit.withrottle.UserInterface" height="250.0" locX="25.0" locY="26.0" width="400.0"/>
        <window xmlns="" class="jmri.jmrit.display.layoutEditor.LayoutEditor:HART Railroad" height="1018.0" locX="0.0" locY="26.0" width="1920.0"/>
    </windowDetails>
</auxiliary-configuration>
"""


class PanelWindowSizes(unittest.TestCase):
    def files(self, ui=UI):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        t, u = Path(tmp.name) / "tables.xml", Path(tmp.name) / "user-interface.xml"
        t.write_text(TABLES)
        u.write_text(ui)
        return t, u

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = pws.main(list(argv))
        self.err = err.getvalue()
        return code, out.getvalue().splitlines()

    def test_each_saved_panel_window_takes_the_tables_size_and_nothing_else_changes(self):
        t, u = self.files()
        code, lines = self.run_main(str(u), "--tables", str(t))
        self.assertEqual(code, 0)
        new = u.read_text()
        self.assertIn('LayoutEditor:Main Level" height="385.0" locX="-69.0" locY="406.0" width="1920.0">', new)
        self.assertIn('LayoutEditor:HART Railroad" height="1032.0" locX="0.0" locY="26.0" width="1920.0"/>', new)
        self.assertIn('UserInterface" height="250.0" locX="25.0" locY="26.0" width="400.0"/>', new)   # not a panel
        self.assertIn("<value class=\"java.lang.Double\">0.79</value>", new)                           # zoom kept
        self.assertEqual(len(new.splitlines()), len(UI.splitlines()))
        self.assertIn("Main Level: 1920.0x408.0 -> 1920.0x385.0", lines)
        self.assertIn("New Level: no saved window (JMRI opens it at the tables' size)", lines)   # a new panel

    def test_check_changes_nothing_and_says_whether_sizes_differ(self):
        t, u = self.files()
        self.assertEqual(self.run_main(str(u), "--tables", str(t), "--check")[0], 1)
        self.assertEqual(u.read_text(), UI)
        self.run_main(str(u), "--tables", str(t))
        code, lines = self.run_main(str(u), "--tables", str(t), "--check")
        self.assertEqual(code, 0)
        self.assertIn("every saved panel window already has the tables' size", lines)

    def test_a_panel_name_with_an_escaped_character_is_matched(self):
        t, u = self.files(ui=UI.replace("LayoutEditor:Main Level", "LayoutEditor:P&amp;CV Yard"))
        t.write_text(TABLES.replace('name="Main Level"', 'name="P&amp;CV Yard"'))
        code, lines = self.run_main(str(u), "--tables", str(t))
        self.assertIn("P&CV Yard: 1920.0x408.0 -> 1920.0x385.0", lines)
        self.assertIn('LayoutEditor:P&amp;CV Yard" height="385.0"', u.read_text())

    def test_backup_keeps_the_file_as_it_was_only_when_it_writes(self):
        t, u = self.files()
        code, lines = self.run_main(str(u), "--tables", str(t), "--backup")
        self.assertEqual(code, 0)
        [copy] = sorted(u.parent.glob("user-interface.xml.hart-*.bak"))
        self.assertEqual(copy.read_text(), UI)
        self.assertIn(f"wrote {u}; its previous copy is {copy}", lines)
        self.run_main(str(u), "--tables", str(t), "--backup")          # nothing left to change: no second copy
        self.assertEqual(len(list(u.parent.glob("*.bak"))), 1)

    def test_a_file_that_is_not_a_user_interface_file_exits_2(self):
        t, u = self.files(ui="<other/>")
        self.assertEqual(self.run_main(str(u), "--tables", str(t))[0], 2)
        self.assertIn("panel_window_sizes:", self.err)
        self.assertIn("no <windowDetails>", self.err)
        self.assertEqual(u.read_text(), "<other/>")

    def test_a_panel_without_a_window_size_exits_2(self):
        t, u = self.files()
        t.write_text('<layout-config><LayoutEditor name="Bare"/></layout-config>')
        self.assertEqual(self.run_main(str(u), "--tables", str(t))[0], 2)
        self.assertIn("Bare has no window size", self.err)

    def test_without_tables_it_reads_the_checkouts(self):
        t, u = self.files()
        code, lines = self.run_main(str(u), "--check")
        self.assertIn(code, (0, 1))
        self.assertTrue(any(line.startswith("HART Railroad: ") for line in lines) or
                        "every saved panel window already has the tables' size" in lines, lines)


if __name__ == "__main__":
    unittest.main()

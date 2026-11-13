"""hartlib.tables: unchanged saves are byte-identical, and the lookups find every bean."""
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import paths, tables  # noqa: E402

# The shape of a raw PanelPro Store: double-quoted declaration, stylesheet line, a comment
# inside the root, a final newline, escapes, an empty element and attribute order.
STORE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<?xml-stylesheet href="/xml/XSLT/panelfile-5-5-5.xsl" type="text/xsl"?>\n'
    '<layout-config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:noNamespaceSchemaLocation="http://jmri.org/xml/schema/layout-5-5-5.xsd">\n'
    '  <jmriversion>\n    <major>5</major>\n    <modifier />\n  </jmriversion>\n'
    '  <sensors class="a.MqttSensorManagerXml">\n'
    '    <sensor inverted="false">\n      <systemName>M2S1</systemName>\n'
    '      <userName>BS K-1</userName>\n    </sensor>\n  </sensors>\n'
    '  <sensors class="a.InternalSensorManagerXml">\n'
    '    <defaultInitialState>unknown</defaultInitialState>\n'
    '    <sensor inverted="false">\n      <systemName>ISNX:1</systemName>\n    </sensor>\n'
    '  </sensors>\n'
    '  <turnouts class="a.OlcbTurnoutManagerXml">\n'
    '    <operations automate="false" />\n'
    '    <turnout feedback="DIRECT" inverted="false">\n      <systemName>MTT1</systemName>\n'
    '      <userName>DCC Switch 1</userName>\n    </turnout>\n  </turnouts>\n'
    '  <turnouts class="a.MqttTurnoutManagerXml">\n'
    '    <turnout feedback="DIRECT" inverted="false">\n      <systemName>M2T1</systemName>\n'
    '      <userName>Switch 1</userName>\n      <comment>A &amp; B &lt;2&gt; "q"</comment>\n'
    '    </turnout>\n  </turnouts>\n'
    '  <signalmasts class="a.DefaultSignalMastManagerXml">\n'
    '    <signalmast class="a.SignalHeadSignalMastXml">\n'
    '      <systemName>IF$shsm:basic:one-low(IH1)</systemName>\n'
    '      <userName>Mast 2R</userName>\n    </signalmast>\n'
    '    <virtualsignalmast class="a.VirtualSignalMastXml">\n'
    '      <systemName>IF$vsm:basic:one-low($1)</systemName>\n'
    '      <userName>Mast 4LA</userName>\n      <unlit allowed="yes" />\n'
    '    </virtualsignalmast>\n  </signalmasts>\n'
    '  <blocks class="a.BlockManagerXml">\n'
    '    <defaultspeed>Normal</defaultspeed>\n'
    '    <block systemName="IB1">\n      <systemName>IB1</systemName>\n'
    '      <userName>OS Switch 1</userName>\n    </block>\n'
    '    <block systemName="IB1" length="254.0" curve="0">\n      <systemName>IB1</systemName>\n'
    '      <userName>OS Switch 1</userName>\n      <permissive>no</permissive>\n    </block>\n'
    '  </blocks>\n'
    '  <signalmastlogics class="a.DefaultSignalMastLogicManagerXml">\n'
    '    <logicDelay>500</logicDelay>\n'
    '    <signalmastlogic source="Mast 2R">\n      <sourceSignalMast>Mast 2R</sourceSignalMast>\n'
    '      <destinationMast destination="Mast 4LA">\n'
    '        <destinationSignalMast>Mast 4LA</destinationSignalMast>\n      </destinationMast>\n'
    '    </signalmastlogic>\n  </signalmastlogics>\n'
    '  <LayoutEditor name="HART Railroad" class="a.LayoutEditorXml">\n'
    '    <layoutturnout ident="TO1" type="RH_TURNOUT" continuing="4" turnoutname="Switch 1" />\n'
    '    <layoutturnout ident="TO2" type="LH_TURNOUT" turnoutname="MTT1" />\n'
    '  </LayoutEditor>\n'
    '  <LayoutEditor name="Dispatcher System" class="a.LayoutEditorXml" />\n'
    '  <!--Written by JMRI version 5.16 on Mon Sep 07 15:46:05 EDT 2026-->\n'
    '</layout-config>\n'
).encode("utf-8")


def no_jmri():
    return mock.patch.dict(os.environ, {"HART_GUARD_JMRI_RUNNING": "0"})


class RoundTripTest(unittest.TestCase):
    def test_repo_tables_xml_is_byte_identical(self):
        original = paths.TABLES_XML.read_bytes()
        doc = tables.load()
        self.assertEqual(doc.path, paths.TABLES_XML)
        self.assertFalse(doc.changed())
        self.assertEqual(doc.tobytes(), original)
        with tempfile.TemporaryDirectory() as d, no_jmri():
            out = Path(d) / "tables.xml"
            self.assertTrue(doc.save(out))
            self.assertEqual(out.read_bytes(), original)
            self.assertFalse(doc.save(out), "an identical file is not rewritten")

    def test_matches_the_existing_elementtree_writers_on_the_repo_file(self):
        # apply_yard_throat_blocks and friends: ET.parse + write(xml_declaration=True).
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "et.xml"
            ET.parse(paths.TABLES_XML).write(out, encoding="UTF-8", xml_declaration=True)
            self.assertEqual(tables.load().tobytes(), out.read_bytes())

    def test_panelpro_store_is_byte_identical(self):
        doc = tables.loads(STORE)
        self.assertEqual(doc.tobytes(), STORE)
        self.assertTrue(doc.prolog.startswith(b'<?xml version="1.0"'))
        self.assertIn(b"xml-stylesheet", doc.prolog)
        self.assertEqual(doc.epilog, b"\n")

    def test_edit_is_written_and_only_the_edit_changes(self):
        doc = tables.loads(STORE)
        tables.by_user_name(tables.turnouts(doc.root))["Switch 1"].find("userName").text = "Switch 99"
        self.assertTrue(doc.changed())
        self.assertEqual(doc.tobytes(), STORE.replace(b">Switch 1<", b">Switch 99<"))
        with tempfile.TemporaryDirectory() as d, no_jmri():
            out = Path(d) / "tables.xml"
            out.write_bytes(STORE)
            os.chmod(out, 0o640)
            self.assertTrue(doc.save(out))
            self.assertEqual(out.read_bytes(), doc.tobytes())
            self.assertEqual(out.stat().st_mode & 0o777, 0o640)
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["tables.xml"])

    def test_bom_doctype_and_self_closing_root(self):
        for data in (b"\xef\xbb\xbf<?xml version='1.0' encoding='UTF-8'?>\n<a>\n  <b />\n</a>",
                     b"<!DOCTYPE a>\n<!-- c -->\n<a x=\"1\" />\n<!-- after -->\n",
                     b"<a><b>t</b></a>"):
            self.assertEqual(tables.loads(data).tobytes(), data)

    def test_rejects_non_utf8_and_text(self):
        with self.assertRaises(ValueError):
            tables.loads(b"<?xml version='1.0' encoding='ISO-8859-1'?><a />")
        with self.assertRaises(TypeError):
            tables.loads("<a />")

    def test_save_needs_a_path(self):
        with self.assertRaises(ValueError):
            tables.loads(STORE).save()


class JmriGuardTest(unittest.TestCase):
    def test_live_tables_are_guarded_temp_copies_are_not(self):
        self.assertTrue(tables._guarded(paths.TABLES_XML))
        self.assertTrue(tables._guarded(Path.home() / "JMRI_UserFiles/tables.xml"))
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(tables._guarded(Path(d) / "tables.xml"))
        self.assertFalse(tables._guarded(paths.LAYOUT_OUTPUT / "other.xml"))

    def test_save_refuses_while_jmri_runs(self):
        doc = tables.loads(STORE)
        doc.root.find("jmriversion/major").text = "6"
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "tables.xml"
            out.write_bytes(STORE)
            with mock.patch.object(tables, "_guarded", return_value=True), \
                    mock.patch.dict(os.environ, {"HART_GUARD_JMRI_RUNNING": "1"}):
                with self.assertRaises(RuntimeError):
                    doc.save(out)
                self.assertEqual(out.read_bytes(), STORE)
                self.assertTrue(doc.save(out, allow_while_jmri_runs=True))


class LookupTest(unittest.TestCase):
    def setUp(self):
        self.root = tables.loads(STORE).root

    def test_every_manager_section(self):
        self.assertEqual([tables.system_name(t) for t in tables.turnouts(self.root)], ["MTT1", "M2T1"])
        self.assertEqual([tables.system_name(s) for s in tables.sensors(self.root)], ["M2S1", "ISNX:1"])
        self.assertEqual(len(self.root.find("sensors").findall("sensor")), 1)  # the find() trap

    def test_names(self):
        sensors = tables.sensors(self.root)
        self.assertEqual(tables.user_name(sensors[1]), "")
        self.assertEqual(set(tables.by_user_name(sensors)), {"BS K-1"})
        self.assertEqual(set(tables.by_system_name(sensors)), {"M2S1", "ISNX:1"})
        self.assertEqual(set(tables.by_any_name(tables.turnouts(self.root))),
                         {"MTT1", "DCC Switch 1", "M2T1", "Switch 1"})
        self.assertEqual(tables.text(None, "x"), "")

    def test_masts_include_virtual(self):
        self.assertEqual([tables.user_name(m) for m in tables.masts(self.root)], ["Mast 2R", "Mast 4LA"])
        self.assertEqual(len(tables.masts(self.root, tags=("virtualsignalmast",))), 1)

    def test_blocks_full_pass(self):
        full = tables.blocks(self.root)
        self.assertEqual(len(full), 1)
        self.assertEqual(full[0].get("length"), "254.0")
        self.assertEqual(len(tables.blocks(self.root, full=False)), 1)

    def test_layout_editor_and_continuing(self):
        le = tables.layout_editor(self.root)
        self.assertEqual(le.get("name"), "HART Railroad")
        self.assertEqual(tables.layout_editor(self.root, "Dispatcher System").get("name"),
                         "Dispatcher System")
        self.assertIsNone(tables.layout_editor(self.root, "Nope"))
        senses = [tables.continuing_sense(lt) for lt in tables.layout_turnouts(le)]
        self.assertEqual(senses, [tables.THROWN, tables.CLOSED])

    def test_mast_logic(self):
        self.assertEqual(list(tables.mast_logic_sources(self.root)), ["Mast 2R"])
        self.assertEqual([(s, d) for s, d, _ in tables.mast_logic_pairs(self.root)],
                         [("Mast 2R", "Mast 4LA")])

    def test_elements_skips_comments(self):
        self.assertTrue(any(not isinstance(c.tag, str) for c in self.root))
        self.assertTrue(all(isinstance(c.tag, str) for c in tables.elements(self.root)))


class RepoTablesTest(unittest.TestCase):
    """The lookups agree with the repo file's own counts."""

    @classmethod
    def setUpClass(cls):
        cls.root = tables.read()

    def test_counts(self):
        r = self.root
        self.assertEqual(len(tables.turnouts(r)), sum(len(b.findall("turnout")) for b in r.findall("turnouts")))
        self.assertEqual(len(tables.masts(r)), len(r.findall("signalmasts/signalmast"))
                         + len(r.findall("signalmasts/virtualsignalmast")))
        full = tables.blocks(r)
        self.assertEqual(len(full), len(tables.blocks(r, full=False)))
        self.assertEqual(len({tables.system_name(b) for b in full}), len(full))
        self.assertEqual(tables.layout_editor(r).get("name"), "HART Railroad")
        self.assertEqual(len(tables.mast_logic_pairs(r)), sum(1 for _ in r.iter("destinationMast")))
        for lt in tables.layout_turnouts(tables.layout_editor(r)):
            self.assertIn(tables.continuing_sense(lt), (tables.CLOSED, tables.THROWN), lt.get("ident"))


if __name__ == "__main__":
    unittest.main()

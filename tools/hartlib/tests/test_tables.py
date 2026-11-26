"""hartlib.tables: unchanged saves are byte-identical, and the lookups find every bean."""
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

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


class RoundTripTest(unittest.TestCase):
    def test_repo_tables_xml_is_byte_identical(self):
        original = paths.TABLES_XML.read_bytes()
        doc = tables.load()
        self.assertEqual(doc.path, paths.TABLES_XML)
        self.assertFalse(doc.changed())
        self.assertEqual(doc.tobytes(), original)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "tables.xml"
            self.assertTrue(doc.save(out))
            self.assertEqual(out.read_bytes(), original)
            self.assertFalse(doc.save(out), "an identical file is not rewritten")

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
        with tempfile.TemporaryDirectory() as d:
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


class EscapeTest(unittest.TestCase):
    """JDOM's character escapes survive an unchanged save, and new text gets them too."""

    # Every character JDOM2 escapes: & < > and CR in text; & < > " CR LF tab in attributes.
    # Quotes and apostrophes stay literal in text, apostrophes in attributes.
    JDOM = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<layout-config>\n'
        '  <memory value="a&#xA;b&#x9;c&#xD;d &quot;q&quot; &lt;x&gt; &amp; \'s\'">\n'
        '    <comment>line one&#xD;\nline two &lt;3&gt; &amp; "q" \'s\'</comment>\n'
        '  </memory>\n'
        '</layout-config>\n'
    ).encode("utf-8")
    ELEMENTTREE = (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        '<layout-config>\n  <memory value="a&#10;b&#09;c&#13;d" />\n</layout-config>'
    ).encode("utf-8")

    def test_jdom_store_is_byte_identical(self):
        doc = tables.loads(self.JDOM)
        self.assertEqual(doc.escapes, "jdom")
        mem = doc.root.find("memory")
        self.assertEqual(mem.get("value"), "a\nb\tc\rd \"q\" <x> & 's'")
        self.assertEqual(mem.findtext("comment"), "line one\r\nline two <3> & \"q\" 's'")
        self.assertEqual(doc.tobytes(), self.JDOM)

    def test_elementtree_file_is_byte_identical(self):
        doc = tables.loads(self.ELEMENTTREE)
        self.assertEqual(doc.escapes, "elementtree")
        self.assertEqual(doc.tobytes(), self.ELEMENTTREE)

    def test_new_values_get_jdom_escapes(self):
        doc = tables.loads(STORE)
        sw = tables.by_user_name(tables.turnouts(doc.root))["Switch 1"]
        sw.set("note", "x\ny\tz\r\"")
        sw.find("comment").text = "a\rb"
        out = doc.tobytes()
        self.assertIn(b'note="x&#xA;y&#x9;z&#xD;&quot;"', out)
        self.assertIn(b"<comment>a&#xD;b</comment>", out)

    def test_elementtree_escapes_are_restored(self):
        tables.loads(self.JDOM).tobytes()
        self.assertEqual(ET.tostring(ET.fromstring('<a b="&#10;">\r</a>')), b'<a b="&#10;">\n</a>')
        self.assertTrue(callable(ET._serialize_xml))
        self.assertIs(ET._serialize_xml.__globals__, vars(ET))


class LinkTest(unittest.TestCase):
    def test_symlink_stays_a_link_and_its_target_is_written(self):
        doc = tables.loads(STORE)
        doc.root.find("jmriversion/major").text = "6"
        with tempfile.TemporaryDirectory() as d:
            real, link = Path(d) / "real.xml", Path(d) / "tables.xml"
            real.write_bytes(STORE)
            link.symlink_to(real)
            self.assertTrue(doc.save(link))
            self.assertTrue(link.is_symlink())
            self.assertEqual(real.read_bytes(), doc.tobytes())

    def test_hard_link_is_written_in_place(self):
        doc = tables.loads(STORE)
        doc.root.find("jmriversion/major").text = "6"
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "tables.xml", Path(d) / "other.xml"
            a.write_bytes(STORE + b"\n" * 50)  # longer than the new bytes: tail must go
            os.link(a, b)
            self.assertTrue(doc.save(a))
            self.assertEqual(b.read_bytes(), doc.tobytes())
            self.assertEqual(a.stat().st_ino, b.stat().st_ino)

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


class MastIconTest(unittest.TestCase):
    def test_appearance_and_icon_size(self):
        self.assertEqual(tables.mast_appearance("IF$shsm:basic:one-low(IH143)"), "one-low")
        self.assertEqual(tables.mast_appearance("IF$vsm:basic:one-low($1001)"), "one-low")
        self.assertEqual(tables.mast_appearance("IM1"), "")
        self.assertEqual(tables.mast_icon_size("IF$shsm:basic:one-low(IH143)"), (tables.MAST_ICON_DWARF, True))
        self.assertEqual(tables.mast_icon_size("IF$shsm:basic:two-searchlight(IH1)(IH2)"),
                         (tables.MAST_ICON_HIGH, True))
        self.assertEqual(tables.mast_icon_size("IF$shsm:basic:slow-lowish(IH1)"), (tables.MAST_ICON_HIGH, False))
        self.assertEqual(tables.mast_icon_size(""), (tables.MAST_ICON_HIGH, False))

    def test_masts_found_by_user_or_system_name(self):
        root = ET.fromstring("<layout-config><signalmasts><signalmast><systemName>IF$shsm:basic:one-low(IH1)"
                             "</systemName><userName>Mast 1</userName></signalmast><virtualsignalmast><systemName>"
                             "IF$vsm:basic:one-low($1)</systemName></virtualsignalmast></signalmasts></layout-config>")
        names = tables.mast_system_names(root)
        self.assertEqual(names["Mast 1"], "IF$shsm:basic:one-low(IH1)")
        self.assertEqual(names["IF$shsm:basic:one-low(IH1)"], "IF$shsm:basic:one-low(IH1)")
        self.assertEqual(names["IF$vsm:basic:one-low($1)"], "IF$vsm:basic:one-low($1)")


class GeneratedPanelMarkerTest(unittest.TestCase):
    """The hidden label that marks a generated Layout Editor panel (LE cut-over)."""

    def panel(self, markers: int) -> ET.Element:
        le = ET.Element("LayoutEditor", {"name": "HART Railroad"})
        for _ in range(markers):
            le.append(tables.generated_marker_label())
        return le

    def test_marker_is_a_hidden_label_with_the_marker_text(self):
        label = tables.generated_marker_label()
        self.assertEqual(("positionablelabel", "yes", tables.GENERATED_PANEL_MARKER),
                         (label.tag, label.get("hidden"), label.get("text")))

    def test_found_once_or_not_at_all(self):
        self.assertFalse(tables.generated_panel(None))
        self.assertFalse(tables.generated_panel(self.panel(0)))
        self.assertTrue(tables.generated_panel(self.panel(1)))
        with self.assertRaisesRegex(ValueError, "'HART Railroad' has 2 generated-panel markers"):
            tables.generated_panel(self.panel(2))

    def test_the_repo_panel_is_generated(self):
        # since the Layout Editor cut-over (Phase 5) the repo's panel is the generated one, which the build starts from
        self.assertTrue(tables.generated_panel(tables.layout_editor(tables.read(paths.REPO_TABLES_XML))))

    def test_require_generated_panel(self):
        root = ET.Element("layout-config")
        with self.assertRaisesRegex(ValueError, r"^t.xml: no main Layout Editor panel \(HART Railroad"):
            tables.require_generated_panel(root, "t.xml")
        root.append(self.panel(0))
        with self.assertRaisesRegex(ValueError, "^t.xml: the 'HART Railroad' panel is not a generated one"):
            tables.require_generated_panel(root, "t.xml")
        tables.layout_editor(root).append(tables.generated_marker_label())
        self.assertIs(tables.require_generated_panel(root, "t.xml"), tables.layout_editor(root))
        tables.layout_editor(root).append(tables.generated_marker_label())
        with self.assertRaisesRegex(ValueError, "^--reference x: Layout Editor panel 'HART Railroad' has 2"):
            tables.require_generated(tables.layout_editor(root), "--reference x")
        with self.assertRaisesRegex(ValueError, "^r: no main Layout Editor panel"):
            tables.require_generated(None, "r")


class BlockContentsTest(unittest.TestCase):
    def test_labels_go_on_the_label_layer_in_black_and_the_plugins_font_stays(self):
        le = ET.fromstring(
            '<LayoutEditor name="HART Railroad">'
            '<BlockContentsIcon blockcontents="Track West Ext" x="1394" y="232" level="0" fontFamily="Lucida Grande" '
            'fontname="LucidaGrande-Bold" size="12" red="51" green="51" blue="51" />'
            '<BlockContentsIcon blockcontents="Track K-1" x="10" y="20" level="4" fontFamily="Dialog" '
            'fontname="Dialog" red="0" green="0" blue="0" />'
            "</LayoutEditor>")
        self.assertEqual(6, len(tables.ensure_block_contents_visible(le, check=True)[1]))
        changes, errors = tables.ensure_block_contents_visible(le, check=False, spots={"Track K-1": (30, 40)})
        self.assertEqual((7, []), (changes, errors))
        west, k1 = le
        self.assertEqual(("4", "0"), (west.get("level"), west.get("red")))
        self.assertNotIn("fontFamily", west.attrib)
        self.assertNotIn("fontname", west.attrib)
        self.assertEqual(("Dialog", "30", "40"), (k1.get("fontFamily"), k1.get("x"), k1.get("y")))
        self.assertEqual((0, []), tables.ensure_block_contents_visible(le, check=True, spots={"Track K-1": (30, 40)}))

    def test_the_live_panel_labels_are_visible(self):
        le = tables.layout_editor(tables.read(paths.REPO_TABLES_XML))
        self.assertTrue(le.findall("BlockContentsIcon"))
        self.assertEqual((0, []), tables.ensure_block_contents_visible(le, check=True))


class OverrideSaveTest(unittest.TestCase):
    """While HART_TABLES is set, Tables.save refuses the checkout's file, the override and the profile."""

    def test_saves_refused_under_hart_tables(self):
        import subprocess
        src = str(Path(paths.__file__).resolve().parents[1])
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path\n"
            "from hartlib import paths, tables\n"
            "doc = tables.load(paths.TABLES_XML)\n"
            "for target in (paths.TABLES_XML, paths.REPO_TABLES_XML, paths.JMRI_USER_FILES / 'tables.xml'):\n"
            "    try:\n"
            "        doc.save(target); print('WROTE', target)\n"
            "    except RuntimeError as exc:\n"
            "        print('REFUSED', 'HART_TABLES is set' in str(exc))\n"
            "print('OTHER', doc.save(Path(sys.argv[2])))\n"
            "try:\n    paths.exit_if_overridden('x.py')\nexcept SystemExit as exc:\n    print('EXIT', exc.code[:5])\n")
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home"
            (home / "JMRI_UserFiles").mkdir(parents=True)
            copy = Path(d) / "tables.xml"
            copy.write_bytes(b"<layout-config><LayoutEditor name='HART Railroad'/></layout-config>")
            env = {**os.environ, "HART_TABLES": str(copy), "HOME": str(home), "HART_GUARD_JMRI_RUNNING": "0"}
            done = subprocess.run([sys.executable, "-c", code, src, str(Path(d) / "other.xml")], env=env,
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(0, done.returncode, done.stderr)
            self.assertEqual(["REFUSED True"] * 3 + ["OTHER True", "EXIT x.py:"], done.stdout.splitlines())
            self.assertEqual([], list((home / "JMRI_UserFiles").iterdir()))

    def test_no_message_without_hart_tables(self):
        if not paths.TABLES_OVERRIDDEN:
            self.assertIsNone(paths.check_only_message("x.py"))
            paths.exit_if_overridden("x.py")


if __name__ == "__main__":
    unittest.main()

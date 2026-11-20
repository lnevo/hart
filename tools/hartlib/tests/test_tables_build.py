"""hartlib.tables_build: the template, the master's staging beans, the discovered Signal Mast Logic, the Digicon rule
and the envelope of the generated tables.xml (ADR-029), on small fixtures and on the committed sources."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import devices as D, paths, railroad, tables  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402


def blank(**cells) -> dict:
    row = {c: "" for c in D.COLUMNS}
    row.update({"level": "1", "description": "A device.", **cells})
    return row


def rows() -> list[dict]:
    """A small staging: one turnout with its alias and feedback, a block and its detector, a wired and a virtual
    head, a head mast and a hidden mast."""
    return [
        blank(layer="turnout", role="turnout", user_name="Switch 1", assignment="field", system_name="M2T408",
              jmri_name="M2T408", dcc="100", wiring="Node: 4 Turnout: 0 | OU: 1 Ports: 1,2"),
        blank(layer="turnout", role="lcc_alias", user_name="DCC Switch 1", assignment="field", system_name="MTT100",
              jmri_name="MTT100", dcc="100", wiring="Node: 4 Turnout: 0 | OU: 1 Ports: 1,2"),
        blank(layer="fb", role="fb", user_name="FB Switch 1 N", assignment="field", system_name="M2S470",
              jmri_name="M2S470", wiring="Node: 4 Sensor: 3 | IN: 1 Ports: 1"),
        blank(layer="fb", role="fb", user_name="FB Switch 1 R", assignment="field", system_name="M2S471",
              jmri_name="M2S471", wiring="Node: 4 Sensor: 4 | IN: 1 Ports: 2"),
        blank(layer="block", role="os", user_name="OS Switch 1", assignment="field", system_name="IB:AUTO:0033",
              jmri_name="IB:AUTO:0033", layout_block="ILB33", jmri_comment="Brick CP, Switch 1"),
        blank(layer="occupancy", role="os", user_name="BS Switch 1", assignment="field", system_name="M2S401",
              jmri_name="M2S401", wiring="Node: 4 Block: 2", blocks="OS Switch 1"),
        blank(layer="mast", role="home", user_name="Mast 2L", assignment="virtual",
              system_name="IF$shsm:basic:one-searchlight(IH:HART:C1:2L)",
              jmri_name="IF$shsm:basic:one-searchlight(IH:HART:C1:2L)", jmri_comment="Brick | Switch 1"),
        blank(layer="mast", role="hidden", user_name="Mast 4LA", assignment="virtual",
              system_name="IF$vsm:basic:one-low($1001)", jmri_name="IF$vsm:basic:one-low($1001)", jmri_comment="Brick"),
        blank(layer="head", role="head", user_name="Head 2L", assignment="virtual", system_name="IH:HART:C1:2L",
              jmri_name="IH:HART:C1:2L", jmri_comment="Brick | Switch 1"),
        blank(layer="head", role="head", user_name="Head 6LB", assignment="field", system_name="IH432",
              jmri_name="IH432", wiring="Node: 4 Signal: 0 | OU: 2 Ports: 1,2,3"),
        blank(level="2", layer="block", role="track", user_name="Track 101-103", assignment="none"),
    ]


LENGTHS = {"OS Switch 1": railroad.BlockLength(2, "OS Switch 1", "Block 4-2", 9.2, 22.6, "timed")}


class Template(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def copy(self, edit=None) -> Path:
        doc = tables.load(tb.TEMPLATE)
        if edit:
            edit(doc.root)
        p = self.tmp / "t.xml"
        p.write_bytes(doc.tobytes())
        return p

    def test_the_committed_template_reads(self) -> None:
        doc = tb.read_template()
        self.assertEqual([tb.section_key(s) for s in tables.elements(doc.root)], list(tb.SECTIONS))
        held = tb.bean_names(doc.root)
        self.assertIn("ISCLOCKRUNNING", held)
        self.assertIn("IQ:AUTO:0001", held)

    def test_the_template_holds_no_bean_of_the_master(self) -> None:
        master = {n for r in D.load() for n in (r["user_name"], r["jmri_name"], r["system_name"]) if n}
        self.assertEqual(set(), tb.bean_names(tb.read_template().root) & master)

    def test_a_missing_section_stops_naming_it(self) -> None:
        p = self.copy(lambda root: root.remove(root.find("memories")))
        with self.assertRaisesRegex(tb.TablesBuildError, "no <memories class=.*> section"):
            tb.read_template(p)

    def test_sections_out_of_order_stop(self) -> None:
        def swap(root):
            m = root.find("memories")
            root.remove(m)
            root.append(m)
        with self.assertRaisesRegex(tb.TablesBuildError, "not exactly"):
            tb.read_template(self.copy(swap))

    def test_what_a_store_writes_stops(self) -> None:
        for edit, what in ((lambda r: r.find("timebase").set("time", "Mon"), "timebase@time"),
                           (lambda r: r.find("memories")[0].set("value", "1"), "memory@value"),
                           (lambda r: ET.SubElement(r, "filehistory"), "filehistory")):
            with self.subTest(what=what), self.assertRaisesRegex(tb.TablesBuildError, what):
                tb.read_template(self.copy(edit))

    def test_a_panel_or_logic_in_the_template_stops(self) -> None:
        def add(root):
            ET.SubElement(root.find("signalmastlogics"), "signalmastlogic", source="Mast 1")
        with self.assertRaisesRegex(tb.TablesBuildError, "Signal Mast Logic or a panel"):
            tb.read_template(self.copy(add))

    def test_a_block_or_mast_in_the_template_stops(self) -> None:
        def add_block(root):
            el = ET.SubElement(root.find("blocks"), "block", systemName="IB99")
            ET.SubElement(el, "systemName").text = "IB99"
        with self.assertRaisesRegex(tb.TablesBuildError, "holds block IB99, but .* come from devices.csv"):
            tb.read_template(self.copy(add_block))

        def add_mast(root):
            el = ET.SubElement(root.find("signalmasts"), "virtualsignalmast")
            ET.SubElement(el, "systemName").text = "IF$vsm:basic:one-low($9)"
        with self.assertRaisesRegex(tb.TablesBuildError, "holds virtualsignalmast"):
            tb.read_template(self.copy(add_mast))

    def test_a_changed_envelope_stops(self) -> None:
        p = self.copy()
        p.write_bytes(p.read_bytes().replace(b'<?xml-stylesheet href="/xml/XSLT/panelfile-5-5-5.xsl"', b"<?xml-stylesheet"))
        with self.assertRaisesRegex(tb.TablesBuildError, "fixed envelope"):
            tb.read_template(p)

    def test_an_unreadable_template_names_the_file(self) -> None:
        with self.assertRaisesRegex(tb.TablesBuildError, "cannot read it"):
            tb.read_template(self.tmp / "none.xml")


class MasterBeans(unittest.TestCase):
    def test_each_kind_lands_in_its_section_with_its_comment(self) -> None:
        doc = tb.base(rows(), lengths=LENGTHS)
        root = doc.root
        sec = {tb.section_key(s): s for s in tables.elements(root)}
        self.assertEqual(["M2S401", "M2S470", "M2S471"], [tables.system_name(e) for e in sec[tb.MQTT_SENSORS]])
        mqtt = sec[tb.MQTT_TURNOUTS].find("turnout")
        self.assertEqual(("FB Switch 1 R", "FB Switch 1 N"), (mqtt.get("sensor1"), mqtt.get("sensor2")))
        self.assertEqual("Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2", mqtt.findtext("comment"))
        alias = sec[tb.LCC_TURNOUTS].find("turnout")
        self.assertEqual("Node: 4 Turnout: 0 | OU: 1 Ports: 1,2", alias.findtext("comment"))   # no DCC group
        heads = {tables.system_name(h): h.findtext("comment") for h in tables.signal_heads(root)}
        self.assertEqual({"IH432": "Node: 4 Signal: 0 | OU: 2 Ports: 1,2,3",
                          "IH:HART:C1:2L": "Brick | Switch 1 | internal, not wired"}, heads)
        self.assertEqual(["IH432", "IH:HART:C1:2L"], list(heads))           # JMRI order: digits before ':'
        masts = {tables.user_name(m): m for m in tables.masts(root)}
        self.assertEqual("virtualsignalmast", masts["Mast 4LA"].tag)
        self.assertEqual("yes", masts["Mast 4LA"].find("unlit").get("allowed"))
        self.assertEqual("no", masts["Mast 2L"].find("unlit").get("allowed"))
        full = tables.blocks(root)[0]
        self.assertEqual(("574.0", "0"), (full.get("length"), full.get("curve")))
        self.assertEqual(["systemName", "userName", "comment", "permissive", "occupancysensor"],
                         [c.tag for c in full])
        self.assertEqual(1, len(tables.blocks(root, full=False)))
        lb = tables.layout_blocks(root)[0]
        self.assertEqual(["systemName", "occupancysensor", "occupiedsense", "trackcolor", "occupiedcolor",
                          "extracolor"], list(lb.attrib))
        self.assertNotIn("Track 101-103", tb.bean_names(root))              # assignment none: no bean

    def test_the_template_settings_stay_first(self) -> None:
        root = tb.base(rows(), lengths=LENGTHS).root
        internal = [s for s in root.findall("sensors") if "Internal" in s.get("class")][0]
        self.assertEqual("defaultInitialState", next(tables.elements(internal)).tag)
        blocks = root.find("blocks")
        self.assertEqual("defaultspeed", next(tables.elements(blocks)).tag)

    def test_a_turnout_without_its_feedback_stops(self) -> None:
        bad = [r for r in rows() if r["user_name"] != "FB Switch 1 R"]
        with self.assertRaisesRegex(tb.TablesBuildError, "Switch 1.*no feedback row FB Switch 1 R"):
            tb.base(bad, lengths=LENGTHS)

    def test_a_block_with_no_length_or_layout_block_stops(self) -> None:
        with self.assertRaisesRegex(tb.TablesBuildError, "OS Switch 1.*no row in block_lengths.csv"):
            tb.base(rows(), lengths={})
        bad = [dict(r, layout_block="") if r["layer"] == "block" else r for r in rows()]
        with self.assertRaisesRegex(tb.TablesBuildError, "no layout_block"):
            tb.base(bad, lengths=LENGTHS)

    def test_a_block_with_two_detectors_stops(self) -> None:
        extra = blank(layer="occupancy", role="os", user_name="BS Switch 1b", assignment="field",
                      system_name="M2S402", jmri_name="M2S402", wiring="Node: 4 Block: 3", blocks="OS Switch 1")
        with self.assertRaisesRegex(tb.TablesBuildError, "detected by 2 occupancy rows"):
            tb.base(rows() + [extra], lengths=LENGTHS)

    def test_an_unknown_bean_stops(self) -> None:
        for row, why in ((blank(layer="sensor", role="panel_status", user_name="Odd", assignment="field",
                                system_name="XS1", jmri_name="XS1", jmri_comment="x"), "no manager section"),
                         (blank(layer="mast", role="home", user_name="Mast 9", assignment="virtual",
                                system_name="IF$dsm:x", jmri_name="IF$dsm:x", jmri_comment="x"), "neither a head mast"),
                         (blank(layer="head", role="head", user_name="Head 9", assignment="virtual",
                                system_name="IH:HART:C1:9", jmri_name="IH:HART:C1:9"), "neither wiring nor")):
            with self.subTest(why=why), self.assertRaisesRegex(tb.TablesBuildError, why):
                tb.base(rows() + [row], lengths=LENGTHS)

    def test_a_duplicate_name_stops(self) -> None:
        twin = dict(rows()[2], user_name="FB Switch 1 X")          # the same system name M2S470 again
        with self.assertRaisesRegex(tb.TablesBuildError, "names given twice: sensor 'M2S470' x2"):
            tb.base(rows() + [twin], lengths=LENGTHS)

    def test_a_master_bean_the_template_holds_too_stops(self) -> None:
        clock = blank(layer="sensor", role="panel_status", user_name="Clock running", assignment="virtual",
                      system_name="ISCLOCKRUNNING", jmri_name="ISCLOCKRUNNING", jmri_comment="x")
        with self.assertRaisesRegex(tb.TablesBuildError, "holds beans the master gives too.*ISCLOCKRUNNING"):
            tb.base(rows() + [clock], lengths=LENGTHS)

    def test_a_bad_master_row_stops_before_any_bean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "devices.csv"
            p.write_text(D.master_text([dict(rows()[0], role="nonsense")]), encoding="utf-8")
            with self.assertRaisesRegex(D.DevicesError, "role 'nonsense'"):
                tb.base(D.load(p), lengths=LENGTHS)

    def test_the_committed_staging_reads_into_a_base(self) -> None:
        root = tb.base().root
        self.assertEqual(45, len(tables.blocks(root)))
        self.assertIsNone(root.find("LayoutEditor"))
        self.assertEqual([], tables.mast_logics(root))


class MissingLogic(unittest.TestCase):
    def test_head_masts_need_a_source_and_virtual_masts_a_mention(self) -> None:
        root = tables.loads(STORE).root
        self.assertEqual([], tb.missing_logic(root))
        box = root.find("signalmastlogics")
        box.remove(box.find("signalmastlogic"))
        self.assertEqual(["Mast 6LB", "Mast 4LA"], tb.missing_logic(root))

    def test_the_committed_tables_miss_none(self) -> None:
        self.assertEqual([], tb.missing_logic(tables.read(paths.REPO_TABLES_XML)))


class Order(unittest.TestCase):
    def test_jmri_order(self) -> None:
        self.assertEqual(["IH432", "IH9990", "IH:HART:C1:2L_Bottom", "IH:HART:C1:2L_Top", "IH:HART:C1:24L"],
                         tb.jmri_order(["IH:HART:C1:24L", "IH9990", "IH:HART:C1:2L_Top", "IH432",
                                        "IH:HART:C1:2L_Bottom"]))
        self.assertEqual(["IS:SML_MODE", "IS:TRACK_POWER", "ISCLOCKRUNNING"],
                         tb.jmri_order(["ISCLOCKRUNNING", "IS:TRACK_POWER", "IS:SML_MODE"]))
        self.assertEqual(["IB24", "IB:AUTO:0001"], tb.jmri_order(["IB:AUTO:0001", "IB24"]))


STORE = b"""<?xml version="1.0" encoding="UTF-8"?>
<layout-config>
  <signalmasts>
    <signalmast class="x">
      <systemName>IF$shsm:basic:one-searchlight(IH432)</systemName>
      <userName>Mast 6LB</userName>
      <properties>
        <property>
          <key>intermediateSignal</key>
          <value class="java.lang.Boolean">true</value>
        </property>
      </properties>
      <unlit allowed="no" />
    </signalmast>
    <virtualsignalmast class="y">
      <systemName>IF$vsm:basic:one-low($1001)</systemName>
      <userName>Mast 4LA</userName>
      <unlit allowed="yes" />
    </virtualsignalmast>
  </signalmasts>
  <signalmastlogics>
    <logicDelay>500</logicDelay>
    <signalmastlogic source="Mast 6LB">
      <sourceSignalMast>Mast 6LB</sourceSignalMast>
      <destinationMast destination="Mast 4LA">
        <destinationSignalMast>Mast 4LA</destinationSignalMast>
        <enabled>yes</enabled>
      </destinationMast>
    </signalmastlogic>
  </signalmastlogics>
  <filehistory />
  <!--Written by JMRI-->
</layout-config>
"""


class Discovered(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_a_store_round_trips_through_the_file(self) -> None:
        store = tables.loads(STORE).root
        doc = tb.discovered_from_store(store)
        path = self.tmp / "d.xml"
        self.assertTrue(tb.write_discovered(doc, path))
        self.assertFalse(tb.write_discovered(doc, path))                 # unchanged bytes: not written again
        logics, props = tb.read_discovered(path)
        self.assertEqual(["Mast 6LB"], [x.get("source") for x in logics])
        self.assertEqual(["Mast 6LB"], list(props))
        target = tables.loads(STORE).root
        for m in tables.masts(target):
            p = m.find("properties")
            if p is not None:
                m.remove(p)
        box = target.find("signalmastlogics")
        box.remove(box.find("signalmastlogic"))
        tb.merge_discovered(target, logics, props)
        mast = tables.masts(target)[0]
        self.assertEqual(["systemName", "userName", "properties", "unlit"], [c.tag for c in tables.elements(mast)])
        self.assertEqual(["logicDelay", "signalmastlogic"], [c.tag for c in tables.elements(box)])

    def test_a_store_without_logic_stops(self) -> None:
        root = tables.loads(STORE).root
        box = root.find("signalmastlogics")
        box.remove(box.find("signalmastlogic"))
        with self.assertRaisesRegex(tb.TablesBuildError, "no Signal Mast Logic"):
            tb.discovered_from_store(root)

    def test_logic_naming_a_mast_the_tables_lack_stops(self) -> None:
        logics, props = tb.read_discovered_root(tb.discovered_from_store(tables.loads(STORE).root), "x")
        target = tables.loads(STORE).root
        box = target.find("signalmastlogics")
        box.remove(box.find("signalmastlogic"))
        sm = target.find("signalmasts")
        sm.remove(sm.find("virtualsignalmast"))
        with self.assertRaisesRegex(tb.TablesBuildError, "names masts the tables do not hold \\(Mast 4LA\\)"):
            tb.merge_discovered(target, logics, props)

    def test_a_bad_discovered_file_stops(self) -> None:
        for body, why in (("<other />", "not <discovered-sml>"),
                          ("<discovered-sml><signalmastlogic /></discovered-sml>", "source ''"),
                          ("<discovered-sml><x /></discovered-sml>", "neither signalmastlogic"),
                          ("<discovered-sml><mastproperties mast='M' /></discovered-sml>", "exactly one")):
            with self.subTest(why=why), self.assertRaisesRegex(tb.TablesBuildError, why):
                tb.read_discovered_root(ET.fromstring(body), "d.xml")
        with self.assertRaisesRegex(tb.TablesBuildError, "cannot read it"):
            tb.read_discovered(self.tmp / "none.xml")

    def test_the_committed_file_names_only_masts_of_the_tables(self) -> None:
        logics, props = tb.read_discovered()
        masts = {tables.user_name(m) for m in tables.masts(tables.read(paths.REPO_TABLES_XML))}
        named = {x.get("source") for x in logics} | {d.get("destination") for x in logics
                                                     for d in x.findall("destinationMast")}
        self.assertEqual(set(), (named | set(props)) - masts)


class Envelope(unittest.TestCase):
    def test_strip_takes_out_what_a_store_writes(self) -> None:
        root = tables.loads(STORE.replace(b"<signalmasts>", b'<timebase time="x" /><memories><memory value="1">'
                                          b"<systemName>IM1</systemName></memory></memories><signalmasts>")).root
        self.assertEqual(["filehistory", "the 'Written by' comment", "timebase@time", "memory@value"],
                         tb.envelope_items(root))
        tb.strip_envelope(root)
        self.assertEqual([], tb.envelope_items(root))

    def test_the_generated_file_has_the_fixed_envelope(self) -> None:
        doc = tables.load(paths.REPO_TABLES_XML)
        self.assertEqual((tb.PROLOG, tb.EPILOG), (doc.prolog, doc.epilog))
        self.assertEqual([], tb.envelope_items(doc.root))


if __name__ == "__main__":
    unittest.main()

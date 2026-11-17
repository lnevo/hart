"""hartlib.parked: the build splits the parked features out of the tables, the check holds both files to it, and a
restore puts them back."""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import parked  # noqa: E402

TABLES = """<layout-config>
  <sensors class="jmri.jmrix.internal.configurexml.InternalSensorManagerXml">
    <sensor><systemName>ISNX:100L</systemName><userName>NX Mast 2L</userName></sensor>
    <sensor><systemName>IS:DSMT:1</systemName><userName>MoveToTrack_Barn_stored</userName></sensor>
    <sensor><systemName>IS:IY:AUTO:0001:forward</systemName><userName>IY:AUTO:0001:forward</userName></sensor>
    <sensor><systemName>IS1:LEVER</systemName><userName>CTC 3 lever</userName></sensor>
    <sensor><systemName>IS:FLEETING</systemName><userName>CTC fleeting</userName></sensor>
    <sensor><systemName>IS:SML_MODE</systemName><userName>SML Mode</userName></sensor>
  </sensors>
  <memories class="m">
    <memory><systemName>IMIS:ISMEM:versionNo</systemName></memory>
    <memory><systemName>IMCURRENTTIME</systemName></memory>
  </memories>
  <sections class="s"><section systemName="IY:AUTO:0001" userName="Mast 2L:Mast 6LB"/></sections>
  <transits class="t"><transit systemName="IZ1"/></transits>
  <signalmastlogics class="l">
    <signalmastlogic source="Mast 2L">
      <destinationMast destination="Mast 6LB"><associatedSection>Mast 2L:Mast 6LB</associatedSection></destinationMast>
    </signalmastlogic>
  </signalmastlogics>
  <logixs class="x">
    <logix><systemName>IX:DSLX:1</systemName></logix>
    <logix><systemName>IX:CTC:REVDEF</systemName></logix>
  </logixs>
  <conditionals class="c">
    <conditional systemName="IX:DSLX:1C1"><systemName>IX:DSLX:1C1</systemName></conditional>
    <conditional systemName="IX:CTC:REVDEF:C1"><systemName>IX:CTC:REVDEF:C1</systemName></conditional>
  </conditionals>
  <LogixNGs class="n">
    <LogixNG><systemName>IQ:AUTO:0001</systemName><ConditionalNGs>
      <systemName>IQC:AUTO:0001</systemName><systemName>IQC:AUTO:0002</systemName><systemName>IQC:AUTO:0003</systemName>
    </ConditionalNGs></LogixNG>
  </LogixNGs>
  <LogixNGConditionalNGs class="g">
    <ConditionalNG><systemName>IQC:AUTO:0001</systemName><Socket><systemName>IQDA:AUTO:0001</systemName></Socket></ConditionalNG>
    <ConditionalNG><systemName>IQC:AUTO:0002</systemName><Socket><systemName>IQDA:AUTO:0002</systemName></Socket></ConditionalNG>
    <ConditionalNG><systemName>IQC:AUTO:0003</systemName><Socket><systemName>IQDA:AUTO:0003</systemName></Socket></ConditionalNG>
  </LogixNGConditionalNGs>
  <LogixNGDigitalActions class="a">
    <A><systemName>IQDA:AUTO:0001</systemName></A>
    <A><systemName>IQDA:AUTO:0002</systemName></A>
    <A><systemName>IQDA:AUTO:0003</systemName></A>
  </LogixNGDigitalActions>
  <ctcdata class="ctc"><ctcCodeButtonData/></ctcdata>
  <entryexitpairs class="e"><layoutPanel name="HART Railroad"/></entryexitpairs>
  <paneleditor class="p" name="USS CTC"><sensoricon sensor="IS1:LEVER"/></paneleditor>
  <LayoutEditor class="le" name="HART Railroad">
    <layoutturnout ident="TO1"><sensorA>NX Mast 2L</sensorA><signalAMast>Mast 2L</signalAMast></layoutturnout>
    <positionablepoint ident="A1" eastboundsensor="NX Mast 2L" eastboundsignalmast="Mast 2L"/>
    <sensoricon sensor="MoveToTrack_Barn_stored"/>
    <sensoricon sensor="SML Mode"/>
  </LayoutEditor>
  <LayoutEditor class="le" name="Dispatcher System"><sensoricon sensor="MoveToTrack_Barn_stored"/></LayoutEditor>
</layout-config>"""


def canon(el: ET.Element) -> list[str]:
    return sorted(ET.canonicalize(ET.tostring(e, encoding="unicode"), strip_text=True) for e in el)


class Parked(unittest.TestCase):
    def setUp(self):
        self.root = ET.fromstring(TABLES)
        self.doc = parked.split(self.root, parked.FEATURES)
        self.doc.set("source", "3bd3ac64")

    def test_split_leaves_only_the_active_parts(self):
        self.assertEqual([s.findtext("systemName") for s in self.root.iter("sensor")], ["IS:SML_MODE"])
        self.assertEqual([m.findtext("systemName") for m in self.root.iter("memory")], ["IMCURRENTTIME"])
        tags = [c.tag for c in self.root]
        for gone in ("sections", "transits", "ctcdata", "entryexitpairs", "paneleditor", "logixs", "conditionals"):
            self.assertNotIn(gone, tags)
        self.assertEqual([p.get("name") for p in self.root.iter("LayoutEditor")], ["HART Railroad"])
        self.assertEqual([c.text for c in self.root.find("LogixNGs/LogixNG/ConditionalNGs")], ["IQC:AUTO:0001"])
        self.assertEqual(len(self.root.find("LogixNGDigitalActions")), 1)
        panel = self.root.find("LayoutEditor")
        self.assertIsNone(panel.find("layoutturnout/sensorA"))
        self.assertIsNone(panel.find("positionablepoint").get("eastboundsensor"))
        self.assertEqual([i.get("sensor") for i in panel.iter("sensoricon")], ["SML Mode"])
        self.assertIsNone(self.root.find(".//associatedSection"))
        self.assertEqual([f.get("name") for f in self.doc], ["nx", "dispatcher", "uss"])

    def test_check_passes_and_catches_a_leftover(self):
        # the fixture's sensor counts are below the real ones: only that complaint is expected
        bad = [b for b in parked.check(self.root, self.doc, parked.FEATURES) if "sensors, expected" not in b]
        self.assertEqual(bad, [])
        self.root.find("sensors").append(ET.fromstring(
            "<sensor><systemName>IS2:LEVER</systemName><userName>CTC 1 lever</userName></sensor>"))
        self.assertTrue(any("still holds parked uss" in b for b in parked.check(self.root, self.doc, parked.FEATURES)))

    def test_a_reference_to_a_parked_name_is_caught(self):
        self.root.find("LayoutEditor").append(ET.fromstring('<sensoricon sensor="CTC 3 lever"/>'))
        self.assertTrue(any("refers to" in b or "still holds" in b
                            for b in parked.check(self.root, self.doc, parked.FEATURES)))

    def test_restore_puts_everything_back(self):
        back = parked.restore(self.root, self.doc)
        original = ET.fromstring(TABLES)
        for tag in ("sensors", "sections", "transits", "ctcdata", "entryexitpairs", "logixs", "conditionals"):
            self.assertEqual(canon(back.find(tag)), canon(original.find(tag)), tag)
        panel = next(p for p in back.iter("LayoutEditor") if p.get("name") == "HART Railroad")
        self.assertEqual(panel.findtext("layoutturnout/sensorA"), "NX Mast 2L")
        self.assertEqual(panel.find("positionablepoint").get("eastboundsensor"), "NX Mast 2L")
        self.assertEqual(back.findtext(".//associatedSection"), "Mast 2L:Mast 6LB")
        self.assertEqual(len(back.find("LogixNGs/LogixNG/ConditionalNGs")), 3)

    def test_parked_in_reads_tables_as_they_are(self):
        self.assertEqual(parked.parked_in(self.root, parked.FEATURES), frozenset(parked.FEATURES))
        self.assertEqual(parked.parked_in(ET.fromstring(TABLES), parked.FEATURES), frozenset())

    def test_the_parked_file_records_its_source_commit(self):
        del self.doc.attrib["source"]
        self.assertTrue(any("source" in b for b in parked.check(self.root, self.doc, parked.FEATURES)))
        with self.assertRaises(parked.ParkError):
            parked.to_bytes(self.doc)
        data = parked.to_bytes(self.doc, "3bd3ac64")
        self.assertIn(b"at commit 3bd3ac64", data)
        self.assertEqual(ET.fromstring(data).get("source"), "3bd3ac64")

    def test_a_conditional_belongs_to_its_own_logix_only(self):
        self.assertTrue(parked._conditional_of("IX:DSLX:1C1", "IX:DSLX:1"))
        self.assertTrue(parked._conditional_of("IX:DSLX:1C12", "IX:DSLX:1"))
        self.assertFalse(parked._conditional_of("IX:DSLX:10C1", "IX:DSLX:1"))
        self.assertFalse(parked._conditional_of("IX:DSLX:1", "IX:DSLX:1"))
        self.assertTrue(parked._conditional_of("IX:CTC:REVDEF:C1", "IX:CTC:REVDEF"))
        self.assertFalse(parked._conditional_of("IX:CTC:REVDEF2:C1", "IX:CTC:REVDEF"))

    def test_unknown_feature_stops(self):
        with self.assertRaises(parked.ParkError):
            parked.split(ET.fromstring(TABLES), {"signals"})


if __name__ == "__main__":
    unittest.main()

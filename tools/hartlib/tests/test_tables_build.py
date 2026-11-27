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
from hartlib import (devices as D, jmri_bean, level_devices, paths, tables, tables_build as tb,  # noqa: E402
                     tables_normal, tables_roundtrip, tables_sections as ts, tables_sml)


def blank(**cells) -> dict:
    row = {c: "" for c in D.COLUMNS}
    row.update({"level": "1", "description": "A device.", **cells})
    return row


def rows() -> list[dict]:
    """A small staging: one turnout with its alias and feedback, a block and its detector, a wired and a virtual
    head, a head mast and a hidden mast."""
    return [
        blank(layer="turnout", role="turnout", id="switch:1", user_name="Switch 1", assignment="field", system_name="M2T408",
              jmri_name="M2T408", dcc="100", wiring="Node: 4 Turnout: 0 | OU: 1 Ports: 1,2"),
        blank(layer="turnout", role="lcc_alias", id="dcc:1", user_name="DCC Switch 1", assignment="field", system_name="MTT100",
              jmri_name="MTT100", dcc="100", wiring="Node: 4 Turnout: 0 | OU: 1 Ports: 1,2"),
        blank(layer="fb", role="fb", id="fb:1:N", user_name="FB Switch 1 N", assignment="field", system_name="M2S470",
              jmri_name="M2S470", wiring="Node: 4 Sensor: 3 | IN: 1 Ports: 1"),
        blank(layer="fb", role="fb", id="fb:1:R", user_name="FB Switch 1 R", assignment="field", system_name="M2S471",
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


LENGTHS = {"OS Switch 1": 9.2}       # block name -> operating length in inches (block_lengths.operating_lengths)


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
        got = [tb.section_key(s) for s in tables.elements(doc.root)]
        # the known sections in order; a split may keep an extra one the owner made (a Route table, audio)
        self.assertEqual([k for k in got if k in tb.SECTIONS], list(tb.SECTIONS))
        held = tb.bean_names(doc.root)
        self.assertIn("ISCLOCKRUNNING", held)
        self.assertIn("IQ:AUTO:0001", held)

    def test_the_template_holds_no_bean_of_the_master(self) -> None:
        master = {n for r in D.load() for n in (r.user_name, r.jmri_name, r.system_name) if n}
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
        with self.assertRaisesRegex(tb.TablesBuildError, "holds block IB99, but .* come from the device master"):
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
        self.assertEqual(["M2S401", "M2S470", "M2S471"], [tables.system_name(e) for e in sec[ts.MQTT_SENSORS]])
        mqtt = sec[ts.MQTT_TURNOUTS].find("turnout")
        self.assertEqual(("FB Switch 1 R", "FB Switch 1 N"), (mqtt.get("sensor1"), mqtt.get("sensor2")))
        self.assertEqual("Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2", mqtt.findtext("comment"))
        alias = sec[ts.LCC_TURNOUTS].find("turnout")
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
        # the plan length (9.2 in), not the measured one (22.6 in): JMRI takes plan_in on every level (step 5 part 2)
        self.assertEqual(("233.7", "0"), (full.get("length"), full.get("curve")))
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
        with self.assertRaisesRegex(tb.TablesBuildError, "Switch 1.*no feedback bean fb:1:R"):
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

    def test_a_level_less_device_lands_as_its_bean(self) -> None:
        """A device added in PanelPro (no level, its Store bean in jmri_bean) goes into tables.xml as it was."""
        store = ET.fromstring('<turnout feedback="MONITORING" inverted="false"><systemName>MTT999</systemName>'
                              "<userName>Test 999</userName></turnout>")
        row = blank(level="", layer="turnout", user_name="Test 999", assignment="field", system_name="MTT999",
                    jmri_name="MTT999")
        row["jmri_bean"] = jmri_bean.bean_json([(ts.LCC_TURNOUTS, store)], row)
        root = tb.base(rows() + [row], lengths=LENGTHS).root
        got = next(el for el in root.iter("turnout") if tables.system_name(el) == "MTT999")
        self.assertEqual(("MONITORING", "Test 999", None), (got.get("feedback"), tables.user_name(got), got.get("sensor1")))

    def test_a_level_less_bean_a_level_row_makes_too_stops(self) -> None:
        store = ET.fromstring("<turnout><systemName>MTT100</systemName></turnout>")
        row = blank(level="", layer="turnout", user_name="Test", assignment="field", system_name="MTT100",
                    jmri_name="MTT100")
        row["jmri_bean"] = jmri_bean.bean_json([(ts.LCC_TURNOUTS, store)], row)
        with self.assertRaisesRegex(tb.TablesBuildError, "a level row makes too \\(MTT100\\)"):
            tb.base(rows() + [row], lengths=LENGTHS)

    def test_a_bad_master_row_stops_before_any_bean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "devices.csv"
            p.write_text(D.master_text([dict(rows()[0], role="nonsense")]), encoding="utf-8")
            with self.assertRaisesRegex(D.DevicesError, "role 'nonsense'"):
                tb.base([r.cells() for r in D.load(p)], lengths=LENGTHS)

    def test_the_committed_master_reads_into_a_base(self) -> None:
        """Every level's blocks (naming-layers step 11): staging's 45 and its 14 parts (owner, 2026-11-20), and main
        and upper's 120; and the startup LogixNG of the main and upper virtual detectors and turnouts."""
        root = tb.base().root
        self.assertEqual(59 + 120, len(tables.blocks(root)))
        self.assertIsNone(root.find("LayoutEditor"))
        self.assertEqual([], tables.mast_logics(root))
        self.assertEqual(97, len(level_devices.clear_sensors(root)))
        self.assertEqual(39, len(level_devices.turnout_states(root)))


class MasterBeansByAssignment(unittest.TestCase):
    """What master_beans makes of a row by its assignment (field is MasterBeans' fixture), pinned before the builder
    merge sends every level through it (ADR-033 step 1)."""

    def section(self, root: ET.Element, key: tuple) -> list[str]:
        return [tables.system_name(e) for e in tables.elements({tb.section_key(s): s
                                                                for s in tables.elements(root)}[key])]

    def test_a_spare_detector_is_a_sensor_no_block_takes(self) -> None:
        spare = blank(layer="occupancy", role="spare", user_name="unused Block 2-2", assignment="spare",
                      system_name="M2S201", jmri_name="M2S201", wiring="Node: 2 Block: 2")
        root = tb.base(rows() + [spare], lengths=LENGTHS).root
        self.assertIn("M2S201", self.section(root, ts.MQTT_SENSORS))
        self.assertEqual({"BS Switch 1"}, {b.findtext("occupancysensor") for b in tables.blocks(root)})

    def test_a_virtual_part_with_a_jmri_block_takes_its_blocks_sensor(self) -> None:
        part = blank(layer="block", role="part", user_name="Track 1-3 at 1", assignment="virtual",
                     jmri_name="IB:AUTO:0052", layout_block="ILB52", part_of="OS Switch 1",
                     jmri_comment="Part of OS Switch 1")
        lengths = dict(LENGTHS, **{"Track 1-3 at 1": 3.0})
        root = tb.base(rows() + [part], lengths=lengths).root
        full = next(b for b in tables.blocks(root) if tables.system_name(b) == "IB:AUTO:0052")
        self.assertEqual(("76.2", "BS Switch 1"), (full.get("length"), full.findtext("occupancysensor")))
        lb = next(b for b in tables.layout_blocks(root) if tables.system_name(b) == "ILB52")
        self.assertEqual(("Track 1-3 at 1", "BS Switch 1"), (tables.user_name(lb), lb.get("occupancysensor")))

    def test_a_row_with_assignment_none_gives_no_bean(self) -> None:
        part = blank(layer="block", role="part", user_name="Track 1-3 at 3", assignment="none", part_of="OS Switch 1")
        root = tb.base(rows() + [part], lengths=LENGTHS).root
        self.assertNotIn("Track 1-3 at 3", tb.bean_names(root))

    def test_a_virtual_panel_lamp_is_an_internal_sensor(self) -> None:
        lamp = blank(layer="sensor", role="panel_status", user_name="Test Lamp", assignment="virtual",
                     system_name="IS:TEST_LAMP", jmri_name="IS:TEST_LAMP", jmri_comment="Test lamp; ACTIVE=on")
        root = tb.base(rows() + [lamp], lengths=LENGTHS).root
        self.assertIn("IS:TEST_LAMP", self.section(root, ts.INTERNAL_SENSORS))
        self.assertNotIn("IS:TEST_LAMP", self.section(root, ts.MQTT_SENSORS))

    def test_a_main_or_upper_row_gives_its_bean_in_the_base(self) -> None:
        """Every level's rows give beans (naming-layers step 11: GENERATED_LEVELS went), a virtual one on its
        jmri_name with its row's bean_comment."""
        level = [blank(level="2", layer="turnout", role="turnout", id="switch:101", user_name="Switch 101",
                       assignment="virtual", system_name="M2T3408", jmri_name="IT:HART:C3:101", bean_comment="t"),
                 blank(level="2", layer="occupancy", role="track", user_name="BS 101-103", assignment="virtual",
                       jmri_name="IS:HART:C3:B:101-103", blocks="Track 101-103", bean_comment="s"),
                 blank(level="3", layer="mast", role="home", user_name="Mast 201R", assignment="virtual",
                       jmri_name="IF$shsm:basic:one-searchlight(IH:HART:C3:201R)", bean_comment="m"),
                 blank(level="3", layer="head", role="head", user_name="Head 201R", assignment="virtual",
                       jmri_name="IH:HART:C3:201R", bean_comment="h")]
        root = tb.base(rows() + level, lengths=LENGTHS).root
        self.assertLessEqual({n for r in level for n in (r["user_name"], r["jmri_name"])}, tb.bean_names(root))
        self.assertNotIn("M2T3408", tb.bean_names(root))         # a virtual turnout's planned name is a draft
        self.assertEqual("t", next(t.findtext("comment") for t in tables.turnouts(root)
                                   if tables.user_name(t) == "Switch 101"))


def main_rows() -> list[dict]:
    """A small main level as build_device_map.py writes it: a virtual switch with its planned LCC alias and two
    feedback rows with assignment none, an OS block and a part of it with their detector (start inactive), and a
    helix block with assignment none whose detector binds staging's helix block."""
    lvl = dict(level="2", assignment="virtual")
    return [
        blank(**lvl, layer="turnout", role="turnout", id="switch:101", user_name="Switch 101", system_name="M2T3408",
              jmri_name="IT:HART:C3:101", start="closed", bean_comment="Main and upper level, internal"),
        blank(**lvl, layer="turnout", role="lcc_alias", id="dcc:101", user_name="DCC Switch 101", system_name="MTT120",
              jmri_name="IT:HART:C3:101", wiring="Node: 34 Turnout: 0"),
        blank(level="2", assignment="none", layer="fb", role="fb", id="fb:101:N", user_name="FB Switch 101 N",
              system_name="M2S3467"),
        blank(level="2", assignment="none", layer="fb", role="fb", id="fb:101:R", user_name="FB Switch 101 R",
              system_name="M2S3468"),
        blank(**lvl, layer="block", role="os", id="os:101", user_name="OS Switch 101", jmri_name="IB:C3:0001",
              layout_block="ILB1001", jmri_comment="Peninsula", bean_comment="Main and upper level, internal"),
        blank(**lvl, layer="block", role="part", id="block:101AB-103AA", user_name="Track 101-103",
              jmri_name="IB:C3:0075", layout_block="ILB1075", part_of="OS Switch 101",
              bean_comment="Main and upper level, internal"),
        blank(**lvl, layer="occupancy", role="os", id="det:os:101", user_name="BS Switch 101",
              jmri_name="IS:HART:C3:B:OS101", blocks="OS Switch 101", start="inactive",
              bean_comment="Main and upper level occupancy, virtual"),
        blank(level="2", assignment="none", layer="block", role="helix", id="block:131AA-helix",
              user_name="Track Helix Outer", jmri_comment="CP 127"),
        blank(**lvl, layer="occupancy", role="helix", id="det:block:131AA-helix", user_name="BS Helix Outer",
              system_name="M2S4101", jmri_name="IS:HART:C3:B:Helix_Outer", blocks="Track Helix Outer",
              start="inactive", bean_comment="Main and upper level occupancy, virtual"),
    ]


STAGING_HELIX = blank(layer="block", role="helix", id="block:39B-helix", user_name="Track Helix Outer",
                      assignment="field", system_name="IB23", jmri_name="IB23", layout_block="ILB76",
                      jmri_comment="Helix track, outer")
ALL_LENGTHS = dict(LENGTHS, **{n: 10.0 for n in ("OS Switch 101", "Track 101-103", "Track Helix Outer")})


class ShapeByColumn(unittest.TestCase):
    """Each rule master_beans shapes a bean by (naming-layers step 10, builder merge step 4), on a small main level
    run through it with staging (levels 1 and 2, as base() runs every level) and on staging alone."""

    def beans(self, extra=(), levels=("1", "2")) -> dict:
        return tb.master_beans(rows() + [STAGING_HELIX] + main_rows() + list(extra), ALL_LENGTHS, levels)

    def named(self, beans: dict, key: tuple) -> dict[str, ET.Element]:
        return {tables.system_name(e): e for e in beans.get(key, [])}

    def test_a_field_row_is_its_system_name_and_any_other_its_jmri_name(self) -> None:
        self.assertEqual("M2T1308", tb.bean_name(blank(layer="turnout", assignment="field", system_name="M2T1308",
                                                       jmri_name="Switch 7")))
        # any other field row is its jmri_name, the device tables.xml uses; system_name may be a draft (ADR-028)
        self.assertEqual("IS:X", tb.bean_name(blank(layer="occupancy", assignment="field", system_name="M2S4101",
                                                    jmri_name="IS:X")))
        self.assertEqual("IT:HART:C3:101", tb.bean_name(main_rows()[0]))      # system_name is the planned M2T3408
        turnouts = self.named(self.beans(), ts.INTERNAL_TURNOUTS)
        self.assertEqual(["IT:HART:C3:101"], list(turnouts))
        self.assertNotIn("M2T3408", self.named(self.beans(), ts.MQTT_TURNOUTS))

    def test_feedback_is_twosensor_on_two_fb_beans_and_direct_on_none(self) -> None:
        beans = self.beans()
        staging = self.named(beans, ts.MQTT_TURNOUTS)["M2T408"]
        self.assertEqual(("TWOSENSOR", "FB Switch 1 R", "FB Switch 1 N"),
                         (staging.get("feedback"), staging.get("sensor1"), staging.get("sensor2")))
        main = self.named(beans, ts.INTERNAL_TURNOUTS)["IT:HART:C3:101"]
        self.assertEqual({"feedback": "DIRECT", "inverted": "false", "automate": "Off"}, dict(main.attrib))
        one = [dict(r, assignment="virtual", jmri_name="IS:HART:C3:FB101N", jmri_comment="x")
               if r["id"] == "fb:101:N" else r for r in main_rows()]
        with self.assertRaisesRegex(tb.TablesBuildError, "Switch 101'.*no feedback bean fb:101:R"):
            tb.master_beans(one, ALL_LENGTHS, ("2",))

    def test_a_field_turnout_with_no_feedback_beans_stops(self) -> None:
        """Staging must match exactly: only a virtual turnout is DIRECT."""
        for gone in ("none", "drop"):
            with self.subTest(gone=gone):
                bad = [r if r["layer"] != "fb" else dict(r, assignment="none") for r in rows()
                       if gone == "none" or r["layer"] != "fb"]
                with self.assertRaisesRegex(tb.TablesBuildError, "'Switch 1'.*no feedback bean fb:1:R, fb:1:N"):
                    tb.master_beans(bad, LENGTHS)

    def test_an_alias_whose_turnout_row_is_missing_or_gives_no_bean_stops(self) -> None:
        gone = [r for r in main_rows() if r["id"] != "switch:101"]
        with self.assertRaisesRegex(tb.TablesBuildError, "DCC Switch 101'.*no turnout row switch:101 on level 2"):
            tb.master_beans(gone, ALL_LENGTHS, ("2",))
        none = [dict(r, assignment="none") if r["id"] == "switch:101" else r for r in main_rows()]
        with self.assertRaisesRegex(tb.TablesBuildError, "DCC Switch 101'.*switch:101, whose assignment is none"):
            tb.master_beans(none, ALL_LENGTHS, ("2",))

    def test_a_detector_binds_only_its_own_levels_block_but_a_helix_one(self) -> None:
        """A main detector naming a block a staging block shares the name of does not bind it; a helix one does."""
        twin = blank(level="2", layer="occupancy", role="os", id="det:os:1", user_name="BS Twin",
                     assignment="virtual", jmri_name="IS:HART:C3:B:Twin", blocks="OS Switch 1", start="inactive",
                     bean_comment="x")
        beans = self.beans([twin])
        full = {tables.system_name(b): b.findtext("occupancysensor") for b in beans[tb.BLOCKS]}
        self.assertEqual(("BS Switch 1", "BS Helix Outer"), (full["IB:AUTO:0033"], full["IB23"]))

    def test_feedback_rows_are_found_on_the_turnouts_own_level(self) -> None:
        """A main switch numbered like a staging one would not take staging's feedback rows."""
        twin = [dict(r, id=r["id"].replace("101", "1")) if r["layer"] in ("turnout", "fb") else r for r in main_rows()]
        main = self.named(tb.master_beans(rows() + twin, ALL_LENGTHS, ("1", "2")), ts.INTERNAL_TURNOUTS)
        self.assertEqual("DIRECT", main["IT:HART:C3:101"].get("feedback"))

    def test_an_lcc_alias_naming_its_turnouts_bean_gives_none(self) -> None:
        beans = self.beans()
        self.assertEqual(1, sum(1 for e in beans[ts.INTERNAL_TURNOUTS] if tables.system_name(e) == "IT:HART:C3:101"))
        self.assertIn("MTT100", self.named(beans, ts.LCC_TURNOUTS))           # staging's alias is a bean of its own
        own = [dict(r, jmri_name="IT:HART:C3:DCC101") if r["id"] == "dcc:101" else r for r in main_rows()]
        self.assertIn("IT:HART:C3:DCC101", self.named(tb.master_beans(own, ALL_LENGTHS, ("2",)), ts.INTERNAL_TURNOUTS))

    def test_a_turnout_with_no_switch_id_stops(self) -> None:
        bad = [dict(r, id="") if r["id"] == "switch:101" else r for r in main_rows()]
        with self.assertRaisesRegex(tb.TablesBuildError, "Switch 101'.*id '' is not switch:<n>"):
            tb.master_beans(bad, ALL_LENGTHS, ("2",))

    def test_the_comment_is_the_bean_comment_where_set(self) -> None:
        beans = self.beans()
        self.assertEqual("Main and upper level, internal",
                         self.named(beans, ts.INTERNAL_TURNOUTS)["IT:HART:C3:101"].findtext("comment"))
        full = {tables.system_name(b): b for b in beans[tb.BLOCKS]}
        self.assertEqual("Main and upper level, internal", full["IB:C3:0001"].findtext("comment"))   # not "Peninsula"
        self.assertEqual("Brick CP, Switch 1", full["IB:AUTO:0033"].findtext("comment"))           # wiring columns
        self.assertEqual("x", tb.row_comment(blank(layer="sensor", bean_comment="x", jmri_comment="y")))

    def test_a_block_gives_three_beans_and_a_part_its_blocks_sensor(self) -> None:
        beans = self.beans()
        names = [tables.system_name(b) for b in beans[("blocks-names",) + tb.BLOCKS]]
        self.assertIn("IB:C3:0001", names)
        full = {tables.system_name(b): b for b in beans[tb.BLOCKS]}
        self.assertEqual(("254.0", "BS Switch 101"), (full["IB:C3:0075"].get("length"),
                                                      full["IB:C3:0075"].findtext("occupancysensor")))
        lbs = {tables.system_name(b): b for b in beans[tb.LAYOUT_BLOCKS]}
        self.assertEqual("BS Switch 101", lbs["ILB1075"].get("occupancysensor"))

    def test_a_helix_block_is_staging_s_bean_on_the_main_or_upper_sensor(self) -> None:
        beans = self.beans()
        full = [b for b in beans[tb.BLOCKS] if tables.user_name(b) == "Track Helix Outer"]
        self.assertEqual([("IB23", "BS Helix Outer")], [(tables.system_name(b), b.findtext("occupancysensor"))
                                                        for b in full])
        alone = tb.master_beans(rows() + [STAGING_HELIX] + main_rows(), ALL_LENGTHS, ("1",))      # staging alone
        full = [b for b in alone[tb.BLOCKS] if tables.user_name(b) == "Track Helix Outer"]
        self.assertEqual([None], [b.find("occupancysensor") for b in full])
        self.assertNotIn(tb.START_ACTIONS, alone)

    def test_a_virtual_row_with_a_start_is_set_when_the_tables_load(self) -> None:
        actions = self.beans()[tb.START_ACTIONS]
        got = [(a.tag, a.findtext("systemName"), a.findtext("namedBean/name"), a.findtext("state/enum"))
               for a in actions]
        self.assertEqual([("ActionSensor", "IQDA$HART:C3:B:Helix_Outer", "IS:HART:C3:B:Helix_Outer", "Inactive"),
                          ("ActionSensor", "IQDA$HART:C3:B:OS101", "IS:HART:C3:B:OS101", "Inactive"),
                          ("ActionTurnout", "IQDA$HART:C3:T:101", "IT:HART:C3:101", "Closed")], got)
        self.assertEqual(["MaleSocket"], [c.tag for c in actions[0]][-1:])

    def test_a_start_on_a_field_row_or_a_name_with_no_action_stops(self) -> None:
        field = [dict(r, start="closed") if r["user_name"] == "Switch 1" else r for r in rows()]
        with self.assertRaisesRegex(tb.TablesBuildError, "Switch 1'.*start 'closed' on a field turnout row"):
            tb.master_beans(field, LENGTHS)
        odd = [dict(r, jmri_name="IT:ODD:101") if r["id"] in ("switch:101", "dcc:101") else r for r in main_rows()]
        with self.assertRaisesRegex(tb.TablesBuildError, "not a main or upper virtual turnout"):
            tb.master_beans(odd, ALL_LENGTHS, ("2",))

    def test_base_wraps_the_startup_actions_in_the_startup_logixng(self) -> None:
        """base() puts the startup LogixNG around master_beans' actions (start_logixng, naming-layers step 11): its
        DigitalMany's sockets A1, A2, ... name the actions in their order, and level_devices reads them back."""
        root = tb.base(rows() + [STAGING_HELIX] + main_rows(), lengths=ALL_LENGTHS).root
        self.assertEqual(["IS:HART:C3:B:Helix_Outer", "IS:HART:C3:B:OS101"], level_devices.clear_sensors(root))
        self.assertEqual({"IT:HART:C3:101": "Closed"}, level_devices.turnout_states(root))
        many = next(e for e in root.find("LogixNGDigitalActions") if e.tag == "DigitalMany")
        self.assertEqual([("A1", "IQDA$HART:C3:B:Helix_Outer"), ("A2", "IQDA$HART:C3:B:OS101"),
                          ("A3", "IQDA$HART:C3:T:101")],
                         [(s.findtext("socketName"), s.findtext("systemName")) for s in many.find("Actions")])
        lx = [e for e in root.find("LogixNGs") if e.tag == "LogixNG"]
        self.assertEqual(level_devices.CLEAR_LOGIXNG, tables.system_name(lx[-1]))     # after the template's
        self.assertIsNone(tb.base(rows(), lengths=LENGTHS).root.find(
            f"LogixNGs/LogixNG[systemName='{level_devices.CLEAR_LOGIXNG}']"))         # no start: no LogixNG

    def test_level_turnouts_are_the_rows_whatever_their_bean(self) -> None:
        """The main and upper turnouts by their rows (the desk checks pick plants by them): an LCC alias, a feedback
        row and a staging turnout are not one; a turnout swapped to a field name still is."""
        got = tb.level_turnouts(rows() + main_rows())
        self.assertEqual({"Switch 101": "IT:HART:C3:101"}, got)
        swapped = [dict(r, assignment="field", jmri_name="M2T3408") if r["id"] == "switch:101" else r
                   for r in main_rows()]
        self.assertEqual({"Switch 101": "M2T3408"}, tb.level_turnouts(swapped))

    def test_every_layer_has_its_beans_named(self) -> None:
        self.assertEqual({"turnout", "fb", "occupancy", "sensor", "head", "mast", "block"}, set(tb.LAYER_BEANS))


class CommentOrder(unittest.TestCase):
    """The data reads first, the way the owner reads the tables (2026-11-22)."""

    def test_a_mast_names_its_direction_after_its_place(self) -> None:
        self.assertEqual("Brick | Switch 1 | West", tb.with_direction("Brick | Switch 1", "west"))
        self.assertEqual("Switch 241 | East", tb.with_direction("Switch 241", "east"))
        self.assertEqual("Switch 241 | East", tb.with_direction("Switch 241 | East", "east"))
        self.assertEqual("Brick", tb.with_direction("Brick", ""))
        self.assertEqual("Brick | West", tb.with_direction("Brick | West", "west"))      # named already: once

    def test_occupancy_back_undoes_occupancy_first(self) -> None:
        for master in ("Princess balloon, Track K-1; occupancy Block 1-1 / M2S100; stop",
                       "Brick CP, Switch 1; occupancy Block 4-2 / M2S401",
                       "Helix track; occupancy Block 41-2 / M2S4101 (main and upper device map); stop",
                       "occupancy Block 4-2 / M2S401"):
            self.assertEqual(master, tb.occupancy_back(tb.occupancy_first(master)))
        self.assertIsNone(tb.occupancy_back("Brick CP, Switch 1; occupancy Block 4-2 / M2S401"))

    def test_a_block_puts_its_detector_first_without_the_word_occupancy(self) -> None:
        self.assertEqual("Block 1-1 / M2S100; Princess balloon, Track K-1; stop",
                         tb.occupancy_first("Princess balloon, Track K-1; occupancy Block 1-1 / M2S100; stop"))
        self.assertEqual("Block 41-2 / M2S4101 (main and upper device map); Helix track, outer; stop",
                         tb.occupancy_first("Helix track, outer; occupancy Block 41-2 / M2S4101 "
                                            "(main and upper device map); stop"))
        self.assertEqual("Block 4-2 / M2S401", tb.occupancy_first("occupancy Block 4-2 / M2S401"))
        self.assertEqual("Brick CP, Switch 1", tb.occupancy_first("Brick CP, Switch 1"))

    def test_the_built_tables_carry_the_new_order(self) -> None:
        rs = rows()
        for r in rs:
            if r["user_name"] == "Mast 2L":
                r["dir"] = "west"
            if r["user_name"] == "OS Switch 1":
                r["jmri_comment"] = "Brick CP, Switch 1; occupancy Block 4-2 / M2S401"
        rs.append(blank(layer="mast", role="home", user_name="Mast 6LB", assignment="field", dir="west",
                        system_name="IF$shsm:basic:one-searchlight(IH432)",
                        jmri_name="IF$shsm:basic:one-searchlight(IH432)", jmri_comment="Plane | Switch 5"))
        root = tb.base(rs, lengths=LENGTHS).root
        heads = {tables.system_name(h): h.findtext("comment") for h in tables.signal_heads(root)}
        self.assertEqual("Plane | Switch 5 | Node: 4 Signal: 0 | OU: 2 Ports: 1,2,3", heads["IH432"])
        self.assertEqual("Brick | Switch 1 | internal, not wired", heads["IH:HART:C1:2L"])   # a virtual head as it was
        masts = {tables.user_name(m): m.findtext("comment") for m in tables.masts(root)}
        self.assertEqual("Brick | Switch 1 | West", masts["Mast 2L"])
        self.assertEqual("Brick", masts["Mast 4LA"])                          # no dir: nothing added
        self.assertEqual("Block 4-2 / M2S401; Brick CP, Switch 1", tables.blocks(root)[0].findtext("comment"))


class MissingLogic(unittest.TestCase):
    def test_head_masts_need_a_source_and_virtual_masts_a_mention(self) -> None:
        root = tables.loads(STORE).root
        self.assertEqual([], tables_sml.missing_logic(root))
        box = root.find("signalmastlogics")
        box.remove(box.find("signalmastlogic"))
        self.assertEqual(["Mast 6LB", "Mast 4LA"], tables_sml.missing_logic(root))

    def test_the_committed_tables_miss_none(self) -> None:
        self.assertEqual([], tables_sml.missing_logic(tables.read(paths.REPO_TABLES_XML)))


class Order(unittest.TestCase):
    def test_jmri_order(self) -> None:
        self.assertEqual(["IH432", "IH9990", "IH:HART:C1:2L_Bottom", "IH:HART:C1:2L_Top", "IH:HART:C1:24L"],
                         ts.jmri_order(["IH:HART:C1:24L", "IH9990", "IH:HART:C1:2L_Top", "IH432",
                                        "IH:HART:C1:2L_Bottom"]))
        self.assertEqual(["IS:SML_MODE", "IS:TRACK_POWER", "ISCLOCKRUNNING"],
                         ts.jmri_order(["ISCLOCKRUNNING", "IS:TRACK_POWER", "IS:SML_MODE"]))
        self.assertEqual(["IB24", "IB:AUTO:0001"], ts.jmri_order(["IB:AUTO:0001", "IB24"]))


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
        doc = tables_sml.discovered_from_store(store)
        path = self.tmp / "d.xml"
        self.assertTrue(tables_sml.write_discovered(doc, path))
        self.assertFalse(tables_sml.write_discovered(doc, path))                 # unchanged bytes: not written again
        logics, props = tables_sml.read_discovered(path)
        self.assertEqual(["Mast 6LB"], [x.get("source") for x in logics])
        self.assertEqual(["Mast 6LB"], list(props))
        target = tables.loads(STORE).root
        for m in tables.masts(target):
            p = m.find("properties")
            if p is not None:
                m.remove(p)
        box = target.find("signalmastlogics")
        box.remove(box.find("signalmastlogic"))
        tables_sml.merge_discovered(target, logics, props)
        mast = tables.masts(target)[0]
        self.assertEqual(["systemName", "userName", "properties", "unlit"], [c.tag for c in tables.elements(mast)])
        self.assertEqual(["logicDelay", "signalmastlogic"], [c.tag for c in tables.elements(box)])

    def test_a_store_without_logic_stops(self) -> None:
        root = tables.loads(STORE).root
        box = root.find("signalmastlogics")
        box.remove(box.find("signalmastlogic"))
        with self.assertRaisesRegex(tb.TablesBuildError, "no Signal Mast Logic"):
            tables_sml.discovered_from_store(root)

    def test_logic_naming_a_mast_the_tables_lack_stops(self) -> None:
        logics, props = tables_sml.read_discovered_root(tables_sml.discovered_from_store(tables.loads(STORE).root), "x")
        target = tables.loads(STORE).root
        box = target.find("signalmastlogics")
        box.remove(box.find("signalmastlogic"))
        sm = target.find("signalmasts")
        sm.remove(sm.find("virtualsignalmast"))
        with self.assertRaisesRegex(tb.TablesBuildError, "names masts the tables do not hold \\(Mast 4LA\\)"):
            tables_sml.merge_discovered(target, logics, props)

    def test_a_bad_discovered_file_stops(self) -> None:
        for body, why in (("<other />", "not <discovered-sml>"),
                          ("<discovered-sml><signalmastlogic /></discovered-sml>", "source ''"),
                          ("<discovered-sml><x /></discovered-sml>", "neither signalmastlogic"),
                          ("<discovered-sml><mastproperties mast='M' /></discovered-sml>", "exactly one")):
            with self.subTest(why=why), self.assertRaisesRegex(tb.TablesBuildError, why):
                tables_sml.read_discovered_root(ET.fromstring(body), "d.xml")
        with self.assertRaisesRegex(tb.TablesBuildError, "cannot read it"):
            tables_sml.read_discovered(self.tmp / "none.xml")

    def test_the_committed_file_names_only_masts_of_the_tables(self) -> None:
        logics, props = tables_sml.read_discovered()
        masts = {tables.user_name(m) for m in tables.masts(tables.read(paths.REPO_TABLES_XML))}
        named = {x.get("source") for x in logics} | {d.get("destination") for x in logics
                                                     for d in x.findall("destinationMast")}
        self.assertEqual(set(), (named | set(props)) - masts)


SORTABLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<layout-config>
  <sensors class="x">
    <defaultInitialState>unknown</defaultInitialState>
    <sensor><systemName>ISCLOCKRUNNING</systemName></sensor>
    <sensor><systemName>IS:SML_MODE</systemName></sensor>
    <sensor><systemName>IS:HART:C3:B:101</systemName></sensor>
  </sensors>
  <blocks class="y">
    <defaultspeed>Normal</defaultspeed>
    <block systemName="IB:AUTO:0001"><systemName>IB:AUTO:0001</systemName></block>
    <block systemName="IB24"><systemName>IB24</systemName></block>
    <block systemName="IB:AUTO:0001" length="1.0"><systemName>IB:AUTO:0001</systemName><permissive>no</permissive></block>
    <block systemName="IB24" length="2.0"><systemName>IB24</systemName><permissive>no</permissive>
      <path block="IB:AUTO:0001" /></block>
  </blocks>
  <LogixNGs>
    <Thread><id>0</id></Thread>
    <LogixNG><systemName>IQ:AUTO:0001</systemName></LogixNG>
    <LogixNG><systemName>IQ$HART:C3:X</systemName></LogixNG>
    <InitializationTable />
  </LogixNGs>
</layout-config>
"""


class StoreOrder(unittest.TestCase):
    def test_beans_take_jmri_order_and_settings_stay(self) -> None:
        root = tables.loads(SORTABLE).root
        ts.jmri_sort(root)
        internal = root.find("sensors")
        self.assertEqual(["defaultInitialState", "IS:HART:C3:B:101", "IS:SML_MODE", "ISCLOCKRUNNING"],
                         [tables.system_name(e) or e.tag for e in tables.elements(internal)])
        blocks = [(tables.system_name(e), bool(e.get("length"))) for e in root.find("blocks").findall("block")]
        self.assertEqual([("IB24", False), ("IB:AUTO:0001", False), ("IB24", True), ("IB:AUTO:0001", True)], blocks)
        self.assertEqual(["Thread", "IQ$HART:C3:X", "IQ:AUTO:0001", "InitializationTable"],
                         [tables.system_name(e) or e.tag for e in tables.elements(root.find("LogixNGs"))])

    def test_the_generated_file_is_in_store_order(self) -> None:
        doc = tables.loads(paths.REPO_TABLES_XML.read_bytes())
        ts.jmri_sort(doc.root)
        tb.finish(doc.root)
        self.assertEqual(paths.REPO_TABLES_XML.read_bytes(), doc.tobytes())


class RoundTrip(unittest.TestCase):
    def store_of(self, data: bytes) -> bytes:
        """A Store as JMRI writes one: the file history and the "Written by" comment added, a clock time, the
        derived block paths on every full block pass."""
        doc = tables.loads(data)
        root = doc.root
        root.find("timebase").set("time", "Fri Nov 20 17:36:00 EST 2026")
        for b in tables.blocks(root):
            ET.SubElement(b, "path", block="IB1")
        ET.SubElement(root, "filehistory")
        root.append(ET.Comment("Written by JMRI version 5.16"))
        tb.finish(root)
        return doc.tobytes()

    def test_a_store_of_the_generated_file_normalises_to_its_bytes(self) -> None:
        generated = paths.REPO_TABLES_XML.read_bytes()
        self.assertEqual([], tables_roundtrip.roundtrip_differences(self.store_of(generated), generated))

    def test_a_changed_store_is_shown(self) -> None:
        generated = paths.REPO_TABLES_XML.read_bytes()
        store = self.store_of(generated).replace(b"<userName>Clock running</userName>",
                                                 b"<userName>Clock</userName>")
        diff = tables_roundtrip.roundtrip_differences(store, generated)
        self.assertIn("-      <userName>Clock running</userName>", diff)
        self.assertIn("+      <userName>Clock</userName>", diff)

    def test_the_report_fails_a_staging_block_with_no_derived_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store, counts = Path(tmp) / "store.xml", Path(tmp) / "paths.tsv"
            store.write_bytes(self.store_of(paths.REPO_TABLES_XML.read_bytes()))
            counts.write_text("IB1\tOS Switch 13\t3\nIB3\tTrack Scale\t0\n", encoding="utf-8")
            ok, lines = tables_roundtrip.roundtrip_report(store, counts, paths.REPO_TABLES_XML)
            self.assertFalse(ok)
            self.assertTrue(any(line.startswith("FAIL: staging blocks with no derived path: ") and "IB3" in line
                                for line in lines), lines)
            self.assertTrue(any(line.startswith("ok: the Store and the generated tables.xml are the same bytes")
                                for line in lines), lines)
            self.assertEqual("FAIL: the PanelPro round trip does not give the generated tables.xml back", lines[-1])
            counts.write_text("IB1 broken\n", encoding="utf-8")
            with self.assertRaisesRegex(tb.TablesBuildError, "line 1 is not"):
                tables_roundtrip.roundtrip_report(store, counts, paths.REPO_TABLES_XML)


PANEL = (
    '<layout-config>\n  <LayoutEditor class="LE" name="HART Railroad" x="0" y="0" sliders="no" windowwidth="1900" '
    'windowheight="1140" panelwidth="2509">\n'
    '    <layoutturnout ident="TOL15" type="LH_TURNOUT" ver="1" xcen="1018.6" ycen="282.0" xa="1011.3" ya="272.5" '
    'xb="1026.0" yb="291.5" xc="1030.6" yc="282.0" xd="1011.3" yd="272.5" />\n'
    '    <tracksegment ident="TG63" angle="90" />\n'
    '    <positionablepoint ident="AGE1" x="1761.2" y="195.0" />\n'
    '    <BlockContentsIcon blockcontents="OS Switch 1" editable="true" x="10" y="20" />\n'
    '    <positionablelabel text="SW-1" x="389" y="159" />\n'
    '  </LayoutEditor>\n</layout-config>\n')


class PanelRewrites(unittest.TestCase):
    """normalise_panel: each rewrite a PanelPro Store makes to the panel compares equal, and nothing more does."""

    def same(self, store: str) -> list[str]:
        return tables_roundtrip.roundtrip_differences(store.encode(), PANEL.encode())

    def test_window_state(self) -> None:
        self.assertEqual([], self.same(PANEL.replace('x="0" y="0" sliders="no" windowwidth="1900" windowheight="1140"',
                                                     'x="270" y="147" sliders="yes" windowwidth="1600" '
                                                     'windowheight="900"')))
        self.assertNotEqual([], self.same(PANEL.replace('panelwidth="2509"', 'panelwidth="2600"')))

    def test_attribute_order(self) -> None:
        self.assertEqual([], self.same(PANEL.replace('class="LE" name="HART Railroad"',
                                                     'name="HART Railroad" class="LE"')
                                       .replace('ident="TG63" angle="90"', 'angle="90" ident="TG63"')))

    def test_element_order(self) -> None:
        moved = PANEL.replace('    <positionablelabel text="SW-1" x="389" y="159" />\n', '').replace(
            '    <layoutturnout', '    <positionablelabel text="SW-1" x="389" y="159" />\n    <layoutturnout')
        self.assertEqual([], self.same(moved))

    def test_numbers_at_float32(self) -> None:
        self.assertEqual([], self.same(PANEL.replace('x="1761.2"', 'x="1761.199951171875"')
                                       .replace('angle="90"', 'angle="90.0"')))
        self.assertNotEqual([], self.same(PANEL.replace('x="1761.2"', 'x="1761.3"')))      # no wider tolerance

    def test_block_contents_editable(self) -> None:
        self.assertEqual([], self.same(PANEL.replace('editable="true"', 'editable="false"')))
        self.assertNotEqual([], self.same(PANEL.replace('blockcontents="OS Switch 1"', 'blockcontents="OS Switch 3"')))

    def test_derived_turnout_points(self) -> None:
        """JMRI computes a version 1 turnout's A and D from its centre and B (2 x 1018.6 - 1026.0, in doubles from
        floats), so a Store writes 1011.199951171875 where the file held 1011.3; a changed B still differs."""
        derived = PANEL.replace('xa="1011.3"', 'xa="1011.199951171875"').replace('xd="1011.3"',
                                                                                 'xd="1011.199951171875"')
        self.assertEqual([], self.same(derived))
        self.assertNotEqual([], self.same(PANEL.replace('xb="1026.0"', 'xb="1026.5"')))

    def test_a_label_change_still_differs(self) -> None:
        self.assertNotEqual([], self.same(PANEL.replace('text="SW-1"', 'text="SW-2"')))


class Envelope(unittest.TestCase):
    def test_strip_takes_out_what_a_store_writes(self) -> None:
        root = tables.loads(STORE.replace(b"<signalmasts>", b'<timebase time="x" /><memories><memory value="1">'
                                          b"<systemName>IM1</systemName></memory></memories><signalmasts>")).root
        self.assertEqual(["filehistory", "the 'Written by' comment", "timebase@time", "memory@value"],
                         tb.envelope_items(root))
        tables_normal.strip_envelope(root)
        self.assertEqual([], tb.envelope_items(root))

    def test_the_generated_file_has_the_fixed_envelope(self) -> None:
        doc = tables.load(paths.REPO_TABLES_XML)
        self.assertEqual((tb.PROLOG, tb.EPILOG), (doc.prolog, doc.epilog))
        self.assertEqual([], tb.envelope_items(doc.root))


if __name__ == "__main__":
    unittest.main()

"""hartlib.store_split: where each change of a PanelPro Store goes (R9d, owner design 2026-11-20): the template keeps
what the owner made, the repo wins on what the build makes, device facts and clashes are reviewed. Small tables built
here; tools/schematic/split_store.py runs the same code on the real files."""
from __future__ import annotations

import copy
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import devices as D, jmri_bean, tables, tables_normal, tables_sections  # noqa: E402
from hartlib import store_plan as sp  # noqa: E402
from hartlib import store_split as ss  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402
from master_edit import fixture_id  # noqa: E402

TURNOUTS = 'class="jmri.jmrix.openlcb.configurexml.OlcbTurnoutManagerXml"'
MEMORIES = 'class="jmri.managers.configurexml.DefaultMemoryManagerXml"'
BLOCKS = 'class="jmri.configurexml.BlockManagerXml"'
LBLOCKS = 'class="jmri.jmrit.display.layoutEditor.configurexml.LayoutBlockManagerXml"'
LOGICS = 'class="jmri.managers.configurexml.DefaultSignalMastLogicManagerXml"'
TIMEBASE = 'class="jmri.jmrit.simpleclock.configurexml.SimpleTimebaseXml"'
ISENSORS = 'class="jmri.jmrix.internal.configurexml.InternalSensorManagerXml"'


def blank(**cells) -> dict:
    row = {c: "" for c in D.COLUMNS}
    row.update({"level": "1", "description": "A device.", **cells})
    if row["level"] and "id" not in cells:          # check_rows wants one on every row with a level
        row["id"] = fixture_id(row)
    return row


ROWS = [
    blank(layer="turnout", role="lcc_alias", user_name="DCC Switch 1", assignment="field", system_name="MTT100",
          jmri_name="MTT100", wiring="Node: 4 Turnout: 0"),
    blank(layer="turnout", role="turnout", user_name="Switch 1", assignment="field", system_name="M2T408",
          jmri_name="Switch 1", jmri_comment="bound by its user name"),
    blank(layer="block", role="os", user_name="OS Switch 1", assignment="field", system_name="IB:AUTO:0033",
          jmri_name="IB:AUTO:0033", layout_block="ILB33", jmri_comment="Brick CP, Switch 1"),
    blank(layer="block", role="track", user_name="Track 5", assignment="field", system_name="IB:AUTO:0040",
          jmri_name="IB:AUTO:0040", layout_block="ILB40", jmri_comment="Track 5", written_by="build_device_map.py"),
]


def bean(tag: str, system: str, user: str = "", comment: str = "", **attrs) -> str:
    a = "".join(f' {k}="{v}"' for k, v in attrs.items())
    kids = f"<systemName>{system}</systemName>" + (f"<userName>{user}</userName>" if user else "")
    kids += f"<comment>{comment}</comment>" if comment else ""
    return f"<{tag}{a}>{kids}</{tag}>"


def doc(memories: str = "", timebase_rate: str = "1.0", turnouts: str | None = None, blocks: str | None = None,
        logic_enabled: str = "yes", panel_x: str = "10", extra: str = "", isensors: str = "",
        template: bool = False) -> ET.Element:
    """A small tables root: a known section of each kind the tests need; `template` leaves out the build's part."""
    if turnouts is None:
        turnouts = (bean("turnout", "MTT100", "DCC Switch 1", "Node: 4 Turnout: 0")
                    + bean("turnout", "M2T408", "Switch 1", "bound by its user name"))
    if blocks is None:
        blocks = bean("block", "IB:AUTO:0033", "OS Switch 1", "Brick CP, Switch 1", systemName="IB:AUTO:0033")
    mem = bean("memory", "IMCURRENTTIME", "Current time") + memories
    build = not template
    text = (
        "<layout-config>"
        "<jmriversion><major>5</major></jmriversion>"
        f"<sensors {ISENSORS}><defaultInitialState>unknown</defaultInitialState>"
        + (bean("sensor", "IS:HART:C3:B:101", "BS 101") if build else "") + isensors + "</sensors>"
        f"<turnouts {TURNOUTS}><operations automate='false'/>" + (turnouts if build else "") + "</turnouts>"
        f"<memories {MEMORIES}>{mem}</memories>"
        f"<blocks {BLOCKS}><defaultspeed>Normal</defaultspeed>" + (blocks if build else "") + "</blocks>"
        f"<layoutblocks {LBLOCKS}>"
        + (bean("layoutblock", "ILB33", "OS Switch 1", systemName="ILB33") if build else "") + "</layoutblocks>"
        f"<signalmastlogics {LOGICS}><logicDelay>500</logicDelay>"
        + (f'<signalmastlogic source="Mast 2L"><sourceSignalMast>Mast 2L</sourceSignalMast>'
           f"<enabled>{logic_enabled}</enabled></signalmastlogic>" if build else "") + "</signalmastlogics>"
        f'<timebase {TIMEBASE} rate="{timebase_rate}" />'
        + extra
        + (f'<LayoutEditor name="HART Railroad"><positionablelabel x="{panel_x}" /></LayoutEditor>' if build else "")
        + "</layout-config>"
    )
    root = ET.fromstring(text)
    tb.finish(root)
    return root


def plan(base, repo, store, template=None, rows=ROWS):
    template = template if template is not None else doc(template=True)
    return ss.plan(base, repo, store, template, rows)


def kinds(p: ss.Plan) -> dict[str, list[str]]:
    return {k: [i.where for i in p.of(k)] for k in ss.KINDS if p.of(k)}


class Unchanged(unittest.TestCase):
    def test_a_store_of_the_base_plans_nothing(self) -> None:
        p = plan(doc(), doc(), doc())
        self.assertEqual([], p.items)

    def test_a_repo_change_since_the_base_is_not_the_owners(self) -> None:
        """The repo removed a memory and changed the rate since the deploy; the Store still has the deploy's: no
        item, so nothing the repo did is undone."""
        base = doc(memories=bean("memory", "IMOLD", "Old"), timebase_rate="1.0")
        p = plan(base, doc(timebase_rate="2.0"), copy.deepcopy(base))
        self.assertEqual([], p.items)


class TemplateItems(unittest.TestCase):
    def test_the_owners_settings_and_new_memories_are_kept(self) -> None:
        store = doc(memories=bean("memory", "IMOWNER", "Owner"), timebase_rate="4.0")
        p = plan(doc(), doc(), store)
        self.assertEqual({ss.KEPT: ["<timebase> settings", "memory IMOWNER (Owner)"]}, kinds(p))
        self.assertIn("rate '1.0' -> '4.0'", p.by_id()["K1"].what)

    def test_a_template_item_the_repo_changed_too_is_a_clash(self) -> None:
        p = plan(doc(), doc(timebase_rate="2.0"), doc(timebase_rate="4.0"),
                 template=doc(template=True, timebase_rate="2.0"))
        self.assertEqual({ss.CLASH: ["<timebase> settings"]}, kinds(p))

    def test_with_no_base_every_template_change_is_a_clash(self) -> None:
        p = plan(None, doc(), doc(timebase_rate="4.0"))
        self.assertFalse(p.has_base)
        self.assertEqual({ss.CLASH: ["<timebase> settings"]}, kinds(p))
        self.assertTrue(any("NO BASE" in line for line in ss.report(p)))

    def test_an_extra_section_is_kept_and_a_parked_one_dropped(self) -> None:
        routes = '<routes class="jmri.managers.configurexml.DefaultRouteManagerXml"><route systemName="IO1">' \
                 "<systemName>IO1</systemName></route></routes>"
        nx = '<entryexitpairs class="jmri.jmrit.signalling.configurexml.EntryExitPairsXml" />'
        p = plan(doc(), doc(), doc(extra=routes + nx))
        self.assertEqual([i.key[1] for i in p.of(ss.KEPT)], ["routes"])
        self.assertEqual([i.key[1] for i in p.of(ss.DROPPED)], ["entryexitpairs"])
        self.assertIn("parked", p.of(ss.DROPPED)[0].note)

    def test_a_panel_or_a_second_connection_section_is_dropped(self) -> None:
        extra = '<ControlPanelEditor name="cpe" />' \
                '<sensors class="jmri.jmrix.openlcb.configurexml.OlcbSensorManagerXml" />'
        p = plan(doc(), doc(), doc(extra=extra))
        self.assertEqual([], p.of(ss.KEPT))
        self.assertEqual(2, len(p.of(ss.DROPPED)))

    def test_a_section_the_store_left_out_keeps_its_class(self) -> None:
        store = doc()
        store.remove(store.find("timebase"))
        p = plan(doc(), doc(), store)
        self.assertEqual([], p.items)

    def test_a_memory_on_a_claimed_name_is_dropped(self) -> None:
        p = plan(doc(), doc(), doc(memories=bean("memory", "IMIS:ISMEM:versionNo")))
        self.assertEqual({ss.DROPPED: ["memory IMIS:ISMEM:versionNo"]}, kinds(p))


class BuildItems(unittest.TestCase):
    def test_the_panel_logic_and_a_deleted_bean_are_dropped(self) -> None:
        store = doc(panel_x="15", logic_enabled="no")
        sec = next(s for s in tables.elements(store) if s.get("class", "").endswith("InternalSensorManagerXml"))
        sec.remove(next(e for e in tables.elements(sec) if tables.system_name(e)))
        p = plan(doc(), doc(), store)
        self.assertEqual(sorted(["panel 'HART Railroad'", "Signal Mast Logic from 'Mast 2L'",
                                 "sensor IS:HART:C3:B:101 (BS 101)"]), sorted(kinds(p)[ss.DROPPED]))
        self.assertNotIn(ss.KEPT, kinds(p))

    def test_a_new_device_on_a_name_a_row_plans_names_that_row(self) -> None:
        rows = ROWS + [blank(level="2", layer="turnout", role="lcc_alias", user_name="DCC Switch 9",
                             assignment="virtual", system_name="MTT200", jmri_name="IT:HART:C3:9")]
        turnouts = (bean("turnout", "MTT100", "DCC Switch 1", "Node: 4 Turnout: 0")
                    + bean("turnout", "M2T408", "Switch 1", "bound by its user name")
                    + bean("turnout", "MTT200", "Test 200"))
        p = plan(doc(), doc(), doc(turnouts=turnouts), rows=rows)
        [g] = p.of(ss.DROPPED)
        self.assertEqual("added in the Store", g.what)
        self.assertIn("'DCC Switch 9' plans this device", g.note)
        self.assertEqual([], p.of(ss.DEVICE))

    def test_a_new_device_on_a_field_rows_user_name_says_to_rename_it(self) -> None:
        turnouts = TURNOUTS_NOW + bean("turnout", "MTT950", "Switch 1")
        [g] = plan(doc(), doc(), doc(turnouts=turnouts)).of(ss.DROPPED)
        self.assertEqual("its user name 'Switch 1' is that row's user_name; give the Store's device another name in "
                         "PanelPro", g.note)

    def test_a_layout_block_alone_is_dropped_not_a_crash(self) -> None:
        store = doc()
        store.find("layoutblocks").append(ET.fromstring(bean("layoutblock", "ILB98", "Lonely", systemName="ILB98")))
        [g] = plan(doc(), doc(), store).of(ss.DROPPED)
        self.assertIn("a layout block with no block", g.note)


TEST_TURNOUT = ('<turnout feedback="MONITORING" inverted="false" automate="Off"><systemName>MTT999</systemName>'
                "<userName>Test 999</userName></turnout>")
TURNOUTS_NOW = (bean("turnout", "MTT100", "DCC Switch 1", "Node: 4 Turnout: 0")
                + bean("turnout", "M2T408", "Switch 1", "bound by its user name"))


def unplaced(store: ET.Element, *names: str) -> dict:
    """The level-less row of the beans named `names` in `store` (the row a merge adds)."""
    beans = [(tb.section_key(sec), el) for sec in tables.elements(store) for el in tables.elements(sec)
             if tables.system_name(el) in names]
    return ss.unplaced_row(beans)


class AddedDevices(unittest.TestCase):
    """A device the owner adds in PanelPro becomes a level-less devices.csv row on merge, its beans kept exactly in
    jmri_bean (owner, 2026-11-20): a test turnout or a DCC accessory is no layout element."""

    def test_a_new_turnout_is_a_row_to_add_with_the_stores_bean(self) -> None:
        store = doc(turnouts=TURNOUTS_NOW + TEST_TURNOUT)
        p = plan(doc(), doc(), store)
        [d] = p.of(ss.DEVICE)
        self.assertEqual((ss.ROW, "added in the Store"), (d.part, d.what))
        [add] = d.edits
        row = add.row
        self.assertEqual(("", "", "turnout", "", "Test 999", "field", "MTT999", "MTT999"),
                         tuple(row[c] for c in ("level", "cp", "layer", "role", "user_name", "assignment",
                                                "system_name", "jmri_name")))
        [(sec, el)] = jmri_bean.row_beans(row)
        self.assertEqual(tables_sections.LCC_TURNOUTS, sec)
        self.assertEqual(ss.canon(store.find("turnouts").find("turnout[systemName='MTT999']")), ss.canon(el))
        self.assertNotIn("Test 999", row["jmri_bean"])      # the user name is the column's, not a second copy

    def test_the_row_goes_after_every_level_and_passes_the_checks(self) -> None:
        p = plan(doc(), doc(), doc(turnouts=TURNOUTS_NOW + TEST_TURNOUT))
        rows = ss.edited_rows(ROWS, ss.device_edits(p, ss.Choices(merge=frozenset({"D1"}))))
        self.assertEqual("Test 999", rows[-1]["user_name"])
        D.check_rows(rows)

    def test_a_dropped_new_device_writes_nothing(self) -> None:
        p = plan(doc(), doc(), doc(turnouts=TURNOUTS_NOW + TEST_TURNOUT))
        self.assertEqual([], ss.device_edits(p, ss.Choices()))

    def test_a_new_block_with_both_passes_and_its_layout_block_is_one_row(self) -> None:
        old = bean("block", "IB:AUTO:0033", "OS Switch 1", "Brick CP, Switch 1", systemName="IB:AUTO:0033")
        new = (bean("block", "IB99", "Test block", systemName="IB99")
               + bean("block", "IB99", "Test block", "Owner's", systemName="IB99", length="100.0"))
        store = doc(blocks=old + new)
        store.find("layoutblocks").append(ET.fromstring(bean("layoutblock", "ILB99", "Test block",
                                                             systemName="ILB99")))
        p = plan(doc(blocks=old), doc(blocks=old), store)
        [d] = p.of(ss.DEVICE)
        self.assertEqual(2, len(d.also))
        row = d.edits[0].row
        self.assertEqual(("block", "Test block", "IB99", "ILB99", "Owner's"),
                         (row["layer"], row["user_name"], row["jmri_name"], row["layout_block"], row["jmri_comment"]))
        self.assertEqual(3, len(jmri_bean.row_beans(row)))
        D.check_rows(ROWS + [row])


class UnplacedRows(unittest.TestCase):
    """A level-less row's beans are the Store's: a later Store that changes or deletes them is a DEVICE merge."""

    def setUp(self) -> None:
        self.repo = doc(turnouts=TURNOUTS_NOW + TEST_TURNOUT)
        self.rows = ROWS + [unplaced(self.repo, "MTT999")]

    def test_a_feedback_change_rewrites_the_bean_column(self) -> None:
        store = doc(turnouts=TURNOUTS_NOW + TEST_TURNOUT.replace("MONITORING", "DIRECT"))
        p = plan(self.repo, self.repo, store, rows=self.rows)
        [d] = p.of(ss.DEVICE)
        self.assertEqual(["jmri_bean"], [e.column for e in d.edits])
        self.assertIn("DIRECT", d.edits[0].new)

    def test_a_rename_changes_only_the_user_name(self) -> None:
        store = doc(turnouts=TURNOUTS_NOW + TEST_TURNOUT.replace("Test 999", "Yard light"))
        p = plan(self.repo, self.repo, store, rows=self.rows)
        [d] = p.of(ss.DEVICE)
        self.assertEqual([("user_name", "Yard light")], [(e.column, e.new) for e in d.edits])

    def test_a_device_deleted_in_the_store_deletes_its_row(self) -> None:
        p = plan(self.repo, self.repo, doc(turnouts=TURNOUTS_NOW), rows=self.rows)
        [d] = p.of(ss.DEVICE)
        self.assertEqual((ss.RowDelete(("", "turnout", "Test 999")),), d.edits)        # by key, never by place
        self.assertEqual(ROWS, ss.edited_rows(self.rows, d.edits))

    def test_a_repo_edit_since_the_deploy_survives_an_owner_rename(self) -> None:
        """The repo gave the row a comment after the deploy; the owner renamed it in PanelPro. The merge renames only."""
        rows = ROWS + [dict(self.rows[-1], jmri_comment="DCC 999")]
        repo = doc(turnouts=TURNOUTS_NOW + TEST_TURNOUT.replace("</userName>", "</userName><comment>DCC 999</comment>"))
        store = doc(turnouts=TURNOUTS_NOW + TEST_TURNOUT.replace("Test 999", "Yard light"))
        [d] = plan(self.repo, repo, store, rows=rows).of(ss.DEVICE)
        self.assertEqual([("user_name", "Yard light")], [(e.column, e.new) for e in d.edits])

    def test_a_new_layout_block_for_a_level_less_block_is_a_row_rewrite(self) -> None:
        blocks = bean("block", "IB:AUTO:0033", "OS Switch 1", "Brick CP, Switch 1", systemName="IB:AUTO:0033")
        mine = (bean("block", "IB99", "Test block", systemName="IB99")
                + bean("block", "IB99", "Test block", "Owner's", systemName="IB99"))
        repo = doc(blocks=blocks + mine)
        rows = ROWS + [unplaced(repo, "IB99")]
        store = doc(blocks=blocks + mine)
        store.find("layoutblocks").append(ET.fromstring(bean("layoutblock", "ILB99", "Test block",
                                                             systemName="ILB99")))
        [d] = plan(repo, repo, store, rows=rows).of(ss.DEVICE)
        self.assertEqual({"layout_block", "jmri_bean"}, {e.column for e in d.edits})
        self.assertEqual([], plan(repo, repo, store, rows=rows).of(ss.DROPPED))

    def test_an_unchanged_level_less_device_plans_nothing(self) -> None:
        p = plan(self.repo, self.repo, self.repo, rows=self.rows)
        self.assertEqual([], p.items)

    def test_the_build_gives_the_stores_bean_back(self) -> None:
        kept = jmri_bean.kept_beans(self.rows)
        [el] = kept[tables_sections.LCC_TURNOUTS]
        self.assertEqual(ss.canon(self.repo.find("turnouts").find("turnout[systemName='MTT999']")), ss.canon(el))


class DeviceItems(unittest.TestCase):
    def test_a_hand_kept_comment_is_a_device_merge(self) -> None:
        blocks = bean("block", "IB:AUTO:0033", "OS Switch 1", "Owner note", systemName="IB:AUTO:0033")
        p = plan(doc(), doc(), doc(blocks=blocks))
        [d] = p.of(ss.DEVICE)
        self.assertEqual((ss.Edit(("1", "test:block:OS Switch 1"), "jmri_comment", "Brick CP, Switch 1", "Owner note"),), d.edits)

    def detected(self) -> list[dict]:
        """ROWS with OS Switch 1's detector in its comment, as build_device_map.py fills it in."""
        return [dict(r, jmri_comment="Brick CP, Switch 1; occupancy Block 4-2 / M2S401")
                if r["user_name"] == "OS Switch 1" else r for r in ROWS]

    def blocks(self, comment: str) -> str:
        return bean("block", "IB:AUTO:0033", "OS Switch 1", comment, systemName="IB:AUTO:0033")

    def test_a_detector_first_block_comment_goes_back_in_the_masters_order(self) -> None:
        built = doc(blocks=self.blocks("Block 4-2 / M2S401; Brick CP, Switch 1"))
        store = doc(blocks=self.blocks("Block 4-2 / M2S401; Brick CP, Switch 1 east"))
        [d] = plan(built, built, store, rows=self.detected()).of(ss.DEVICE)
        self.assertEqual(["Brick CP, Switch 1 east; occupancy Block 4-2 / M2S401"], [e.new for e in d.edits])

    def test_a_block_comment_without_its_detector_first_is_dropped(self) -> None:
        built = doc(blocks=self.blocks("Block 4-2 / M2S401; Brick CP, Switch 1"))
        store = doc(blocks=self.blocks("Brick CP, Switch 1; occupancy Block 4-2 / M2S401"))
        p = plan(built, built, store, rows=self.detected())
        self.assertEqual([], p.of(ss.DEVICE))
        self.assertIn("starts with its detector", p.of(ss.DROPPED)[0].note)

    MAST = blank(layer="mast", role="home", user_name="Mast 2L", assignment="virtual", dir="west",
                 system_name="IF$shsm:basic:one-searchlight(IH:HART:C1:2L)",
                 jmri_name="IF$shsm:basic:one-searchlight(IH:HART:C1:2L)", jmri_comment="Brick | Switch 1")

    def masts(self, comment: str) -> str:
        return ('<signalmasts class="jmri.managers.configurexml.DefaultSignalMastManagerXml">'
                + bean("signalmast", self.MAST["jmri_name"], "Mast 2L", comment,
                       **{"class": "jmri.implementation.configurexml.SignalHeadSignalMastXml"})
                + "</signalmasts>")

    def test_a_masts_direction_is_left_out_of_its_jmri_comment(self) -> None:
        built = doc(extra=self.masts("Brick | Switch 1 | West"))
        store = doc(extra=self.masts("Brick | Switch 1 | West | home"))
        [d] = plan(built, built, store, rows=ROWS + [self.MAST]).of(ss.DEVICE)
        self.assertEqual(["Brick | Switch 1 | home"], [e.new for e in d.edits])

    def test_a_mast_comment_without_its_direction_is_dropped(self) -> None:
        built = doc(extra=self.masts("Brick | Switch 1 | West"))
        p = plan(built, built, doc(extra=self.masts("Brick | Switch 1")), rows=ROWS + [self.MAST])
        self.assertEqual([], p.of(ss.DEVICE))
        self.assertIn("direction", p.of(ss.DROPPED)[0].note)

    def test_a_wiring_comment_is_dropped(self) -> None:
        turnouts = (bean("turnout", "MTT100", "DCC Switch 1", "Owner note")
                    + bean("turnout", "M2T408", "Switch 1", "bound by its user name"))
        p = plan(doc(), doc(), doc(turnouts=turnouts))
        self.assertEqual([], p.of(ss.DEVICE))
        self.assertIn("wiring", p.of(ss.DROPPED)[0].note)

    def test_a_rename_of_a_bean_bound_by_its_user_name_writes_both_columns(self) -> None:
        turnouts = (bean("turnout", "MTT100", "DCC Switch 1", "Node: 4 Turnout: 0")
                    + bean("turnout", "M2T408", "Switch 1A", "bound by its user name"))
        p = plan(doc(), doc(), doc(turnouts=turnouts))
        [d] = p.of(ss.DEVICE)
        self.assertEqual({("user_name", "Switch 1A"), ("jmri_name", "Switch 1A")},
                         {(e.column, e.new) for e in d.edits})

    def test_a_rename_of_a_wired_staging_turnout_says_where_to_rename_it(self) -> None:
        """Staging's turnout rows are build_device_map.py's since wiring.csv (2026-11-20); a rename is the owner's,
        by hand in its field row (keyed by id), not a rebuild's. By the row's layer and writer, not its level
        (naming-layers step 14): a main turnout swapped in the same way is told the same."""
        turnouts = (bean("turnout", "MTT100", "DCC Switch 1", "Node: 4 Turnout: 0")
                    + bean("turnout", "M2T408", "Switch 1A", "bound by its user name"))
        for level in ("1", "2"):
            with self.subTest(level=level):
                rows = [dict(r, written_by="build_device_map.py", level=level) if r["layer"] == "turnout" else r
                        for r in ROWS]
                p = plan(doc(), doc(), doc(turnouts=turnouts), rows=rows)
                self.assertEqual([], p.of(ss.DEVICE))
                [g] = p.of(ss.DROPPED)
                self.assertIn("rename it by hand in its devices_field.csv row (keyed by its id): change user_name, "
                              "and jmri_name with it when that binds the turnout by its user name", g.note)
                # a comment edit is no rename: it is not told to rename the row (code review of step 14)
                edited = (bean("turnout", "MTT100", "DCC Switch 1", "Node: 4 Turnout: 0")
                          + bean("turnout", "M2T408", "Switch 1", "an owner's note"))
                notes = [d.note for d in plan(doc(), doc(), doc(turnouts=edited), rows=rows).of(ss.DROPPED)]
                self.assertTrue(notes)
                self.assertFalse([n for n in notes if "rename it by hand" in n], notes)

    def test_a_rename_of_a_built_block_says_where_to_rename_it(self) -> None:
        """Naming-layers step 8: a block row of the builder's (main and upper's are virtual beans with their names in
        the row) is renamed by hand in its field row, not by changing the builder's inputs."""
        rows = [dict(r, written_by="build_device_map.py") if r["layer"] == "block" else r for r in ROWS]
        before = bean("block", "IB:AUTO:0033", "OS Switch 1", "Brick CP, Switch 1", systemName="IB:AUTO:0033")
        after = bean("block", "IB:AUTO:0033", "OS Switch 1A", "Brick CP, Switch 1", systemName="IB:AUTO:0033")
        p = plan(doc(blocks=before), doc(blocks=before), doc(blocks=after), rows=rows)
        self.assertEqual([], p.of(ss.DEVICE))
        self.assertTrue(any("rename it by hand in its devices_field.csv row (keyed by its id): change user_name; its "
                            "jmri_name and layout_block stay" in g.note for g in p.of(ss.DROPPED)),
                        [g.note for g in p.of(ss.DROPPED)])

    def test_a_rename_on_both_passes_is_one_question(self) -> None:
        """A block's names-only pass and full pass (and its layout block) carry one rename: one DEVICE item."""
        both = (bean("block", "IB:AUTO:0033", "OS Switch 1A", systemName="IB:AUTO:0033")
                + bean("block", "IB:AUTO:0033", "OS Switch 1A", "Brick CP, Switch 1", systemName="IB:AUTO:0033"))
        before = (bean("block", "IB:AUTO:0033", "OS Switch 1", systemName="IB:AUTO:0033")
                  + bean("block", "IB:AUTO:0033", "OS Switch 1", "Brick CP, Switch 1", systemName="IB:AUTO:0033"))
        p = plan(doc(blocks=before), doc(blocks=before), doc(blocks=both))
        [d] = p.of(ss.DEVICE)
        self.assertEqual(1, len(d.also))
        self.assertEqual([ss.Edit(("1", "test:block:OS Switch 1"), "user_name", "OS Switch 1", "OS Switch 1A")], list(ss.device_edits(
            p, ss.Choices(merge=frozenset({d.id})))))

    def test_a_script_written_row_is_dropped(self) -> None:
        blocks = (bean("block", "IB:AUTO:0033", "OS Switch 1", "Brick CP, Switch 1", systemName="IB:AUTO:0033")
                  + bean("block", "IB:AUTO:0040", "Track 5", "Track 5", systemName="IB:AUTO:0040"))
        store_blocks = blocks.replace("<comment>Track 5</comment>", "<comment>Owner</comment>")
        p = plan(doc(blocks=blocks), doc(blocks=blocks), doc(blocks=store_blocks))
        [g] = p.of(ss.DROPPED)
        self.assertIn("build_device_map.py writes", g.note)


class Choices(unittest.TestCase):
    def test_only_reviewed_ids_merge_and_only_kept_ids_drop(self) -> None:
        p = plan(doc(), doc(timebase_rate="2.0"), doc(timebase_rate="4.0", memories=bean("memory", "IMOWNER")),
                 template=doc(template=True, timebase_rate="2.0"))
        ss.check_choices(p, ss.Choices(merge=frozenset({"C1"}), drop=frozenset({"K1"})))
        for bad in (ss.Choices(merge=frozenset({"K1"})), ss.Choices(drop=frozenset({"C1"})),
                    ss.Choices(merge=frozenset({"D9"}))):
            with self.assertRaises(ss.SplitError):
                ss.check_choices(p, bad)

    def test_the_fingerprint_follows_the_store(self) -> None:
        a = plan(doc(), doc(), doc(timebase_rate="4.0"))
        b = plan(doc(), doc(), doc(timebase_rate="5.0"))
        self.assertNotEqual(a.fingerprint, b.fingerprint)
        self.assertEqual(a.fingerprint, plan(doc(), doc(), doc(timebase_rate="4.0")).fingerprint)

    def test_an_edit_on_a_cell_that_moved_stops(self) -> None:
        with self.assertRaises(ss.SplitError):
            ss.edited_rows(ROWS, [ss.Edit(("1", "test:block:OS Switch 1"), "jmri_comment", "not this", "new")])
        with self.assertRaisesRegex(ss.SplitError, "has no row id 'test:block:OS Switch 9' \\(level 1\\)"):
            ss.edited_rows(ROWS, [ss.Edit(("1", "test:block:OS Switch 9"), "jmri_comment", "", "new")])

    def test_edits_find_their_row_by_key_wherever_it_is(self) -> None:
        """A rename and its jmri_name edit name the row by its key: both land, whatever the row's place."""
        rows = list(reversed(ROWS))
        key = ("1", "switch:1")                      # a field row is keyed by (level, id)
        got = ss.edited_rows(rows, [ss.Edit(key, "user_name", "Switch 1", "Switch 1X"),
                                    ss.Edit(key, "jmri_name", "Switch 1", "Switch 1X")])
        row = next(r for r in got if r["system_name"] == "M2T408")
        self.assertEqual((row["user_name"], row["jmri_name"]), ("Switch 1X", "Switch 1X"))


class NewTemplate(unittest.TestCase):
    def tdoc(self) -> tables.Tables:
        root = doc(template=True)
        return tables.Tables(root=root, prolog=tables_normal.PROLOG, epilog=tables_normal.EPILOG)

    def test_changes_land_in_place(self) -> None:
        routes = '<routes class="jmri.managers.configurexml.DefaultRouteManagerXml"><route systemName="IO1">' \
                 "<systemName>IO1</systemName></route></routes>"
        store = doc(memories=bean("memory", "IMA", "A"), timebase_rate="4.0", extra=routes)
        p = plan(doc(), doc(), store)
        new = ss.new_template(self.tdoc(), store, ss.template_changes(p, ss.Choices())).root
        tags = [c.tag for c in tables.elements(new)]
        self.assertEqual(tags.index("timebase") + 1, tags.index("routes"))   # where the Store had it
        self.assertEqual("4.0", new.find("timebase").get("rate"))
        self.assertEqual(["IMA", "IMCURRENTTIME"], [tables.system_name(m) for m in new.find("memories")])

    def test_a_dropped_kept_item_stays_out(self) -> None:
        store = doc(memories=bean("memory", "IMA", "A"))
        p = plan(doc(), doc(), store)
        new = ss.new_template(self.tdoc(), store, ss.template_changes(p, ss.Choices(drop=frozenset({"K1"})))).root
        self.assertEqual(["IMCURRENTTIME"], [tables.system_name(m) for m in new.find("memories")])


class Verify(unittest.TestCase):
    def test_a_rebuild_that_gives_the_plan_passes(self) -> None:
        store = doc(timebase_rate="4.0")
        p = plan(doc(), doc(), store)
        self.assertEqual([], ss.verify(p, ss.Choices(), doc(), doc(timebase_rate="4.0"),
                                       doc(template=True, timebase_rate="4.0")))

    def test_a_change_that_did_not_land_or_one_nobody_asked_for_fails(self) -> None:
        store = doc(timebase_rate="4.0")
        p = plan(doc(), doc(), store)
        bad = ss.verify(p, ss.Choices(), doc(), doc(timebase_rate="1.0"), doc(template=True))
        self.assertTrue(any("K1" in b for b in bad), bad)
        bad = ss.verify(p, ss.Choices(), doc(), doc(timebase_rate="4.0", panel_x="99"),
                        doc(template=True, timebase_rate="4.0"))
        self.assertTrue(any("panel" in b for b in bad), bad)


class ReadTemplate(unittest.TestCase):
    def test_an_extra_section_reads_but_a_second_known_one_stops(self) -> None:
        import tempfile
        base = tb.read_template()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.xml"
            root = copy.deepcopy(base.root)
            routes = ET.SubElement(root, "routes", {"class": "jmri.managers.configurexml.DefaultRouteManagerXml"})
            tb.finish(root)
            p.write_bytes(tables.Tables(root=root, prolog=base.prolog, epilog=base.epilog).tobytes())
            tb.read_template(p)
            root.remove(routes)
            root.append(copy.deepcopy(root.find("memories")))
            tb.finish(root)
            p.write_bytes(tables.Tables(root=root, prolog=base.prolog, epilog=base.epilog).tobytes())
            with self.assertRaises(tb.TablesBuildError):
                tb.read_template(p)


def with_version(root: ET.Element, major: str, minor: str = "16") -> ET.Element:
    root = copy.deepcopy(root)
    sec = root.find("jmriversion")
    for kid in list(sec):
        sec.remove(kid)
    for tag, text in (("major", major), ("minor", minor), ("test", "0")):
        ET.SubElement(sec, tag).text = text
    tb.finish(root)
    return root


def with_threads(root: ET.Element, *names: str) -> ET.Element:
    """`root` with a LogixNG section of nameless <Thread> settings, one per name (a tag given more than once)."""
    root = copy.deepcopy(root)
    sec = ET.SubElement(root, "LogixNGs", {"class": "jmri.jmrit.logixng.implementation.configurexml."
                                                    "DefaultLogixNGManagerXml"})
    for name in names:
        t = ET.SubElement(sec, "Thread")
        ET.SubElement(t, "id").text = name[0]           # a thread keeps its id when others come and go
        ET.SubElement(t, "name").text = name
    tb.finish(root)
    return root


class JmriVersion(unittest.TestCase):
    def test_a_newer_jmri_is_always_kept(self) -> None:
        """Even with no base and the repo's version changed since the deploy (a clash for any other setting)."""
        repo = with_version(doc(), "5", "16")
        store = with_version(doc(), "5", "18")
        for base in (None, with_version(doc(), "5", "14")):
            p = plan(base, repo, store, template=with_version(doc(template=True), "5", "16"))
            self.assertEqual({ss.KEPT: ["<jmriversion> <minor>"]}, kinds(p), base)
            self.assertIn("'16' -> '18'", p.by_id()["K1"].what)

    def test_the_same_jmri_gives_no_item(self) -> None:
        repo = with_version(doc(), "5", "16")
        self.assertEqual([], plan(repo, repo, with_version(doc(), "5", "16")).items)

    def test_the_template_takes_the_newer_version(self) -> None:
        template = with_version(doc(template=True), "5", "16")
        tdoc = tables.loads(ET.tostring(template))
        store = with_version(doc(), "6", "0")
        p = plan(None, with_version(doc(), "5", "16"), store, template=template)
        new = ss.new_template(tdoc, store, ss.template_changes(p, ss.Choices()), p.by_content).root
        self.assertEqual(("6", "0"), (new.findtext("jmriversion/major"), new.findtext("jmriversion/minor")))

    def test_an_older_jmri_is_named_and_the_repo_keeps_its_version(self) -> None:
        p = plan(None, with_version(doc(), "5", "16"), with_version(doc(), "5", "14"))
        [item] = p.items
        self.assertEqual(ss.DROPPED, item.kind)
        self.assertIn("older JMRI", item.note)

    def test_a_version_that_is_not_a_number_stops(self) -> None:
        with self.assertRaises(ss.SplitError):
            plan(None, doc(), with_version(doc(), "5", "16beta"))
        with self.assertRaises(ss.SplitError):
            plan(None, doc(), with_version(doc(), "5", "1\u00b2"))


class RepeatedSettings(unittest.TestCase):
    def test_adding_one_in_the_middle_shows_only_that_one(self) -> None:
        """Matched by place, the second and third would both look changed."""
        base = with_threads(doc(), "Main", "Late")
        store = with_threads(doc(), "Main", "Owner", "Late")
        p = plan(base, copy.deepcopy(base), store, template=with_threads(doc(template=True), "Main", "Late"))
        [item] = p.items
        self.assertEqual((ss.KEPT, "added"), (item.kind, item.what))
        self.assertIn("'O'", item.where)          # its id

    def test_a_tag_given_once_still_shows_a_change(self) -> None:
        p = plan(with_threads(doc(), "Main"), with_threads(doc(), "Main"), with_threads(doc(), "Renamed"))
        [item] = p.items
        self.assertIn("'Main' -> 'Renamed'", item.what)

    def test_going_from_one_to_two_keeps_the_first(self) -> None:
        """Every file keys a tag the same way, so the one the base had is not shown as deleted and added again."""
        base = with_threads(doc(), "Main")
        p = plan(base, copy.deepcopy(base), with_threads(doc(), "Main", "Owner"))
        self.assertEqual(["added"], [i.what for i in p.items])

    def test_an_edit_to_one_copy_with_an_id_is_one_change(self) -> None:
        """Threads carry an <id>, so a renamed one is matched by it: one change, not a deletion and an addition."""
        base = with_threads(doc(), "Main", "Late")
        store = copy.deepcopy(base)
        [late] = [t for t in store.iter("Thread") if t.findtext("name") == "Late"]
        late.find("name").text = "Lane"           # the same id, L
        p = plan(base, copy.deepcopy(base), store, template=with_threads(doc(template=True), "Main", "Late"))
        [item] = p.items
        self.assertEqual(ss.KEPT, item.kind)
        self.assertIn("'Late' -> 'Lane'", item.what)
        self.assertIn("'L'", item.where)

    def test_copies_without_ids_are_matched_by_content(self) -> None:
        base, store = doc(), doc()
        for root, names in ((base, ("a", "b")), (store, ("a", "x", "b"))):
            sec = root.find("blocks")
            for n in names:
                ET.SubElement(sec, "defaultspeed").text = n
        p = plan(base, copy.deepcopy(base), store)
        [item] = p.items
        self.assertEqual("added", item.what)
        self.assertIn("(x;", item.where)

    def test_a_deleted_item_the_template_lacks_stops(self) -> None:
        base = with_threads(doc(), "Main", "Late")
        p = plan(base, copy.deepcopy(base), with_threads(doc(), "Main"),
                 template=with_threads(doc(template=True), "Main", "Late"))
        tdoc = tables.loads(ET.tostring(with_threads(doc(template=True), "Main")))
        with self.assertRaises(ss.SplitError):
            ss.new_template(tdoc, doc(), ss.template_changes(p, ss.Choices()), p.by_content)

    def test_a_deleted_one_leaves_the_template_and_the_rest_stays(self) -> None:
        template = with_threads(doc(template=True), "Main", "Owner", "Late")
        tdoc = tables.loads(ET.tostring(template))
        store = with_threads(doc(), "Main", "Late")
        base = with_threads(doc(), "Main", "Owner", "Late")
        p = plan(base, copy.deepcopy(base), store, template=template)
        self.assertEqual(["deleted"], [i.what for i in p.items])
        new = ss.new_template(tdoc, store, ss.template_changes(p, ss.Choices()), p.by_content).root
        self.assertEqual(["Main", "Late"], [t.findtext("name") for t in new.iter("Thread")])
        rebuilt = with_threads(doc(), "Main", "Late")
        self.assertEqual([], ss.verify(p, ss.Choices(), base, rebuilt, new))


class Invariants(unittest.TestCase):
    """The checks plan and verify make on their own records."""

    KEY = ss.BeanKey("bean", tables_sections.LCC_TURNOUTS, "turnout", "bean", "M2T408")

    def test_a_device_draft_with_no_edits_stops(self) -> None:
        draft = sp.Draft(ss.DEVICE, self.KEY, sp.Sides(None, None, None), "userName", "merge writes nothing")
        with self.assertRaisesRegex(ss.SplitError, "device item .* has no edits"):
            sp._numbered([draft])

    def test_a_dropped_draft_with_edits_stops(self) -> None:
        edit = ss.Edit(("1", "x"), "user_name", "a", "b")
        draft = sp.Draft(ss.DROPPED, self.KEY, sp.Sides(None, None, None), "userName", "dropped", edits=(edit,))
        with self.assertRaisesRegex(ss.SplitError, "dropped item .* has 1 edit\\(s\\): only a device item merges"):
            sp._numbered([draft])

    def test_a_merged_rename_of_a_bean_the_store_lacks_is_a_verify_problem(self) -> None:
        item = ss.Item("D1", ss.DEVICE, self.KEY, "userName", "merge writes", store=None,
                       edits=(ss.Edit(("1", "x"), "user_name", "a", "b"),), part="userName")
        p = ss.Plan([item], True, "f")
        bad = ss.verify(p, ss.Choices(merge=frozenset({"D1"})), doc(), doc(), doc(template=True))
        self.assertIn("D1 turnout M2T408: the plan merges a userName of a bean the Store lacks", bad)


if __name__ == "__main__":
    unittest.main()

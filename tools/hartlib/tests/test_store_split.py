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
from hartlib import devices as D, tables  # noqa: E402
from hartlib import store_split as ss  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402

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

    def test_a_new_device_is_dropped_with_the_row_to_add(self) -> None:
        turnouts = (bean("turnout", "MTT100", "DCC Switch 1", "Node: 4 Turnout: 0")
                    + bean("turnout", "M2T408", "Switch 1", "bound by its user name")
                    + bean("turnout", "MTT200", "DCC Switch 9"))
        p = plan(doc(), doc(), doc(turnouts=turnouts))
        [g] = p.of(ss.DROPPED)
        self.assertEqual("added in the Store", g.what)
        self.assertIn("add the devices.csv row", g.note)


class DeviceItems(unittest.TestCase):
    def test_a_hand_kept_comment_is_a_device_merge(self) -> None:
        blocks = bean("block", "IB:AUTO:0033", "OS Switch 1", "Owner note", systemName="IB:AUTO:0033")
        p = plan(doc(), doc(), doc(blocks=blocks))
        [d] = p.of(ss.DEVICE)
        self.assertEqual((ss.Edit(2, "jmri_comment", "Brick CP, Switch 1", "Owner note"),), d.edits)

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

    def test_a_rename_on_both_passes_is_one_question(self) -> None:
        """A block's names-only pass and full pass (and its layout block) carry one rename: one DEVICE item."""
        both = (bean("block", "IB:AUTO:0033", "OS Switch 1A", systemName="IB:AUTO:0033")
                + bean("block", "IB:AUTO:0033", "OS Switch 1A", "Brick CP, Switch 1", systemName="IB:AUTO:0033"))
        before = (bean("block", "IB:AUTO:0033", "OS Switch 1", systemName="IB:AUTO:0033")
                  + bean("block", "IB:AUTO:0033", "OS Switch 1", "Brick CP, Switch 1", systemName="IB:AUTO:0033"))
        p = plan(doc(blocks=before), doc(blocks=before), doc(blocks=both))
        [d] = p.of(ss.DEVICE)
        self.assertEqual(1, len(d.also))
        self.assertEqual([ss.Edit(2, "user_name", "OS Switch 1", "OS Switch 1A")], list(ss.device_edits(
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
            ss.edited_rows(ROWS, [ss.Edit(2, "jmri_comment", "not this", "new")])


class NewTemplate(unittest.TestCase):
    def tdoc(self) -> tables.Tables:
        root = doc(template=True)
        return tables.Tables(root=root, prolog=tb.PROLOG, epilog=tb.EPILOG)

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


if __name__ == "__main__":
    unittest.main()

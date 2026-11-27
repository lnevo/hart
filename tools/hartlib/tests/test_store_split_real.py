"""hartlib.store_split on this checkout's real tables.xml, tables_template.xml and device master: Stores made from
the real tables by known edits, and the kind of item each edit gives. test_store_split.py covers the rules on small
tables; this file checks that they hold on the real file's sections, names and rows.

`scenarios()` is also what a before/after comparison of a refactor runs: `dump()` gives every field of a plan."""
from __future__ import annotations

import copy
import sys
import unittest
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import devices, paths, tables  # noqa: E402
from hartlib import store_split as ss  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402
from hartlib.store_keys import canon  # noqa: E402

STEP = 9            # every STEP-th bean of a device-master section is edited
NEW_TURNOUT = "MTT9901"
NEW_BLOCK = "IB:AUTO:9901"
NEW_LAYOUT_BLOCK = "ILB9901"
LONE_LAYOUT_BLOCK = "ILB9902"
NEW_MEMORY = "IMSPLITTEST"


class Real(NamedTuple):
    repo: ET.Element
    template: ET.Element
    rows: list[dict[str, str]]


class Scenario(NamedTuple):
    name: str
    base: ET.Element | None
    repo: ET.Element
    store: ET.Element
    rows: list[dict[str, str]]


def load_real() -> Real:
    repo = ss.normalised(paths.REPO_TABLES_XML.read_bytes(), "tables.xml")
    template = ss.normalised(tb.read_template(tb.TEMPLATE).tobytes(), "the template")
    return Real(repo, template, [r.cells() for r in devices.load(devices.Files.here())])


def section(root: ET.Element, sk: tuple[str, str | None]) -> ET.Element:
    got = [s for s in tables.elements(root) if s.tag != ss.PANEL and tb.section_key(s) == sk]
    if len(got) != 1:
        raise AssertionError(f"{len(got)} sections {sk} in the real tables")
    return got[0]


def beans(sec: ET.Element) -> list[ET.Element]:
    return [el for el in tables.elements(sec) if tables.system_name(el)]


def set_child(el: ET.Element, tag: str, text: str) -> None:
    kid = el.find(tag)
    if kid is None:
        kid = ET.SubElement(el, tag)
    kid.text = text


def new_bean(tag: str, system: str, user: str, **attrs: str) -> ET.Element:
    el = ET.Element(tag, attrs)
    ET.SubElement(el, "systemName").text = system
    ET.SubElement(el, "userName").text = user
    return el


def edited(root: ET.Element, *edits: Callable[[ET.Element], None]) -> ET.Element:
    out = copy.deepcopy(root)
    for edit in edits:
        edit(out)
    tb.normalise_store(out)
    return out


def bean_edits(root: ET.Element) -> None:
    """Rename, re-comment or delete every STEP-th bean of each device-master section (offsets 0, 3 and 6)."""
    for sk in tb.MASTER_SECTIONS:
        sec = section(root, sk)
        for n, el in enumerate(beans(sec)):
            if n % STEP == 0:
                set_child(el, "userName", (tables.user_name(el) or "unnamed") + " X")
            elif n % STEP == 3 and tb.sort_group(el) != "block-names":     # a names-only pass has no comment
                set_child(el, "comment", f"owner note {n}")
            elif n % STEP == 6:
                sec.remove(el)


def added_devices(root: ET.Element) -> None:
    """A new turnout, a new block with its layout block, and a layout block with no block."""
    section(root, tb.LCC_TURNOUTS).append(new_bean("turnout", NEW_TURNOUT, "Yard Lead Test", feedback="DIRECT"))
    blocks = section(root, tb.BLOCKS)
    blocks.append(new_bean("block", NEW_BLOCK, "Test Siding", systemName=NEW_BLOCK))
    full = new_bean("block", NEW_BLOCK, "Test Siding", systemName=NEW_BLOCK, length="100.0", curve="0")
    ET.SubElement(full, "permissive").text = "no"
    blocks.append(full)
    section(root, tb.LAYOUT_BLOCKS).append(new_bean("layoutblock", NEW_LAYOUT_BLOCK, "Test Siding",
                                                    systemName=NEW_LAYOUT_BLOCK))
    section(root, tb.LAYOUT_BLOCKS).append(new_bean("layoutblock", LONE_LAYOUT_BLOCK, "Nowhere Block",
                                                    systemName=LONE_LAYOUT_BLOCK))


def template_edits(root: ET.Element) -> None:
    """A new memory, the clock rate, a block default, and an extra section."""
    memories = next(s for s in tables.elements(root) if s.tag == "memories")
    memories.append(new_bean("memory", NEW_MEMORY, "Split test"))
    next(s for s in tables.elements(root) if s.tag == "timebase").set("rate", "4.0")
    set_child(section(root, tb.BLOCKS), "defaultspeed", "Restricted")
    ET.SubElement(root, "extrathing", {"class": "test.ExtraXml"}).text = "x"


def build_edits(root: ET.Element) -> None:
    """The first panel's first attribute, the first Signal Mast Logic, and the JMRI version."""
    panel = next(s for s in tables.elements(root) if s.tag == ss.PANEL)
    panel.set("xloc", "1234")
    logic = next(el for el in root.iter(ss.LOGIC))
    set_child(logic, "enabled", "no")
    set_child(root.find("jmriversion"), "minor", "99")      # type: ignore[arg-type]


def repo_since_base(root: ET.Element) -> None:
    """What the repo changed since the deploy: the clock rate (so the Store's rate is a clash)."""
    next(s for s in tables.elements(root) if s.tag == "timebase").set("rate", "2.0")


def unplaced_rows(real: Real) -> tuple[ET.Element, list[dict[str, str]]]:
    """The repo and rows after a merge of the added turnout and block: each a level-less row, its beans built."""
    store = edited(real.repo, added_devices)
    p = ss.plan(real.repo, real.repo, store, real.template, real.rows)
    adds = [e for i in p.of(ss.DEVICE) for e in i.edits if isinstance(e, ss.RowAdd)]
    if len(adds) != 2:
        raise AssertionError(f"{len(adds)} rows added, not 2")
    rows = real.rows + [e.row for e in adds]
    return edited(real.repo, added_devices, lambda r: section(r, tb.LAYOUT_BLOCKS).remove(
        next(el for el in beans(section(r, tb.LAYOUT_BLOCKS)) if tables.system_name(el) == LONE_LAYOUT_BLOCK))), rows


def unplaced_edits(root: ET.Element) -> None:
    """Rename the level-less block, re-feedback the level-less turnout."""
    for el in beans(section(root, tb.BLOCKS)):
        if tables.system_name(el) == NEW_BLOCK:
            set_child(el, "userName", "Test Siding 2")
    for el in beans(section(root, tb.LCC_TURNOUTS)):
        if tables.system_name(el) == NEW_TURNOUT:
            el.set("feedback", "ONESENSOR")


def unplaced_delete(root: ET.Element) -> None:
    sec = section(root, tb.LCC_TURNOUTS)
    sec.remove(next(el for el in beans(sec) if tables.system_name(el) == NEW_TURNOUT))


def scenarios(real: Real) -> list[Scenario]:
    every = (bean_edits, added_devices, template_edits, build_edits)
    base = edited(real.repo, lambda r: None)
    old_base = edited(real.repo, repo_since_base)
    placed_repo, placed_rows = unplaced_rows(real)
    return [
        Scenario("same", base, real.repo, edited(real.repo, lambda r: None), real.rows),
        Scenario("base", base, real.repo, edited(real.repo, *every), real.rows),
        Scenario("no-base", None, real.repo, edited(real.repo, *every), real.rows),
        Scenario("repo-moved", old_base, real.repo, edited(old_base, *every), real.rows),
        Scenario("unplaced", placed_repo, placed_repo, edited(placed_repo, unplaced_edits), placed_rows),
        Scenario("unplaced-delete", placed_repo, placed_repo, edited(placed_repo, unplaced_delete), placed_rows),
        Scenario("older-jmri", base, real.repo, edited(real.repo, lambda r: set_child(
            r.find("jmriversion"), "major", "1")), real.rows),                 # type: ignore[arg-type]
        # every row as if the owner wrote it, so renames and comments reach the DEVICE rules
        Scenario("owner-rows", base, real.repo, edited(real.repo, bean_edits),
                 [{**r, "written_by": ""} for r in real.rows]),
    ]


def plan_of(real: Real, s: Scenario) -> ss.Plan:
    return ss.plan(s.base, s.repo, s.store, real.template, s.rows)


def dump(p: ss.Plan) -> dict[str, object]:
    """Every field of a plan as plain data, the elements by their canonical text."""
    return {
        "fingerprint": p.fingerprint, "has_base": p.has_base, "by_content": sorted(map(repr, p.by_content)),
        "items": [[i.id, i.kind, repr(i.key), i.what, i.note, repr(i.edits), i.part,
                   [[repr(k), canon(el)] for k, el in i.also], canon(i.store), canon(i.repo), canon(i.base)]
                  for i in p.items],
        "report": ss.report(p, verbose=True),
    }


def bean_name(k: ss.ItemKey) -> str:
    """A device item's bean key's system name (a device item is always a bean's)."""
    assert isinstance(k, ss.BeanKey), k
    return k.name


def kind_of(p: ss.Plan) -> Mapping[ss.ItemKey, str]:
    out: dict[ss.ItemKey, str] = {}
    for i in p.items:
        out.setdefault(i.key, i.kind)
    return out


class RealTables(unittest.TestCase):
    real: Real
    plans: dict[str, ss.Plan]

    @classmethod
    def setUpClass(cls) -> None:
        cls.real = load_real()
        cls.plans = {s.name: plan_of(cls.real, s) for s in scenarios(cls.real)}

    def keys(self, name: str, kind: str) -> list[ss.ItemKey]:
        return [i.key for i in self.plans[name].of(kind)]

    def test_a_store_of_the_tables_plans_nothing(self) -> None:
        self.assertEqual([], self.plans["same"].items)

    def test_the_plan_is_the_same_each_time(self) -> None:
        again = plan_of(self.real, scenarios(self.real)[1])
        self.assertEqual(dump(self.plans["base"]), dump(again))

    def test_template_edits_are_kept_with_a_base_and_clash_without(self) -> None:
        for name, kind in (("base", ss.KEPT), ("no-base", ss.CLASH)):
            got = {ss.label(k) for k in self.keys(name, kind)}
            self.assertIn("<timebase> settings", got, name)
            self.assertIn(f"memory {NEW_MEMORY}", got, name)
            self.assertIn("<blocks> <defaultspeed>", got, name)
            self.assertIn("section <extrathing> (ExtraXml)", got, name)

    def test_a_setting_the_repo_changed_since_the_base_is_a_clash(self) -> None:
        self.assertEqual(["<timebase> settings"], [ss.label(k) for k in self.keys("repo-moved", ss.CLASH)])

    def test_the_newer_jmri_is_kept_and_an_older_one_dropped(self) -> None:
        self.assertIn(("jmriversion", None), [k[1] for k in self.keys("base", ss.KEPT)])
        self.assertEqual([("jmriversion", None)], [k[1] for k in self.keys("older-jmri", ss.DROPPED)])

    def test_the_build_items_are_dropped(self) -> None:
        dropped = self.keys("base", ss.DROPPED)
        self.assertTrue(any(isinstance(k, ss.PanelKey) for k in dropped))
        self.assertTrue(any(isinstance(k, ss.LogicKey) for k in dropped))
        self.assertIn(LONE_LAYOUT_BLOCK, [k.name for k in dropped if isinstance(k, ss.BeanKey)])

    def test_every_edited_bean_gives_one_item(self) -> None:
        kinds = kind_of(self.plans["base"])
        also = {k for i in self.plans["base"].items for k, _ in i.also}
        for sk in tb.MASTER_SECTIONS:
            for n, el in enumerate(beans(section(self.real.repo, sk))):
                if n % STEP not in (0, 3, 6) or (n % STEP == 3 and tb.sort_group(el) == "block-names"):
                    continue
                key = ss.BeanKey("bean", sk, el.tag, tb.sort_group(el), tables.system_name(el))
                self.assertTrue(key in kinds or key in also, ss.label(key))
                if n % STEP == 6 and key in kinds:
                    self.assertEqual(ss.DROPPED, kinds[key], ss.label(key))

    def test_a_rename_on_an_owners_row_is_a_device_merge_of_its_user_name(self) -> None:
        renames = [i for i in self.plans["owner-rows"].of(ss.DEVICE) if i.part == "userName"]
        self.assertTrue(renames)
        for i in renames:
            edit = i.edits[0]
            assert isinstance(edit, ss.Edit), i.where
            self.assertEqual("user_name", edit.column, i.where)
            self.assertTrue(edit.new.endswith(" X"), i.where)

    def test_the_added_turnout_and_block_are_rows_to_add(self) -> None:
        adds = [i for i in self.plans["base"].of(ss.DEVICE) if i.part == ss.ROW]
        self.assertEqual({NEW_TURNOUT, NEW_BLOCK}, {bean_name(i.key) for i in adds})
        block = next(i for i in adds if bean_name(i.key) == NEW_BLOCK)
        self.assertEqual([NEW_BLOCK, NEW_LAYOUT_BLOCK], [bean_name(k) for k, _ in block.also])     # its other pass too

    def test_a_level_less_device_changed_or_deleted_rewrites_or_deletes_its_row(self) -> None:
        rewrites = self.plans["unplaced"].of(ss.DEVICE)
        self.assertEqual({NEW_TURNOUT, NEW_BLOCK}, {bean_name(i.key) for i in rewrites})
        self.assertTrue(all(isinstance(e, ss.Edit) for i in rewrites for e in i.edits))
        deleted = self.plans["unplaced-delete"].of(ss.DEVICE)
        self.assertEqual([[ss.RowDelete]], [[type(e) for e in i.edits] for i in deleted])


if __name__ == "__main__":
    unittest.main()

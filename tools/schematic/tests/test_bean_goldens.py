"""Golden tests of the beans of every level, which one process makes: hartlib.tables_build.master_beans from the
device master's rows (naming-layers step 11; ADR-033 steps 1, 10 and 11).

They pin the beans against the committed tables.xml, so a change to a row, a builder or the bean process shows any
byte it changes:

- the template with every level's master beans (tables_build.base) is the committed tables.xml's own manager sections,
  but what JMRI and discovery derive (block paths, mast properties);
- every main and upper bean of the committed tables.xml (a bean of a main or upper row: le_tables.level_bean_names)
  is in fixtures/main_upper_beans.txt, line for line, and base() makes exactly those lines;
- every main and upper device row has the beans its layer and role give, and every main and upper bean has a row;
- each main and upper bean's comment is its row's bean_comment, and the startup LogixNG sets each row's start;
- staging's beans are the same made with or without the other levels, but for the helix blocks' sensor.

A change to a main or upper bean that a PR means to make (a listed tables.xml diff) rewrites the fixture with
    python3 tools/schematic/tests/test_bean_goldens.py --write
and the PR shows the fixture's diff. What JMRI or discovery derives (block paths, Signal Mast Logic, the
intermediateSignal property) is left out: those change on a rediscovery, not in the bean process."""
from __future__ import annotations

import copy
import dataclasses
import difflib
import sys
import unittest
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import le_tables as lt  # noqa: E402
from hartlib import block_lengths, devices, level_devices, paths, railroad, startup_logixng, tables, tables_sections  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "main_upper_beans.txt"
WRITE = "python3 tools/schematic/tests/test_bean_goldens.py --write"
DERIVED = ("path", "properties")      # block paths (PanelPro) and mast properties (discovery): not a bean process's
LOGIXNG = ("LogixNG", "ConditionalNG", "DigitalMany", "ActionSensor", "ActionTurnout")
LEVELS = level_devices.LEVELS
HELIX = ("Track Helix Inner", "Track Helix Outer")     # staging blocks with a row on every level they climb through
# The sections a bean of the master lands in: the master's own and the template's that take master beans too
BEAN_SECTIONS = tables_sections.MASTER_SECTIONS + (tables_sections.INTERNAL_SENSORS, tables_sections.LOGIXNGS,
                                      tables_sections.CONDITIONALNGS, tables_sections.DIGITAL_ACTIONS)


def committed() -> ET.Element:
    return tables.loads(paths.REPO_TABLES_XML.read_bytes()).root


def bean_text(el: ET.Element) -> str:
    """A bean on one line, without layout whitespace or what JMRI and discovery derive (DERIVED)."""
    e = copy.deepcopy(el)
    for tag in DERIVED:
        for c in e.findall(tag):
            e.remove(c)
    return lt.canon(e)


def section_of(sec: ET.Element) -> str:
    return f"{sec.tag} {(sec.get('class') or '').rsplit('.', 1)[-1]}".strip()


def golden_lines(root: ET.Element, names: set[str] | None = None) -> list[str]:
    """Every main and upper bean of tables `root` (le_tables.is_level_bean over `names`, default the device master's
    level_bean_names), in the tables' order, as "<section> <manager class>\\t<bean>", then each staging block and
    layout block whose occupancy sensor is a main and upper one (a helix block), as "detector\\t<tag> <system
    name>\\t<sensor>"."""
    names = lt.level_bean_names() if names is None else names
    out = [f"{section_of(sec)}\t{bean_text(el)}" for sec in tables.elements(root) for el in tables.elements(sec)
           if lt.is_level_bean(el, names)]
    level = {tables.user_name(s) for s in tables.sensors(root) if lt.is_level_bean(s, names)}
    for b in tables.blocks(root):
        if not lt.is_level_bean(b, names) and (b.findtext("occupancysensor") or "").strip() in level:
            out.append(f"detector\tblock {tables.system_name(b)}\t{b.findtext('occupancysensor').strip()}")
    for lb in tables.layout_blocks(root):
        if not lt.is_level_bean(lb, names) and (lb.get("occupancysensor") or "") in level:
            out.append(f"detector\tlayoutblock {tables.system_name(lb)}\t{lb.get('occupancysensor')}")
    return out


def read_fixture() -> list[str]:
    return FIXTURE.read_text(encoding="utf-8").splitlines()


def diff(want: list[str], got: list[str]) -> str:
    lines = list(difflib.unified_diff(want, got, "fixture", "tables.xml", n=0, lineterm=""))
    return "\n".join(lines[:40] + ([f"... {len(lines) - 40} more lines"] if len(lines) > 40 else []))


class EveryLevelBeans(unittest.TestCase):
    """base() (the template, every level's master beans and the startup LogixNG) against the committed tables.xml."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.base = tb.base().root
        tables_sections.jmri_sort(cls.base)              # the order build_tables.py writes

    def test_the_template_and_master_beans_are_the_committed_bean_sections(self) -> None:
        built = {section_of(s): s for s in tables.elements(self.base)}
        live = {section_of(s): s for s in tables.elements(committed())}
        for key in BEAN_SECTIONS:
            name = f"{key[0]} {key[1].rsplit('.', 1)[-1]}"
            with self.subTest(section=name):
                want = [bean_text(el) for el in tables.elements(live[name])]
                got = [bean_text(el) for el in tables.elements(built[name])]
                self.assertTrue(want, name)
                self.assertEqual(want, got, diff(want, got))

    def test_base_makes_the_fixtures_main_and_upper_beans(self) -> None:
        got = golden_lines(self.base)
        self.assertEqual(read_fixture(), got, diff(read_fixture(), got))

    def test_master_beans_makes_every_levels_beans(self) -> None:
        """No level is left to another process (GENERATED_LEVELS went in step 11): every main and upper row's names
        are among master_beans' beans."""
        rows = [r.cells() for r in devices.load()]
        made = {n for els in tb.master_beans(rows, block_lengths.operating_lengths(tb.BLOCK_LENGTHS)).values()
                for el in els for n in (tables.system_name(el), tables.user_name(el))}
        level = {n for r in rows if r["level"] in LEVELS and r["assignment"] != "none" and r["role"] != "lcc_alias"
                 for n in (r["user_name"], tb.bean_name(r)) if n}
        self.assertTrue(level)
        self.assertEqual(set(), level - made)


class MainUpperBeans(unittest.TestCase):
    """The main and upper beans as the committed tables.xml holds them."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = committed()
        cls.golden = read_fixture()
        cls.names = lt.level_bean_names()

    def test_the_committed_tables_hold_the_fixtures_beans(self) -> None:
        got = golden_lines(self.root, self.names)
        self.assertEqual(self.golden, got, f"main and upper beans changed; if the PR means it, run {WRITE}\n"
                         + diff(self.golden, got))

    def test_the_fixture_holds_every_kind(self) -> None:
        kinds = Counter(line.split("\t", 1)[0] for line in self.golden)
        for kind in ("turnouts InternalTurnoutManagerXml", "sensors InternalSensorManagerXml", "blocks BlockManagerXml",
                     "layoutblocks LayoutBlockManagerXml", "signalheads AbstractSignalHeadManagerXml",
                     "signalmasts DefaultSignalMastManagerXml", "LogixNGs DefaultLogixNGManagerXml", "detector"):
            self.assertIn(kind, kinds)

    def test_every_main_and_upper_row_has_its_beans_and_every_bean_its_row(self) -> None:
        """The row-to-bean map: a switch one internal turnout, its LCC alias and feedback rows
        none (DIRECT feedback); a block (part or not) a names-only and a full block and a layout block, except a
        helix block, which is staging's bean; a detector one internal sensor; a head and a mast one bean each."""
        rows = [r for r in devices.load() if r.level_cell in LEVELS]
        got = Counter()
        for sec in tables.elements(self.root):
            for el in tables.elements(sec):
                if lt.is_level_bean(el, self.names) and el.tag not in LOGIXNG:
                    got[(el.tag, tables.user_name(el))] += 1
        want = Counter()
        for r in rows:
            layer, user = r.layer, r.user_name
            if layer == "turnout" and r.role == "turnout":
                want[("turnout", user)] += 1
            elif layer == "block" and user not in HELIX:
                want[("block", user)] += 2
                want[("layoutblock", user)] += 1
            elif layer == "occupancy":
                want[("sensor", user)] += 1
            elif layer == "head":
                want[("signalhead", user)] += 1
            elif layer == "mast":
                tag = "virtualsignalmast" if r.jmri_name.startswith("IF$vsm:") else "signalmast"
                want[(tag, user)] += 1
        self.assertEqual(sorted((want - got).items()), [], "rows with no bean")
        self.assertEqual(sorted((got - want).items()), [], "beans with no row")

    def test_every_turnout_and_detector_starts_clear_or_set(self) -> None:
        """The startup LogixNG: one ActionTurnout per main and upper turnout and one ActionSensor per block sensor."""
        kinds = Counter(ET.fromstring(line.split("\t", 1)[1]).tag for line in self.golden
                        if line.startswith("LogixNGDigitalActions"))
        beans = Counter(line.split("\t", 1)[0] for line in self.golden)
        self.assertEqual(kinds["ActionTurnout"], beans["turnouts InternalTurnoutManagerXml"])
        self.assertEqual(kinds["ActionSensor"], beans["sensors InternalSensorManagerXml"])

    def test_a_main_or_upper_bean_is_found_by_its_row_not_its_name(self) -> None:
        """is_level_bean reads the rows: a turnout row bound to a physical name (a swap, ADR-028) is still a main or
        upper bean, and a staging bean is not one."""
        rows = [dataclasses.replace(r, jmri_name="M2T3308", assignment="field", start="")
                if r.id == "switch:107" and r.level == 2 else r for r in devices.load()]
        names = lt.level_bean_names(rows=rows)
        turnout = ET.fromstring("<turnout><systemName>M2T3308</systemName><userName>Switch 107</userName></turnout>")
        self.assertTrue(lt.is_level_bean(turnout, names))
        staging = ET.fromstring("<turnout><systemName>M2T408</systemName><userName>Switch 1</userName></turnout>")
        self.assertFalse(lt.is_level_bean(staging, names))


class RowCellsAreTheGoldenBeans(unittest.TestCase):
    """The start and bean_comment cells build_device_map.py writes on every main and upper row (naming-layers steps 9
    and 11) are what the fixture's beans hold: each bean's comment is its row's bean_comment, and the startup LogixNG
    sets each turnout and sensor to its row's start."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = [r.cells() for r in devices.load() if r.level_cell in LEVELS]
        cls.beans = [(line.split("\t", 1)[0], ET.fromstring(line.split("\t", 1)[1])) for line in read_fixture()
                     if not line.startswith("detector")]

    def test_every_beans_comment_is_its_rows_bean_comment(self) -> None:
        layer = {"turnout": "turnout", "sensor": "occupancy", "block": "block", "signalhead": "head",
                 "signalmast": "mast", "virtualsignalmast": "mast"}
        cells = {(r["layer"], r["user_name"]): r["bean_comment"] for r in self.rows if r["bean_comment"]}
        got, seen = {}, set()
        for _sec, el in self.beans:
            if el.tag not in layer or el.find("comment") is None:
                continue                # a names-only block pass and a layout block carry no comment
            key = (layer[el.tag], tables.user_name(el))
            seen.add(key)
            got[key] = el.findtext("comment")
        self.assertEqual(len(got), 39 + 120 + 97 + 76 + 68)
        bad = [f"{k}: tables.xml {got[k]!r}, row {cells.get(k)!r}" for k in sorted(got) if cells.get(k) != got[k]]
        self.assertEqual([], bad[:10], f"{len(bad)} beans")
        self.assertEqual(sorted(set(cells) - seen), [], "rows with a bean_comment and no bean")

    def test_the_comments_are_in_stagings_form(self) -> None:
        """Staging's words: no main and upper comment names a build script or the old
        "virtual (device map)" note; a bean no field device drives says level_devices.VIRTUAL_NOTE, as a staging
        head on an internal name does; a block names its detector first."""
        for r in self.rows:
            c = r["bean_comment"]
            if not c:
                continue
            with self.subTest(row=r["user_name"]):
                self.assertNotIn(".py", c)
                self.assertNotIn("device map", c)
                if r["layer"] in ("turnout", "occupancy", "head"):
                    self.assertIn(f"| {level_devices.VIRTUAL_NOTE}" if r["layer"] != "occupancy"
                                  else level_devices.VIRTUAL_NOTE, c)
                if r["layer"] == "block":
                    self.assertRegex(c, r"^BS .+ / IS:HART:C3:B:")

    def test_the_startup_logixng_sets_each_rows_start(self) -> None:
        actions = [el for sec, el in self.beans if el.tag in ("ActionTurnout", "ActionSensor")]
        got = {a.findtext("namedBean/name"): a.findtext("state/enum") for a in actions}
        want = {r["jmri_name"]: level_devices.START_ENUM[r["start"]] for r in self.rows if r["start"]}
        self.assertEqual(len(want), 39 + 97)
        self.assertEqual(want, got)
        self.assertEqual({r["user_name"] for r in self.rows if r["start"] == "thrown"}, {"Switch 227", "Switch 229"})

    def test_bean_cells_on_the_rows_as_generated_are_the_committed_cells(self) -> None:
        """device_map_rows.bean_cells, given the committed rows with the two cells emptied and the committed thrown
        switches, writes back the committed cells (no plugin needed)."""
        import device_map_rows
        thrown = frozenset(r["id"].removeprefix("switch:") for r in self.rows if r["start"] == "thrown")
        blank = [r.cells() | {"start": "", "bean_comment": ""} for r in devices.load()]
        got = device_map_rows.bean_cells(blank, thrown)
        want = [r.cells() for r in devices.load()]
        self.assertEqual([(r["start"], r["bean_comment"]) for r in want], [(r["start"], r["bean_comment"]) for r in got])
        self.assertFalse(any(r["start"] or r["bean_comment"] for r in got if r["level"] not in LEVELS))


class StagingAlone(unittest.TestCase):
    """Staging's beans made with the other levels are the ones made alone, but for the helix blocks' sensor (the
    main or upper helix detector binds staging's helix block)."""

    def test_staging_beans_are_the_same_but_the_helix_blocks_sensor(self) -> None:
        rows = devices.load()
        cells = [r.cells() for r in rows]
        lengths = block_lengths.operating_lengths(tb.BLOCK_LENGTHS)
        every = tb.master_beans(cells, lengths)
        alone = tb.master_beans(cells, lengths, (railroad.STAGING_LEVEL,))
        names = lt.level_bean_names(rows=rows)
        for key, els in alone.items():
            with self.subTest(section=key):
                level = [bean_text(el) for el in every[key] if not lt.is_level_bean(el, names)]
                mine = [bean_text(el) for el in els]
                helix = [i for i, (a, b) in enumerate(zip(mine, level)) if a != b]
                self.assertEqual(len(mine), len(level))
                got = {tables.user_name(els[i]) for i in helix}
                self.assertLessEqual(got, set(HELIX), diff(mine, level))
                if key in (tables_sections.BLOCKS, tables_sections.LAYOUT_BLOCKS):
                    self.assertEqual(set(HELIX), got)

    def test_the_startup_actions_come_in_the_frames_socket_order(self) -> None:
        """start_logixng numbers the DigitalMany's sockets A1, A2, ... in master_beans' order."""
        fixture = [ET.fromstring(line.split("\t", 1)[1]) for line in read_fixture()
                   if line.startswith("LogixNGDigitalActions")]
        many = next(e for e in fixture if e.tag == "DigitalMany")
        sockets = [s.findtext("systemName") for s in many.find("Actions")]
        actions = tb.master_beans([r.cells() for r in devices.load()],
                                  block_lengths.operating_lengths(tb.BLOCK_LENGTHS))[startup_logixng.START_ACTIONS]
        self.assertEqual(sockets, [a.findtext("systemName") for a in actions])


def write() -> None:
    FIXTURE.parent.mkdir(exist_ok=True)
    lines = golden_lines(committed())
    FIXTURE.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    print(f"{paths.rel(FIXTURE)}: {len(lines)} lines")


if __name__ == "__main__":
    if sys.argv[1:] == ["--write"]:
        write()
    else:
        unittest.main()

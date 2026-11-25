"""Golden tests of the beans the two bean processes make, before the builder merge moves them (ADR-033 step 1).

Staging's beans come from hartlib.tables_build.master_beans; main and upper's from le_tables.add_level_* while the
Layout Editor build draws the panel. These tests pin both against the committed tables.xml, so a later step that moves
a bean from one process to the other shows any byte it changes:

- the template with the master's beans (tables_build.base) is the committed tables.xml's own manager sections once
  what the Layout Editor build and discovery add is taken out (le_tables.strip_build_owned, block paths, mast
  properties);
- every main and upper bean of the committed tables.xml is in fixtures/main_upper_beans.txt, line for line;
- add_level_signals, run on masts.csv alone (no plugin), makes the fixture's heads and masts;
- every main and upper device row has the beans its layer and role give, and every main and upper bean has a row;
- the two block length formats (le_tables.r1 and master_beans) agree.

A change to a main or upper bean that a PR means to make (a listed tables.xml diff) rewrites the fixture with
    python3 tools/schematic/tests/test_bean_goldens.py --write
and the PR shows the fixture's diff. What JMRI or discovery derives (block paths, Signal Mast Logic, the
intermediateSignal property) is left out: those change on a rediscovery, not in a bean process."""
from __future__ import annotations

import copy
import difflib
import sys
import unittest
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import le_names  # noqa: E402
import le_tables as lt  # noqa: E402
from hartlib import devices, paths, railroad, tables  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "main_upper_beans.txt"
WRITE = "python3 tools/schematic/tests/test_bean_goldens.py --write"
DERIVED = ("path", "properties")      # block paths (PanelPro) and mast properties (discovery): not a bean process's
LOGIXNG = ("LogixNG", "ConditionalNG", "DigitalMany", "ActionSensor", "ActionTurnout")
LEVELS = ("2", "3")
HELIX = ("Track Helix Inner", "Track Helix Outer")     # staging blocks with a row on every level they climb through


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


def golden_lines(root: ET.Element) -> list[str]:
    """Every main and upper bean of tables `root` (le_tables.is_level_bean), in the tables' order, as
    "<section> <manager class>\\t<bean>", then each staging block and layout block whose occupancy sensor is a main
    and upper one (a helix block, which add_level_objects binds), as "detector\\t<tag> <system name>\\t<sensor>"."""
    out = [f"{section_of(sec)}\t{bean_text(el)}" for sec in tables.elements(root) for el in tables.elements(sec)
           if lt.is_level_bean(el)]
    level = lt.level_names(root)
    for b in tables.blocks(root):
        if not lt.is_level_bean(b) and (b.findtext("occupancysensor") or "").strip() in level:
            out.append(f"detector\tblock {tables.system_name(b)}\t{b.findtext('occupancysensor').strip()}")
    for lb in tables.layout_blocks(root):
        if not lt.is_level_bean(lb) and (lb.get("occupancysensor") or "") in level:
            out.append(f"detector\tlayoutblock {tables.system_name(lb)}\t{lb.get('occupancysensor')}")
    return out


def read_fixture() -> list[str]:
    return FIXTURE.read_text(encoding="utf-8").splitlines()


def diff(want: list[str], got: list[str]) -> str:
    lines = list(difflib.unified_diff(want, got, "fixture", "tables.xml", n=0, lineterm=""))
    return "\n".join(lines[:40] + ([f"... {len(lines) - 40} more lines"] if len(lines) > 40 else []))


class StagingBeans(unittest.TestCase):
    """master_beans (through base: the template and the level-less beans too) against the committed tables.xml."""

    def test_the_template_and_master_beans_are_the_committed_manager_sections(self) -> None:
        built = {section_of(s): s for s in tables.elements(tb.base().root)}
        live_root = committed()
        lt.strip_build_owned(live_root)
        live = {section_of(s): s for s in tables.elements(live_root)}
        for key in tb.MASTER_SECTIONS:
            name = f"{key[0]} {key[1].rsplit('.', 1)[-1]}"
            with self.subTest(section=name):
                want = [bean_text(el) for el in tables.elements(live[name])]
                got = [bean_text(el) for el in tables.elements(built[name])]
                self.assertTrue(want, name)
                self.assertEqual(want, got, diff(want, got))

    def test_only_staging_rows_make_master_beans(self) -> None:
        """GENERATED_LEVELS today: a main or upper row gives master_beans no bean (step 11 changes this)."""
        rows = devices.load()
        lengths = railroad.read_block_lengths(tb.BLOCK_LENGTHS)
        made = {n for els in tb.master_beans(rows, lengths).values() for el in els
                for n in (tables.system_name(el), tables.user_name(el))}
        level = {n for r in rows if r["level"] in LEVELS and r["user_name"] not in HELIX
                 for n in (r["user_name"], r["jmri_name"]) if n}
        self.assertTrue(level)
        self.assertEqual(set(), made & level)


class MainUpperBeans(unittest.TestCase):
    """The beans the Layout Editor build adds for main and upper (le_tables.add_level_objects, add_level_sensors,
    add_level_clear, add_level_signals), as the committed tables.xml holds them."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = committed()
        cls.golden = read_fixture()

    def test_the_committed_tables_hold_the_fixtures_beans(self) -> None:
        got = golden_lines(self.root)
        self.assertEqual(self.golden, got, f"main and upper beans changed; if the PR means it, run {WRITE}\n"
                         + diff(self.golden, got))

    def test_the_fixture_holds_every_kind(self) -> None:
        kinds = Counter(line.split("\t", 1)[0] for line in self.golden)
        for kind in ("turnouts InternalTurnoutManagerXml", "sensors InternalSensorManagerXml", "blocks BlockManagerXml",
                     "layoutblocks LayoutBlockManagerXml", "signalheads AbstractSignalHeadManagerXml",
                     "signalmasts DefaultSignalMastManagerXml", "LogixNGs DefaultLogixNGManagerXml", "detector"):
            self.assertIn(kind, kinds)

    def test_add_level_signals_makes_the_fixtures_heads_and_masts_from_masts_csv(self) -> None:
        root = tb.base().root
        lt.add_level_signals(root, le_names.read_level_masts())
        # in order: base() and add_level_signals leave each section in JMRI order, as the build writes it
        tb.jmri_sort(root)
        got = [line for line in golden_lines(root) if line.startswith(("signalheads", "signalmasts"))]
        want = [line for line in self.golden if line.startswith(("signalheads", "signalmasts"))]
        self.assertEqual(want, got, diff(want, got))

    def test_every_main_and_upper_row_has_its_beans_and_every_bean_its_row(self) -> None:
        """The map step 11 keeps when master_beans makes these beans: a switch one internal turnout, its LCC alias
        and feedback rows none (DIRECT feedback); a block (part or not, assignment none) a names-only and a full block
        and a layout block, except a helix block, which is staging's bean; a detector one internal sensor; a head and
        a mast one bean each."""
        rows = [r for r in devices.load() if r["level"] in LEVELS]
        got = Counter()
        for sec in tables.elements(self.root):
            for el in tables.elements(sec):
                if lt.is_level_bean(el) and el.tag not in LOGIXNG:
                    got[(el.tag, tables.user_name(el))] += 1
        want = Counter()
        for r in rows:
            layer, user = r["layer"], r["user_name"]
            if layer == "turnout" and r["role"] == "turnout":
                want[("turnout", user)] += 1
            elif layer == "block" and user not in HELIX:
                want[("block", user)] += 2
                want[("layoutblock", user)] += 1
            elif layer == "occupancy":
                want[("sensor", user)] += 1
            elif layer == "head":
                want[("signalhead", user)] += 1
            elif layer == "mast":
                tag = "virtualsignalmast" if r["jmri_name"].startswith("IF$vsm:") else "signalmast"
                want[(tag, user)] += 1
        self.assertEqual(sorted((want - got).items()), [], "rows with no bean")
        self.assertEqual(sorted((got - want).items()), [], "beans with no row")

    def test_every_added_turnout_and_detector_starts_clear_or_set(self) -> None:
        """add_level_clear: one ActionTurnout per main and upper turnout and one ActionSensor per block sensor."""
        kinds = Counter(ET.fromstring(line.split("\t", 1)[1]).tag for line in self.golden
                        if line.startswith("LogixNGDigitalActions"))
        beans = Counter(line.split("\t", 1)[0] for line in self.golden)
        self.assertEqual(kinds["ActionTurnout"], beans["turnouts InternalTurnoutManagerXml"])
        self.assertEqual(kinds["ActionSensor"], beans["sensors InternalSensorManagerXml"])


class BlockLengthFormats(unittest.TestCase):
    """le_tables writes a main or upper block's length as r1(mm), master_beans a staging one as f"{mm:.1f}"; one
    process for every level needs the two to agree (builder merge step 1)."""

    def test_every_committed_length_reads_the_same_both_ways(self) -> None:
        lengths = railroad.read_block_lengths(tb.BLOCK_LENGTHS)
        self.assertTrue(lengths)
        for name, length in lengths.items():
            mm = length.plan_in * tb.MM_PER_INCH
            self.assertEqual(lt.r1(mm), f"{mm:.1f}", name)

    def test_every_hundredth_of_an_inch_to_3000_in_reads_the_same_both_ways(self) -> None:
        bad = [k for k in range(300_000) if lt.r1(k / 100 * tb.MM_PER_INCH) != f"{k / 100 * tb.MM_PER_INCH:.1f}"]
        self.assertEqual([], bad[:5])


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

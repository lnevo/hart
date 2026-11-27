"""le_tables and le_checks, the Layout Editor build's tables checks and mast checks, on small made-up tables and panels
(no plugin, no solve): what the build checks on the beans the base holds for every level (naming-layers step 11: the
main and upper blocks drawn against block_numbering.csv, every name a band binds a bean), which beans are main and
upper ones (by the rows), and what the mast checks stop on.
"""
import dataclasses
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import le_checks  # noqa: E402
import le_common  # noqa: E402
import le_tables  # noqa: E402
from hartlib import block_numbering, level_devices  # noqa: E402
from hartlib.railroad_facts import DeviceRow  # noqa: E402
from le_common import BuildError  # noqa: E402

STAGING = "Staging"     # the made-up staging band's key in these tables (the build finds its own by level)

INTERNAL_SENSORS = "jmri.jmrix.internal.configurexml.InternalSensorManagerXml"
INTERNAL_TURNOUTS = "jmri.jmrix.internal.configurexml.InternalTurnoutManagerXml"

NAMES = {
    STAGING: dict(turnouts={"s1": "T1"}, os={"s1": "OS Switch 1"}, blocks={"e1": ["Track Helix Outer"]}),
    "Main": dict(turnouts={"n1": "Switch 105", "n2": "Switch 103"}, os={"n1": "OS Switch 105"},
                 blocks={"e2": ["Track 105-109"]}),
    "Upper": dict(turnouts={"n3": "Switch 201"}, os={"n3": "OS Switch 201"}, blocks={}),
}
LEVEL_BLOCKS = ["OS Switch 105", "OS Switch 201", "Track 105-109"]
# each level block's bean names as its device-master row gives them (build_device_map.py copies them from
# block_numbering.csv)
BEANS = {b: (f"IB:C3:{i:04d}", f"ILB{1000 + i}") for i, b in enumerate(LEVEL_BLOCKS, 1)}


def base_root(unbound=()) -> ET.Element:
    """Tables as the base holds them (hartlib.tables_build.base): one staging turnout and block (Track Helix Outer,
    the helix: a staging bean the levels draw too), and the main and upper blocks of BEANS, each bound to its virtual
    occupancy sensor but `unbound`."""
    blocks = "".join(
        f'<block systemName="{s}" length="1.0" curve="0"><systemName>{s}</systemName><userName>{b}</userName>'
        f'<permissive>no</permissive>'
        + ("" if b in unbound else f"<occupancysensor>{level_devices.occupancy_user(b)}</occupancysensor>")
        + "</block>" for b, (s, _lb) in BEANS.items())
    layout = "".join(f'<layoutblock systemName="{lb}"><systemName>{lb}</systemName><userName>{b}</userName>'
                     "</layoutblock>" for b, (_s, lb) in BEANS.items())
    return ET.fromstring(
        f'<layout-config><turnouts class="{INTERNAL_TURNOUTS}"><turnout><systemName>IT1</systemName>'
        '<userName>T1</userName></turnout></turnouts>'
        f'<sensors class="{INTERNAL_SENSORS}"><sensor><systemName>IS1</systemName><userName>S1</userName></sensor>'
        '</sensors><blocks>'
        '<block systemName="IB1" length="1.0" curve="0"><systemName>IB1</systemName><userName>Track Helix Outer'
        f'</userName><permissive>no</permissive></block>{blocks}</blocks>'
        '<layoutblocks><layoutblock systemName="ILB1"><systemName>ILB1</systemName>'
        f'<userName>Track Helix Outer</userName></layoutblock>{layout}</layoutblocks></layout-config>')


class CheckLevelBlocks(unittest.TestCase):
    """check_level_blocks: the numbering checks le_tables keeps now that the base holds every level's beans. Each
    main and upper block drawn has its row's names, current with block_numbering.csv, none is a retired block drawn
    again, no numbering row names a block not drawn, and each is bound to an occupancy sensor."""

    def run_it(self, drawn=None, beans=None, numbered_as=None, retired=(), unbound=()):
        P = SimpleNamespace(blocks=set(drawn if drawn is not None else LEVEL_BLOCKS + ["Track Helix Outer"]))
        made_up = block_numbering.Numbering(numbered_as or {}, (), tuple(retired))
        with mock.patch.object(le_tables, "numbering", return_value=made_up), \
                mock.patch.object(le_tables, "level_block_beans", return_value=BEANS if beans is None else beans):
            le_tables.check_level_blocks(base_root(unbound), P, {STAGING}, NAMES)

    def test_the_drawn_blocks_pass(self):
        self.run_it()

    def test_a_block_whose_row_has_no_names_stops(self):
        with self.assertRaisesRegex(BuildError, r"row gives no jmri_name and layout_block: \['Track 105-109'\]"):
            self.run_it(beans={b: v for b, v in BEANS.items() if b != "Track 105-109"})

    def test_a_retired_block_drawn_again_or_a_stale_numbering_row_stops(self):
        with self.assertRaisesRegex(BuildError, r"retired blocks drawn again: \['Track 105-109'\]"):
            self.run_it(retired=["Track 105-109"])
        with self.assertRaisesRegex(BuildError, "names Track 999-998, which the main and upper levels no longer"):
            self.run_it(numbered_as={"Track 999-998": "Track 105-109"})

    def test_a_block_with_no_occupancy_sensor_stops(self):
        with self.assertRaisesRegex(BuildError, r"no occupancy sensor .*\['OS Switch 201'\]"):
            self.run_it(unbound={"OS Switch 201"})

    def test_a_staging_block_is_not_a_main_or_upper_one(self):
        """Track Helix Outer, drawn on staging's band too, is staging's: its row is never asked for."""
        self.run_it(beans=BEANS)            # BEANS has no row for it, and nothing stops

    def test_the_rows_names_are_checked_against_the_numbering(self):
        """level_block_beans stops on a row whose layout block is not its block's pair, and on rows a
        block_numbering.csv edit left stale (stale_block_beans: build_device_map.py was not run since)."""
        row = DeviceRow(level=2, layer="block", user_name="Track 105-109", role="track", jmri_name="IB:C3:0003",
                        layout_block="ILB1004")
        rows = [row]
        with mock.patch.object(le_tables.devices, "load", return_value=rows), \
                mock.patch.object(le_tables, "stale_block_beans", return_value=[]):
            with self.assertRaisesRegex(BuildError, "layout_block 'ILB1004' is not the pair of jmri_name 'IB:C3:0003'"):
                le_tables.level_block_beans()
            rows[0] = dataclasses.replace(row, layout_block="ILB1003")
            self.assertEqual(le_tables.level_block_beans(), {"Track 105-109": ("IB:C3:0003", "ILB1003")})
        self.assertEqual(le_tables.stale_block_beans(), [])             # the committed rows and file agree
        d = Path(tempfile.mkdtemp())
        self.addCleanup(os.rmdir, d)
        path = d / le_tables.NUMBERING.name
        text = le_tables.NUMBERING.read_text(encoding="utf-8")
        old = "block:227C-241B#1,Track 227-241,,,"
        self.assertIn(old, text)
        path.write_text(text.replace(old, "block:227C-241B#1,,6,,"), encoding="utf-8")
        self.addCleanup(os.remove, path)
        stale = le_tables.stale_block_beans(numbering_path=path)
        self.assertIn("Track 227-241 1 (IB:C3:0108, not IB:C3:0122)", stale)


class CheckBound(unittest.TestCase):
    """check_bound, one check for every level on the tables the panel is drawn on (the base, which holds every
    level's beans): each name a band binds, and each block the panel draws, is a bean of the tables."""

    def root(self):
        root = base_root()
        ET.SubElement(ET.SubElement(root, "signalmasts"), "signalmast").extend(
            [ET.Element("systemName"), ET.Element("userName")])
        sm = root.find("signalmasts/signalmast")
        sm[0].text, sm[1].text = "IF$1", "Mast 2L"
        return root

    def names(self, **staging):
        return {STAGING: dict(dict(turnouts={"s1": "T1"}, os={}, blocks={"e1": ["Track Helix Outer"]},
                                   masts=[dict(mast="Mast 2L")]), **staging)}

    def P(self, blocks=("Track Helix Outer",), base_drawn=("Track Helix Outer",)):
        """A panel drawing `blocks`, of which `base_drawn` on band 0 (staging's)."""
        return SimpleNamespace(blocks=set(blocks), turnouts=[],
                               segments=[dict(ident=f"T{i}", block=b, band=0) for i, b in enumerate(base_drawn)])

    def check(self, root, P, names):
        le_tables.check_bound(root, P, names, {STAGING}, {0}, "the base")

    def test_every_name_bound(self):
        self.check(self.root(), self.P(), self.names())

    def test_every_levels_names_are_held_to_the_same_tables(self):
        """A main band's names are beans of the base too: the build adds none."""
        names = dict(self.names(), Main=dict(turnouts={}, os={"n1": "OS Switch 105"}, blocks={}))
        self.check(self.root(), self.P(blocks={"Track Helix Outer", "OS Switch 105"}), names)
        names["Main"]["turnouts"] = {"n1": "Switch 105"}
        with self.assertRaisesRegex(BuildError, r"Main: turnouts \['Switch 105'\]"):
            self.check(self.root(), self.P(), names)

    def test_a_missing_turnout_block_mast_or_drawn_block_is_named_by_band(self):
        for staging, want in ((dict(turnouts={"s1": "T9"}), r"Staging: turnouts \['T9'\]"),
                              (dict(os={"s1": "OS Switch 9"}), r"Staging: blocks \['OS Switch 9'\]"),
                              (dict(masts=[dict(mast="Mast 9L")]), r"Staging: masts \['Mast 9L'\]")):
            with self.subTest(want=want), self.assertRaisesRegex(BuildError, "no bean of the base: .*" + want):
                self.check(self.root(), self.P(), self.names(**staging))
        with self.assertRaisesRegex(BuildError, r"the panel draws blocks \['Track X'\]"):
            self.check(self.root(), self.P(blocks={"Track X"}, base_drawn=()), self.names())

    def test_a_staging_band_drawing_a_block_its_names_do_not_hold_stops(self):
        """The staging panel draws only staging's blocks, even one the tables hold under another name list."""
        root = self.root()
        blocks = root.find("layoutblocks")
        ET.SubElement(ET.SubElement(blocks, "layoutblock"), "userName").text = "Track W-9"
        with self.assertRaisesRegex(BuildError, r"Staging draws blocks its names do not hold: \['Track W-9'\]"):
            self.check(root, self.P(blocks={"Track Helix Outer", "Track W-9"},
                                    base_drawn=("Track Helix Outer", "Track W-9")), self.names())


class IsLevelBean(unittest.TestCase):
    """A main or upper bean is one whose system name a main or upper row gives (level_bean_names), not one whose name
    follows a rule."""

    ROWS = [DeviceRow(level=2, layer="turnout", user_name="Switch 105", role="turnout", assignment="virtual",
                      system_name="M2T3408", jmri_name="IT:HART:C3:105", layout_block="", start="closed"),
            DeviceRow(level=2, layer="block", user_name="Track 105-109", role="track", assignment="virtual",
                      system_name="", jmri_name="IB:C3:0001", layout_block="ILB1001", start=""),
            DeviceRow(level=2, layer="occupancy", user_name="BS Switch 105", role="os", assignment="virtual",
                      system_name="", jmri_name="IS:HART:C3:B:OS105", layout_block="", start="inactive"),
            DeviceRow(level=2, layer="fb", user_name="FB Switch 105 N", role="fb", assignment="none",
                      system_name="M2S3467", jmri_name="", layout_block="", start=""),
            DeviceRow(level=1, layer="turnout", user_name="Switch 8", role="turnout", assignment="field",
                      system_name="M2T408", jmri_name="M2T408", layout_block="", start="")]

    @staticmethod
    def el(tag, sysname, user=""):
        return ET.fromstring(f"<{tag}><systemName>{sysname}</systemName><userName>{user}</userName></{tag}>")

    def test_by_the_rows(self):
        names = le_tables.level_bean_names(rows=self.ROWS)
        self.assertEqual(names, {"IT:HART:C3:105", "IB:C3:0001", "ILB1001", "IS:HART:C3:B:OS105",
                                 level_devices.turnout_action("IT:HART:C3:105"),
                                 level_devices.clear_action("IS:HART:C3:B:OS105"), level_devices.CLEAR_LOGIXNG,
                                 level_devices.CLEAR_CONDITIONAL, level_devices.CLEAR_MANY})
        self.assertTrue(le_tables.is_level_bean(self.el("turnout", "IT:HART:C3:105"), names))
        self.assertFalse(le_tables.is_level_bean(self.el("turnout", "M2T408"), names))
        self.assertTrue(le_tables.is_level_bean(self.el("layoutblock", "ILB1001", "Track 105-109"), names))
        self.assertFalse(le_tables.is_level_bean(self.el("layoutblock", "ILB12", "Track W-1"), names))
        self.assertFalse(le_tables.is_level_bean(self.el("sensor", "M2S3467"), names))     # no bean: assignment none

    def test_a_start_with_no_action_name_stops_naming_the_row(self):
        rows = [dataclasses.replace(self.ROWS[0], jmri_name="IT:ODD:105", user_name="Switch 105")]
        with self.assertRaisesRegex(BuildError, r"turnout 'Switch 105' \(level 2\): start 'closed': .*IT:ODD:105"):
            le_tables.level_bean_names(rows=rows)

    def test_a_swapped_turnout_is_still_a_main_or_upper_bean(self):
        rows = [dataclasses.replace(self.ROWS[0], jmri_name="M2T3408", assignment="field", start="")]
        names = le_tables.level_bean_names(rows=rows)
        self.assertEqual(names, {"M2T3408"})
        self.assertTrue(le_tables.is_level_bean(self.el("turnout", "M2T3408", "Switch 105"), names))


class BandLevels(unittest.TestCase):
    """A band's level is its plan-overrides section's (every section read), and the staging level is the one whose
    band's names are the staging device map's (le_common.STAGING_LEVELS)."""

    def test_the_committed_bands(self):
        levels = le_common.plan_levels()
        self.assertEqual(sorted(levels.values()), [1, 2, 3])
        bands = sorted(((t, {}, {}) for t in levels), key=lambda b: levels[b[0]])
        self.assertEqual(le_common.band_levels(bands), [1, 2, 3])
        self.assertEqual(le_common.base_bands(bands), [0])
        self.assertEqual(le_common.STAGING_LEVELS, {1})

    def test_the_levels_follow_the_data_folder(self):
        import json
        import tempfile
        le_common.plan_levels()                                 # the committed folder, cached
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "plan_overrides.json").write_text(json.dumps(
                {"_sections": True, "staging": {"level_title": "Attic level", "level": 1}}), encoding="utf-8")
            with mock.patch.object(le_common.pd, "DATA", Path(tmp)):
                self.assertEqual(le_common.plan_levels(), {"Attic level": 1})
                (Path(tmp) / "plan_overrides.json").write_text(json.dumps(
                    {"_sections": True, "staging": {"level_title": "Cellar level", "level": 1}}), encoding="utf-8")
                self.assertEqual(le_common.plan_levels(), {"Cellar level": 1})     # a changed file is read again
        self.assertIn(1, le_common.plan_levels().values())

    def test_a_band_with_no_level_stops_naming_it(self):
        with self.assertRaisesRegex(BuildError, "gives no level to band 'Attic level'"):
            le_common.band_levels([("Attic level", {}, {})])


# ---------------------------------------------------------------- le_checks

class FakeIndex:
    """slots.Index's answers for a made-up panel: `slots` {(kind, ident, slot): (facing, protects)}, `bound`
    {(kind, ident, slot): mast}, `turnouts` {ident: (turnout name, continuing route)}."""

    def __init__(self, slots, bound, turnouts=None):
        self.slots, self.bound = slots, bound
        self.turnouts = {t: {"turnoutname": n, "continuing": c} for t, (n, c) in (turnouts or {}).items()}

    def candidates(self):
        return list(self.slots)

    def blocks(self, kind, ident, slot):
        return self.slots[(kind, ident, slot)]

    def masts(self):
        out = []
        for (kind, ident, slot), mast in self.bound.items():
            f, pr = self.slots[(kind, ident, slot)]
            m = dict(mast=mast, kind=kind, ident=ident, slot=slot, facing=f, protects=pr)
            if kind == "turnout":
                m["turnout"] = self.turnouts[ident]["turnoutname"]
            out.append(m)
        return out


def checks_with(ix):
    return mock.patch.object(le_checks, "slots_module", return_value=SimpleNamespace(Index=lambda _el: ix))


LE = SimpleNamespace(to_xml=lambda *_a: None)
P0 = SimpleNamespace()


def mast(name, kind="turnout", facing="Track W", protects=("OS Switch 1",), **kw):
    return dict(mast=name, kind=kind, facing=facing, protects=list(protects), **kw)


class MastChecks(unittest.TestCase):
    """check_masts, one check for every level's masts (it was check_device_masts for staging's and
    check_level_slots for main and upper's): each placed once, in a slot of its kind JMRI resolves to its blocks, on
    its switch's turnout and its leg, in the one slot its blocks fit; a mast no band asks for stops it."""

    SLOTS = {("turnout", "TO1", "A"): ("Track W", ["OS Switch 1"]),
             ("turnout", "TO2", "A"): ("Track W", ["OS Switch 1"]),
             ("turnout", "TO3", "B"): ("Track 105-109", ["OS Switch 109"]),
             ("turnout", "TO3", "C"): ("Track 105-109", ["OS Switch 109"]),
             ("anchor", "A1", "east"): ("Track W", ["Track E"]),
             ("end bumper", "EB1", "west"): ("Track 101 Spur", [])}
    TURNOUTS = {"TO1": ("M1", "2"), "TO2": ("M2", "2"), "TO3": ("Switch 109", "2")}

    def check(self, bound, masts, turnouts, panel_turnouts=None, listed=None):
        """`turnouts` {mast: turnout name}: listed as turnout masts in a mast file; `listed` as mast_turnouts gives it,
        whole."""
        listed = {m: ("x_masts.csv", t, "turnout") for m, t in turnouts.items()} if listed is None else listed
        with checks_with(FakeIndex(self.SLOTS, bound, panel_turnouts or self.TURNOUTS)):
            le_checks.check_masts(P0, masts, LE, listed)

    def test_every_levels_masts_in_one_check(self):
        self.check({("turnout", "TO1", "A"): "Mast 2L", ("turnout", "TO3", "B"): "Mast 110L",
                    ("end bumper", "EB1", "west"): "Mast 102R"},
                   {"Staging": [mast("Mast 2L")],
                    "Main": [mast("Mast 110L", facing="Track 105-109", protects=["OS Switch 109"], leg="normal"),
                             mast("Mast 102R", kind="end bumper", facing="Track 101 Spur", protects=[], hidden=True)]},
                   {"Mast 2L": "M1", "Mast 110L": "Switch 109"})

    def test_a_turnout_mast_on_another_turnout_or_fitting_two_stops(self):
        bound, want = {("turnout", "TO1", "A"): "Mast 2L"}, {"Staging": [mast("Mast 2L")]}
        with self.assertRaisesRegex(BuildError, r"Mast 2L \(Staging\) is on turnout M1, its switch's is M2"):
            self.check(bound, want, {"Mast 2L": "M2"})
        with self.assertRaisesRegex(BuildError, r"Mast 2L \(Staging\) fits 2 slots \(TO1 A, TO2 A\)"):
            self.check(bound, want, {"Mast 2L": "M1"}, dict(self.TURNOUTS, TO2=("M1", "2")))
        with self.assertRaisesRegex(BuildError, r"Mast 2L \(Staging\) is a turnout mast on the panel, but "
                                                r"masts.csv does not list it"):
            self.check(bound, want, {})
        with self.assertRaisesRegex(BuildError, r"Mast 2L \(Staging\) is a turnout mast on the panel, but "
                                                r"masts.csv gives it no switch \(a end bumper mast there\)"):
            self.check(bound, want, {}, listed={"Mast 2L": ("masts.csv", None, "end bumper")})

    def test_a_mast_bound_twice_not_asked_for_or_missing_stops(self):
        with self.assertRaisesRegex(BuildError, "Mast 2L is bound in two slots"):
            self.check({("turnout", "TO1", "A"): "Mast 2L", ("anchor", "A1", "east"): "Mast 2L"}, {}, {})
        with self.assertRaisesRegex(BuildError, "Mast B1 was not asked for"):      # on any band
            self.check({("anchor", "A1", "east"): "Mast B1"}, {"Staging": [], "Main": []}, {})
        with self.assertRaisesRegex(BuildError, r"Mast N \(Upper\) is not on the panel"):
            self.check({}, {"Upper": [mast("Mast N", kind="anchor")]}, {})
        with self.assertRaisesRegex(BuildError, "Mast M is asked for on Main and Upper"):
            self.check({("anchor", "A1", "east"): "Mast M"},
                       {"Main": [mast("Mast M", kind="anchor", protects=["Track E"])],
                        "Upper": [mast("Mast M", kind="anchor", protects=["Track E"])]}, {})

    def test_the_slot_resolves_to_the_masts_blocks_and_kind(self):
        bound = {("anchor", "A1", "east"): "Mast A"}
        self.check(bound, {"Main": [mast("Mast A", kind="anchor", protects=["Track E"])]}, {})
        with self.assertRaisesRegex(BuildError, r"Mast A \(Main\) at A1 east faces Track W and protects \['Track E'\], "
                                                r"not Track W into \['OS Switch 9'\]"):
            self.check(bound, {"Main": [mast("Mast A", kind="anchor", protects=["OS Switch 9"])]}, {})
        with self.assertRaisesRegex(BuildError, "is in a anchor slot, not a end bumper one"):
            self.check(bound, {"Main": [mast("Mast A", kind="end bumper", protects=["Track E"])]}, {})

    def test_the_leg(self):
        want = {"Main": [mast("Mast 110L", facing="Track 105-109", protects=["OS Switch 109"], leg="normal")]}
        turnouts = {"Mast 110L": "Switch 109"}
        self.check({("turnout", "TO3", "B"): "Mast 110L"}, want, turnouts)
        self.check({("turnout", "TO3", "C"): "Mast 110L"},
                   {"Main": [dict(want["Main"][0], leg="diverging")]}, turnouts)
        with self.assertRaisesRegex(BuildError, r"Mast 110L \(Main\) is on leg C of TO3, not its normal leg"):
            self.check({("turnout", "TO3", "C"): "Mast 110L"}, want, turnouts)
        with self.assertRaisesRegex(BuildError, "fits 2 slots"):              # without its leg: a guess
            self.check({("turnout", "TO3", "B"): "Mast 110L"}, {"Main": [dict(want["Main"][0], leg=None)]}, turnouts)
        # continuing route 4: the normal leg is C
        self.check({("turnout", "TO3", "C"): "Mast 110L"}, want, turnouts, dict(self.TURNOUTS, TO3=("Switch 109", "4")))

    def test_a_leg_on_a_slot_that_is_not_b_or_c_stops(self):
        slots = {**self.SLOTS, ("turnout", "TO3", "A"): ("Track 105-109", ["OS Switch 109"]),
                                    ("turnout", "TO3", "D"): ("Track 105-109", ["OS Switch 109"])}
        want = {"Main": [mast("Mast 110L", facing="Track 105-109", protects=["OS Switch 109"], leg="diverging")]}
        for slot in "AD":
            with self.subTest(slot=slot), checks_with(FakeIndex(slots, {("turnout", "TO3", slot): "Mast 110L"},
                                                                self.TURNOUTS)), \
                    self.assertRaisesRegex(BuildError, rf"Mast 110L \(Main\) has leg diverging but stands on leg "
                                                       rf"{slot} of TO3, not B or C"):
                le_checks.check_masts(P0, want, LE, {"Mast 110L": ("x_masts.csv", "Switch 109", "turnout")})

    def test_a_leg_mast_in_a_slot_that_is_no_turnout_is_named(self):
        want = {"Main": [mast("Mast A", kind="turnout", protects=["Track E"], leg="normal")]}
        with self.assertRaisesRegex(BuildError, r"Mast A \(Main\) at A1 east is in a anchor slot, not a turnout one"):
            self.check({("anchor", "A1", "east"): "Mast A"}, want, {"Mast A": "Switch 109"})


class MastTurnouts(unittest.TestCase):
    """mast_turnouts: each turnout mast's switch turnout, a base level's from the device map, an added level's by
    its switch number."""

    def row(self, mast, switch, system="IF$xx"):
        return dict(mast=mast, switch=switch, system_name=system)

    def test_from_each_mast_file(self):
        facts = {"Mast 2L": dict(kind="turnout", turnout="M2T408"), "Mast 4LA": dict(kind="end bumper")}
        rows = [self.row("Mast 110L", "109"), self.row("Mast A87", ""),
                self.row("Mast 102RA", "", "IF$vsm:basic:one-low($2001)")]
        self.assertEqual(le_checks.mast_turnouts(rows, facts), {
            "Mast 2L": ("masts.csv", "M2T408", "turnout"),
            "Mast 4LA": ("masts.csv", None, "end bumper"),
            "Mast 110L": ("masts.csv", "Switch 109", "turnout"),
            "Mast A87": ("masts.csv", None, "anchor"),
            "Mast 102RA": ("masts.csv", None, "end bumper")})

    def test_a_mast_in_both_files_stops(self):
        with self.assertRaisesRegex(BuildError, "both give Mast 2L"):
            le_checks.mast_turnouts([self.row("Mast 2L", "1")], {"Mast 2L": dict(kind="turnout", turnout="M")})

    def test_a_staging_map_error_names_it(self):
        import staging_device_map as sdm
        with mock.patch.object(sdm, "mast_facts", side_effect=sdm.StagingMapError("x is on switch 99")), \
                self.assertRaisesRegex(BuildError, "staging device map: x is on switch 99"):
            le_checks.mast_turnouts([])


if __name__ == "__main__":
    unittest.main()


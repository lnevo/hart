"""le_tables and le_checks, the Layout Editor build's tables assembly and mast checks, on small made-up tables and panels
(no plugin, no solve): which bands' turnouts and blocks the build adds as virtual beans, which panel elements the staging
guard counts as the other levels', and what the mast checks stop on. These pin the behaviour the level unification
(wiki/projects/level-unification-handoff.md, step 4) keeps while it takes the level branches out.
"""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import le_checks  # noqa: E402
import le_common  # noqa: E402
import le_tables  # noqa: E402
from hartlib import level_devices, tables  # noqa: E402
from le_common import BuildError, STAGING  # noqa: E402

INTERNAL_SENSORS = "jmri.jmrix.internal.configurexml.InternalSensorManagerXml"
INTERNAL_TURNOUTS = "jmri.jmrix.internal.configurexml.InternalTurnoutManagerXml"


def base_root() -> ET.Element:
    """Tables holding one staging block (Track Helix Outer, the helix: a staging bean the levels draw too) and one
    staging turnout, with the sections the build adds to."""
    return ET.fromstring(
        f'<layout-config><turnouts class="{INTERNAL_TURNOUTS}"><turnout><systemName>IT1</systemName>'
        '<userName>T1</userName></turnout></turnouts>'
        f'<sensors class="{INTERNAL_SENSORS}"><sensor><systemName>IS1</systemName><userName>S1</userName></sensor>'
        '</sensors><blocks>'
        '<block systemName="IB1"><systemName>IB1</systemName><userName>Track Helix Outer</userName></block>'
        '<block systemName="IB1" length="1.0" curve="0"><systemName>IB1</systemName><userName>Track Helix Outer'
        '</userName><permissive>no</permissive></block></blocks>'
        '<layoutblocks><layoutblock systemName="ILB1"><systemName>ILB1</systemName>'
        '<userName>Track Helix Outer</userName></layoutblock></layoutblocks>'
        '<LogixNGs/><LogixNGConditionalNGs/><LogixNGDigitalActions/></layout-config>')


def sensors_for(blocks) -> dict:
    return {b: (level_devices.block_sensor(b), level_devices.occupancy_user(b), "c") for b in blocks}


NAMES = {
    STAGING: dict(turnouts={"s1": "T1"}, os={"s1": "OS Switch 1"}, blocks={"e1": ["Track Helix Outer"]}),
    "Main": dict(turnouts={"n1": "Switch 105", "n2": "Switch 103"}, os={"n1": "OS Switch 105"},
                 blocks={"e2": ["Track 105-109"]}),
    "Upper": dict(turnouts={"n3": "Switch 201"}, os={"n3": "OS Switch 201"}, blocks={}),
}
LEVEL_BLOCKS = ["OS Switch 105", "OS Switch 201", "Track 105-109"]


class AddLevelObjects(unittest.TestCase):
    """add_level_objects adds every band's turnouts but staging's, every drawn block staging does not hold, a sensor
    for each and for a staging block the device map gives one (the helix), and the startup positions."""

    def run_it(self, names=NAMES, drawn=None, lengths=None, thrown=frozenset({"Switch 105"}), sensors=None):
        root = base_root()
        P = SimpleNamespace(blocks=set(drawn if drawn is not None else LEVEL_BLOCKS + ["Track Helix Outer"]))
        lengths = {b: 100.0 for b in LEVEL_BLOCKS} if lengths is None else lengths
        sensors = sensors_for(LEVEL_BLOCKS + ["Track Helix Outer"]) if sensors is None else sensors
        with mock.patch.multiple(le_tables, BLOCK_NUMBERED_AS={}, APPENDED_BLOCKS=(), RETIRED_BLOCKS=()), \
                mock.patch.object(le_tables, "level_sensors", return_value=sensors):
            le_tables.add_level_objects(root, P, names, lengths, {"Track Helix Outer", "OS Switch 1"}, thrown)
        return root

    def test_the_other_levels_turnouts_and_blocks_are_added_virtual(self):
        root = self.run_it()
        turnouts = [(tables.system_name(t), tables.user_name(t)) for t in tables.turnouts(root)]
        self.assertEqual(turnouts, [("IT1", "T1"), ("IT:HART:C3:103", "Switch 103"), ("IT:HART:C3:105", "Switch 105"),
                                    ("IT:HART:C3:201", "Switch 201")])
        full = {tables.user_name(b): b for b in tables.blocks(root)}
        self.assertEqual(sorted(full), sorted(LEVEL_BLOCKS + ["Track Helix Outer"]))
        self.assertEqual([tables.system_name(full[b]) for b in LEVEL_BLOCKS], ["IB:C3:0001", "IB:C3:0002",
                                                                               "IB:C3:0003"])
        self.assertEqual(full["Track 105-109"].get("length"), "100.0")
        lbs = {tables.user_name(b): tables.system_name(b) for b in tables.layout_blocks(root)}
        self.assertEqual(lbs["OS Switch 105"], f"ILB{le_tables.LAYOUT_BLOCK_FIRST}")

    def test_a_staging_block_the_device_map_gives_a_sensor_is_bound(self):
        root = self.run_it()
        helix = next(b for b in tables.blocks(root) if tables.user_name(b) == "Track Helix Outer")
        self.assertEqual(helix.findtext("occupancysensor"), level_devices.occupancy_user("Track Helix Outer"))
        added = {tables.system_name(s) for s in tables.sensors(root)} - {"IS1"}
        self.assertEqual(added, {level_devices.block_sensor(b) for b in LEVEL_BLOCKS + ["Track Helix Outer"]})
        self.assertEqual(next(b for b in tables.layout_blocks(root) if tables.user_name(b) == "Track Helix Outer")
                         .get("occupancysensor"), level_devices.occupancy_user("Track Helix Outer"))

    def test_startup_positions_are_the_added_turnouts_only(self):
        root = self.run_it()
        states = {a.findtext("namedBean/name"): a.findtext("state/enum") for a in root.iter("ActionTurnout")}
        self.assertEqual(states, {"IT:HART:C3:103": "Closed", "IT:HART:C3:105": "Thrown", "IT:HART:C3:201": "Closed"})
        with self.assertRaisesRegex(BuildError, r"start Thrown that the panel does not have: \['T1'\]"):
            self.run_it(thrown=frozenset({"T1"}))          # a staging turnout is no virtual one

    def test_a_block_with_no_length_or_sensor_stops(self):
        with self.assertRaisesRegex(BuildError, r"blocks with no source: \['Track 105-109'\]"):
            self.run_it(lengths={"OS Switch 105": 1.0, "OS Switch 201": 1.0})
        with self.assertRaisesRegex(BuildError, r"no occupancy row in the device map: \['OS Switch 201'\]"):
            self.run_it(sensors=sensors_for(["OS Switch 105", "Track 105-109"]))

    def test_a_staging_name_is_never_added(self):
        names = dict(NAMES, **{STAGING: dict(NAMES[STAGING], turnouts={"s1": "Switch 999"})})
        root = self.run_it(names=names)
        self.assertNotIn("Switch 999", {tables.user_name(t) for t in tables.turnouts(root)})


def label_panel(P) -> ET.Element:
    """A panel holding P's elements as the plugin writes them, the marker label first."""
    parts = [f'<positionablelabel hidden="yes" text="{tables.GENERATED_PANEL_MARKER}"/>']
    parts += [f'<layoutturnout ident="{t["ident"]}"/>' for t in P.turnouts]
    parts += [f'<positionablepoint ident="{k}"/>' for k in P.points]
    parts += [f'<tracksegment ident="{s["ident"]}"/>' for s in P.segments]
    parts += [f'<layoutShape ident="{s["ident"]}"/>' for s in P.shapes]
    parts += [f'<positionablelabel text="{lb["text"]}"/>' for lb in P.labels]
    parts += [f'<BlockContentsIcon blockcontents="{b["block"]}"/>' for b in P.bcis]
    parts += [f'<signalmasticon signalmast="{m["mast"]}"/>' for m in P.masts]
    return ET.fromstring("<LayoutEditor>" + "".join(parts) + "</LayoutEditor>")


def fake_panel():
    P = SimpleNamespace(
        turnouts=[dict(ident="TO1", band=0), dict(ident="TO2", band=1)],
        points={"A1": dict(band=0), "A2": dict(band=2)},
        segments=[dict(ident="T1", band=0), dict(ident="T2", band=1), dict(ident="TJ")],    # TJ: a join, no band
        shapes=[dict(ident="C1", band=0), dict(ident="C2", band=2)],
        labels=[dict(text="STAGING LEVEL", kind="title", band=0), dict(text="MAIN LEVEL", kind="title", band=None),
                dict(text="W-1", band=0), dict(text="105", band=1)],
        bcis=[dict(block="Track W-1", band=0), dict(block="Track 105-109", band=1)],
        masts=[dict(mast="Mast 2L", band=0), dict(mast="Mast 108LA", band=1)])
    P.name = lambda i: i
    return P


class LevelItems(unittest.TestCase):
    """level_items: the panel elements of every band but staging's (the plugin's band of each), a join's segment and
    every band title but staging's among them."""

    def test_the_other_bands_elements(self):
        P = fake_panel()
        panel = label_panel(P)
        got = {el.get("ident") or el.get("text") or el.get("blockcontents") or el.get("signalmast")
               for el in panel if id(el) in le_tables.level_items(P, panel, {0})}
        self.assertEqual(got, {"TO2", "A2", "T2", "TJ", "C2", "MAIN LEVEL", "105", "Track 105-109", "Mast 108LA"})

    def test_a_candidate_of_two_bands_keeps_both_and_their_titles(self):
        P = fake_panel()
        panel = label_panel(P)
        got = {el.get("ident") or el.get("text") or el.get("blockcontents") or el.get("signalmast")
               for el in panel if id(el) in le_tables.level_items(P, panel, {0, 1})}
        self.assertEqual(got, {"A2", "TJ", "C2"})
        with self.assertRaisesRegex(BuildError, "draws no band"):
            le_tables.level_items(P, panel, set())

    def test_a_label_or_icon_out_of_step_with_the_plugin_stops(self):
        P = fake_panel()
        panel = label_panel(P)
        next(el for el in panel if el.get("text") == "W-1").set("text", "W-9")
        with self.assertRaisesRegex(BuildError, "label 2 on the panel reads 'W-9'"):
            le_tables.level_items(P, panel, {0})
        P = fake_panel()
        P.labels = [lb for lb in P.labels if lb.get("kind") != "title"]
        with self.assertRaisesRegex(BuildError, "wrote no band title"):
            le_tables.level_items(P, label_panel(P), {0})


class IsLevelBean(unittest.TestCase):
    def test_by_the_naming_rule(self):
        def el(tag, sysname, user=""):
            return ET.fromstring(f"<{tag}><systemName>{sysname}</systemName><userName>{user}</userName></{tag}>")
        self.assertTrue(le_tables.is_level_bean(el("turnout", "IT:HART:C3:105")))
        self.assertFalse(le_tables.is_level_bean(el("turnout", "M2T408")))
        self.assertTrue(le_tables.is_level_bean(el("sensor", level_devices.block_sensor("Track 105-109"))))
        self.assertTrue(le_tables.is_level_bean(el("block", "IB:C3:0001")))
        self.assertTrue(le_tables.is_level_bean(el("layoutblock", "ILB1001", "Track 105-109")))
        self.assertFalse(le_tables.is_level_bean(el("layoutblock", "ILB12", "Track W-1")))


class BandLevels(unittest.TestCase):
    """A band's level is its plan-overrides section's (every section read), and the base levels are the ones the
    generator's base writes beans for (hartlib.tables_build.GENERATED_LEVELS)."""

    def test_the_committed_bands(self):
        levels = le_common.plan_levels()
        self.assertEqual(sorted(levels.values()), [1, 2, 3])
        bands = sorted(((t, {}, {}) for t in levels), key=lambda b: levels[b[0]])
        self.assertEqual(le_common.band_levels(bands), [1, 2, 3])
        self.assertEqual(le_common.base_bands(bands), [0])
        self.assertEqual(le_common.BASE_LEVELS, {1})

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

    def check(self, bound, masts, turnouts, panel_turnouts=None):
        with checks_with(FakeIndex(self.SLOTS, bound, panel_turnouts or self.TURNOUTS)):
            le_checks.check_masts(P0, masts, LE, turnouts)

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
        with self.assertRaisesRegex(BuildError, "a turnout mast whose mast file gives no switch"):
            self.check(bound, want, {})

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


class MastTurnouts(unittest.TestCase):
    """mast_turnouts: each turnout mast's switch turnout from its own mast file."""

    def row(self, mast, switch, system="IF$xx"):
        return dict(mast=mast, switch=switch, system_name=system)

    def test_from_each_mast_file(self):
        facts = {"Mast 2L": dict(kind="turnout", turnout="M2T408"), "Mast 4LA": dict(kind="end bumper")}
        rows = [self.row("Mast 110L", "109"), self.row("Mast A87", ""),
                self.row("Mast 102RA", "", "IF$vsm:HART:C3:($3001)")]
        self.assertEqual(le_checks.mast_turnouts(rows, facts), {"Mast 2L": "M2T408", "Mast 110L": "Switch 109"})

    def test_a_mast_in_both_files_stops(self):
        with self.assertRaisesRegex(BuildError, "both list Mast 2L"):
            le_checks.mast_turnouts([self.row("Mast 2L", "1")], {"Mast 2L": dict(kind="turnout", turnout="M")})

    def test_a_staging_map_error_names_it(self):
        import staging_device_map as sdm
        with mock.patch.object(sdm, "mast_facts", side_effect=sdm.StagingMapError("x is on switch 99")), \
                self.assertRaisesRegex(BuildError, "staging device map: x is on switch 99"):
            le_checks.mast_turnouts([])


if __name__ == "__main__":
    unittest.main()


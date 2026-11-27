"""device_map_masts.py: staging's masts by rule, which build_device_map.py writes as mast and head rows (naming-layers
step 12; build_masts.py part 1 until then). The rule functions on small hand-written inputs (names, numbers, control
points, IDs, the owner's names, the rows they make), and, as data checks that write nothing, the repo's committed
data. The wired heads have their own tests (tools/audit/tests/test_staging_wired_heads.py)."""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_device_map as bdm  # noqa: E402
import device_map_masts as dmm  # noqa: E402
import mast_plan  # noqa: E402
import staging_device_map as sdm  # noqa: E402
from hartlib import devices, level_masts  # noqa: E402


def sw(label):
    return dict(kind="switch", label=label)


def strand(edge, name, cm=100.0):
    return dict(edge=edge, name=name, cm=cm)


class Names(unittest.TestCase):
    def test_internal_head_names_take_the_levels_prefix(self):
        self.assertEqual(dmm.internal_head("Head 2R"), "IH:HART:C1:2R")
        self.assertEqual(dmm.internal_head("Head 24RA Top"), "IH:HART:C1:24RA_Top")
        self.assertEqual(dmm.internal_head("Head 67"), "IH:HART:C1:67")
        self.assertEqual(dmm.internal_head("Head 108LA", 2), "IH:HART:C3:108LA")      # the prefix is data, by level
        self.assertEqual(bdm.head_name("Head 108R Top", "3"), "IH:HART:C3:108R_Top")
        for bad in ("Mast 2R", "Head", "Head 2R Middle", "Head 2r", "head 2R", "Head 2R "):
            with self.assertRaisesRegex(dmm.RuleError, r"is not named Head <mast key>"):
                dmm.internal_head(bad)

    def test_one_head_takes_the_masts_key_two_take_top_and_bottom(self):
        self.assertEqual(dmm.head_users("Mast 4RA", 1), ["Head 4RA"])
        self.assertEqual(dmm.head_users("Mast 2L", 2), ["Head 2L Top", "Head 2L Bottom"])
        self.assertEqual(dmm.head_users("Mast 67", 1), ["Head 67"])


class PlanEdge(unittest.TestCase):
    # the drawing's own names are not read: the name store's, by strand, are STORED
    BAND = {"strands": {"a": strand("e16.0", "Drawn"), "b": strand("e16.1", ""), "c": strand("e16.2", "Drawn"),
                        "d": strand("e9+e10", ""), "e": strand("e160", "")}}
    STORED = {"a": "K-1", "b": "K-2", "d": "Main West", "e": "Other"}

    def test_one_edge_with_every_name_the_store_gives_it(self):
        edge = lambda sids: dmm.plan_edge(self.BAND, sids, self.STORED)     # noqa: E731
        self.assertEqual(edge(["a"]), ("e16", ["K-1", "K-2"]))       # the unnamed part left out
        self.assertEqual(edge(["b", "c"]), ("e16", ["K-1", "K-2"]))
        self.assertEqual(edge(["d"]), ("e9+e10", ["Main West"]))
        self.assertEqual(edge(["e"]), ("e160", ["Other"]))           # e160 is not e16
        self.assertEqual(dmm.plan_edge(self.BAND, ["a"], {}), ("e16", []))     # a drawn name is no name

    def test_a_run_over_two_edges_stops(self):
        with self.assertRaisesRegex(dmm.RuleError, r"spans plan edges \['e16', 'e9\+e10'\]"):
            dmm.plan_edge(self.BAND, ["a", "d"], self.STORED)


class Interlockings(unittest.TestCase):
    """interlockings.csv (every level; hartlib.railroad.read_interlockings checks it): staging's are its level 1
    rows, each switch a staging switch."""
    HEADER = "level,interlocking,switches,area,notes\n"

    def read(self, text, switches):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "interlockings.csv"
            path.write_text(self.HEADER + text, encoding="utf-8")
            return dmm.interlockings(set(switches), path)

    def test_each_staging_switch_maps_to_its_interlocking(self):
        got = self.read('1,Brick,"1, 3,5",,\n1,Barn,7,,\n2,CP 107,107,West,\n', {"1", "3", "5", "7", "9"})
        self.assertEqual(got, {"1": "Brick", "3": "Brick", "5": "Brick", "7": "Barn"})   # 9 in none, 107 not staging

    def test_a_switch_that_is_no_staging_switch_stops(self):
        with self.assertRaisesRegex(dmm.RuleError, r"interlockings.csv: Brick: switch 101 is no staging switch"):
            self.read('1,Brick,"1,101",,\n', {"1"})

    def test_the_file_is_checked_whole(self):
        for text, msg in (('1,Brick,"1,3",,\n1,Plane,3,,\n', "switch 3 is in Brick and Plane"),
                          ("1,Brick,1,Brick,\n", "a staging interlocking has no area"),
                          ("2,CP 107,107,,\n", "no area"),
                          ("4,X,1,,\n", "level is 1, 2 or 3"),
                          ("1,Brick,,,\n", "switches is a list of switch numbers"),
                          ("1,Brick,1,,\n1,Brick,3,,\n", "named, once per level")):
            with self.assertRaisesRegex(dmm.RuleError, msg):
                self.read(text, {"1", "3"})


def home(name, node, leg, **more):
    """A home mast as mast_rule.masts gives it."""
    m = dict(name=name, node=node, leg=leg, cp="Brick", switch="1", kind="one-low", heads=1, letter=name[-1],
             dir="west" if "L" in name.lstrip("0123456789")[:1] else "east", strand="s", running=False)
    m.update(more)
    return m


class Generate(unittest.TestCase):
    """generate() with the plan readers stubbed: what it makes of the home masts mast_rule.masts gives it."""

    BAND = {"nodes": {"N1": sw("1"), "N3": sw("3"), "N5": sw("5"), "END": dict(kind="bumper", label="")},
            "strands": {"west": strand("e1", "Main West", 300.0), "mid": strand("e2", "Scale", 120.0),
                        "short": strand("e3", "", 10.0), "stub": strand("e4", "Stub", 40.0)},
            "mp": {}}
    NAMES = {"os": {"N1": "OS Switch 1", "N3": "OS Switch 3", "N5": "OS Switch 5"}}
    RUNS = [(("N1", "A"), ["Track Main West"], ("END", "x")),
            (("N1", "B"), ["OS Switch 1", "Track Scale", "OS Switch 3"], ("N3", "A")),
            (("N3", "B"), [], ("N5", "A")),
            (("N5", "B"), [], ("END", "y"))]
    CHAINS = {("N1", "A"): ["west"], ("N1", "B"): ["mid"], ("N3", "A"): ["mid"], ("N3", "B"): ["short"],
              ("N5", "A"): ["short"], ("N5", "B"): ["stub"]}
    CM = {"Track Main West": 300.0, "OS Switch 1": 20.0, "Track Scale": 100.0, "OS Switch 3": 30.0}

    def generate(self, homes, cm=None, runs=None, inter=(), parts=None):
        """generate() over the home masts `homes` and intermediates `inter`, as mast_plan.plan gives them."""
        patch = unittest.mock.patch.object
        with patch(mast_plan, "run_blocks", lambda band, names: list(self.RUNS if runs is None else runs)), \
                patch(dmm, "run_strands", lambda band: dict(self.CHAINS)):
            return dmm.generate(self.BAND, self.NAMES, {"home": [dict(m) for m in homes],
                                                        "intermediates": [dict(m) for m in inter]},
                                dict(self.CM if cm is None else cm), dict(parts or {}),
                                {sid: s["name"] for sid, s in self.BAND["strands"].items() if s["name"]})

    def one(self, m, **kw):
        (got,) = self.generate([m], **kw)
        return got

    def test_a_turnout_mast_where_the_block_boundary_is_at_the_leg(self):
        got = self.one(home("2L", "N1", "A", heads=2, kind="two-searchlight", running=True))
        self.assertEqual(got, dict(mast="Mast 2L", cp="Brick", switch="1", facing="Track Main West",
                                   protects="OS Switch 1", kind="two-searchlight", heads=2, dir="west", toward="1",
                                   run="1;", names=["Main West"], edge_cm=300.0, cm_from_toward=0.0, edge="e1",
                                   node="N1", leg="A", strand="s", running=True, role="home"))

    def test_an_anchor_mast_where_the_os_block_runs_past_the_leg(self):
        got = self.one(home("2R", "N1", "B"))
        self.assertEqual((got["switch"], got["toward"], got["facing"], got["protects"]),
                         ("", "1", "Track Scale", "OS Switch 1"))
        self.assertEqual((got["run"], got["dir"], got["edge_cm"], got["cm_from_toward"]), ("1;3", "east", 150.0, 20.0))

    def test_a_part_is_inside_its_block_and_a_mast_faces_the_jmri_block_beyond(self):
        """A part is a JMRI block of its own: a mast at the switch whose OS block holds it stands
        past it, at the anchor; a mast at the other switch stands at its leg and faces the part (Mast 32R faces
        Track 29-31); the lengths are the JMRI blocks'."""
        runs = [(("N1", "B"), ["Track 1-3 at 1", "Track 3 Lead"], ("N3", "A"))]
        cm = {"Track 1-3 at 1": 12.0, "Track 3 Lead": 8.0}
        parts = {"Track 1-3 at 1": "OS Switch 1", "Track 3 Lead": "OS Switch 3"}
        west = self.one(home("2R", "N1", "B"), runs=runs, cm=cm, parts={"Track 1-3 at 1": "OS Switch 1"})
        self.assertEqual((west["switch"], west["facing"], west["protects"], west["edge_cm"], west["cm_from_toward"]),
                         ("", "Track 3 Lead", "OS Switch 1", 20.0, 12.0))
        east = self.one(home("4L", "N3", "A", switch="3"), runs=runs, cm=cm, parts={"Track 1-3 at 1": "OS Switch 1"})
        self.assertEqual((east["switch"], east["facing"], east["protects"], east["cm_from_toward"]),
                         ("3", "Track 3 Lead", "OS Switch 3", 0.0))
        both = self.one(home("4L", "N3", "A", switch="3"), runs=runs, cm=cm, parts=parts)
        self.assertEqual((both["switch"], both["facing"], both["cm_from_toward"]), ("", "Track 1-3 at 1", 8.0))

    def test_an_anchor_past_the_drawn_track_is_measured_from_the_far_end(self):
        # the OS block is longer than the track the plan draws (120 cm): the distance is from the other end
        got = self.one(home("2R", "N1", "B"), cm=dict(self.CM, **{"OS Switch 1": 125.0}))
        self.assertEqual((got["edge_cm"], got["cm_from_toward"]), (255.0, 130.0))

    def test_the_other_end_of_a_run_reads_its_blocks_backwards(self):
        got = self.one(home("4L", "N3", "A", switch="3"))
        self.assertEqual((got["switch"], got["facing"], got["protects"], got["cm_from_toward"], got["run"]),
                         ("", "Track Scale", "OS Switch 3", 30.0, "3;1"))

    def test_with_no_block_between_two_switches_a_mast_faces_the_far_os_block(self):
        got = self.one(home("4R", "N3", "B", switch="3"))
        self.assertEqual((got["switch"], got["facing"], got["protects"], got["edge_cm"]),
                         ("3", "OS Switch 5", "OS Switch 3", 0.0))

    def test_no_block_to_face_stops(self):
        with self.assertRaisesRegex(dmm.RuleError, "switch 5 leg B: no block to face"):
            self.generate([home("6R", "N5", "B", switch="5")])

    def test_kind_and_heads_are_the_plans(self):
        got = self.one(home("2R", "N1", "B", heads=2, kind="two-low", running=False))
        self.assertEqual((got["kind"], got["heads"]), ("two-low", 2))

    def test_an_intermediate_takes_its_run_and_names_from_the_plan(self):
        x = dict(name="67", cp="Brick", dir="west", facing="Track Scale", protects="OS Switch 1", toward="1", other="3",
                 start=("N1", "B"), to=("N1", "B"), dist=20.0, total=150.0, milepost=6.7)
        (got,) = self.generate([], inter=[x])
        self.assertEqual(got, dict(mast="Mast 67", cp="Brick", switch="", facing="Track Scale", protects="OS Switch 1",
                                   kind="one-searchlight", heads=1, dir="west", toward="1", run="1;3", names=["Scale"],
                                   edge_cm=150.0, cm_from_toward=20.0, edge="e2", node="N1", milepost=6.7,
                                   role="intermediate"))

    def test_direction_comes_from_the_rule(self):
        self.assertEqual(self.one(home("2L", "N1", "A"))["dir"], "west")
        self.assertEqual(self.one(home("2R", "N1", "A"))["dir"], "east")


GEN = [dict(mast="Mast 2L", cp="Brick", switch="1", facing="Track Main West", protects="OS Switch 1",
            kind="two-searchlight", heads=2, dir="west", toward="1", run="1;23", names=["Main West"], edge_cm=551.9,
            cm_from_toward=0.0, edge="e9+e10", node="N1", role="home"),
       dict(mast="Mast 67", cp="Princess", switch="", facing="Track K-2", protects="Track K-1",
            kind="one-searchlight", heads=1, dir="west", toward="39", run="39;37", names=["K-1", "K-2"], edge_cm=602.94,
            cm_from_toward=314.25, edge="e16", node="N39", role="intermediate"),
       dict(mast="Mast 4LA", cp="Brick", switch="", facing="Track W-1", protects="", kind="one-low", heads=1,
            dir="west", toward="3", run="3;", names=["W-1"], edge_cm=40.0, cm_from_toward=40.0, edge="e7", node="N3",
            role="hidden", signal_kind="virtual")]
IDS = {"Mast 2L": "mast:1:A:west", "Mast 67": "mast:block:37C-39C#1:west", "Mast 4LA": "mast:block:3B-end:west"}
SHSM_2L = "IF$shsm:basic:two-searchlight(IH:HART:C1:2L_Top)(IH:HART:C1:2L_Bottom)"
VIRTUAL = {"Mast 4LA": "IF$vsm:basic:one-low($1001)"}


def placed():
    return [dict(m) for m in GEN]


class Rows(unittest.TestCase):
    """The rows the builder writes (device-map form with role and id) and the plan facts build_masts.py writes."""

    def test_plan_facts(self):
        """Each placed mast's plan facts, keyed by level and mast; its signal name, kind and heads are not facts of
        their own (level_masts.signal_name, signal_kind, head_count give them from the row)."""
        got = dmm.plan_facts(GEN[:2])
        self.assertEqual(got, {
            (1, "Mast 2L"): dict(toward="1", run="1;23", names="Main West", edge_cm="551.9", cm_from_toward="0.0",
                                 schematic_edge="e9+e10", schematic_toward_node="N1"),
            (1, "Mast 67"): dict(toward="39", run="39;37", names="K-1;K-2", edge_cm="602.9", cm_from_toward="314.2",
                                 schematic_edge="e16", schematic_toward_node="N39")})
        self.assertEqual(list(got[(1, "Mast 2L")]), level_masts.PLAN_FIELDS)

    def test_device_rows_by_id(self):
        ms = placed()
        got = dmm.device_rows(ms, IDS, {}, {}, VIRTUAL)
        # the device-map columns, with the role and id (hartlib.device_ids) the builder gives each row
        self.assertEqual([[c for c in r if c not in ("id", "role")] for r in got], [bdm.COLUMNS] * len(got))
        self.assertEqual({r["user_name"]: (r["role"], r["id"]) for r in got},
                         {"Mast 2L": ("home", "mast:1:A:west"), "Mast 67": ("intermediate", IDS["Mast 67"]),
                          "Mast 4LA": ("hidden", IDS["Mast 4LA"]), "Head 67": ("head", "mast:block:37C-39C#1:west:single"),
                          "Head 2L Top": ("head", "mast:1:A:west:top"), "Head 2L Bottom": ("head", "mast:1:A:west:bottom")})
        # the masts by user name, then the heads by user name (plain string order: Mast 2L, Mast 4LA, Mast 67)
        self.assertEqual([(r["layer"], r["user_name"]) for r in got],
                         [("mast", "Mast 2L"), ("mast", "Mast 4LA"), ("mast", "Mast 67"), ("head", "Head 2L Bottom"),
                          ("head", "Head 2L Top"), ("head", "Head 67")])
        by = {r["user_name"]: r for r in got}
        self.assertEqual((by["Mast 2L"]["system_name"], by["Mast 2L"]["comment"], by["Mast 2L"]["notes"]),
                         (SHSM_2L, "Brick | Switch 1", "facing Track Main West into OS Switch 1"))
        self.assertEqual(by["Mast 67"]["comment"], "Princess")              # an intermediate names no switch
        self.assertEqual((by["Mast 4LA"]["system_name"], by["Mast 4LA"]["comment"], by["Mast 4LA"]["notes"]),
                         ("IF$vsm:basic:one-low($1001)", "Brick | Switch 3", "facing Track W-1, buffer stop"))
        self.assertEqual((by["Head 2L Top"]["jmri_name"], by["Head 2L Top"]["notes"]),
                         ("IH:HART:C1:2L_Top", dmm.INTERNAL_HEAD_NOTE))
        self.assertEqual([m["signal_kind"] for m in ms], ["planned", "planned", "virtual"])

    def test_a_wired_head_by_its_id_makes_a_field_signal(self):
        ms = placed()
        wired = {"mast:block:37C-39C#1:west:single": dict(system_name="IH467", jmri_name="IH467", node="4",
                                                         comment="Node: 4 Signal: 3 | OU: 2 Ports: 1,2,3",
                                                         notes="wired (test)")}
        got = {r["user_name"]: r for r in dmm.device_rows(ms, IDS, wired, {}, VIRTUAL)}
        self.assertEqual((got["Head 67"]["jmri_name"], got["Head 67"]["node"], got["Head 67"]["comment"]),
                         ("IH467", "4", "Node: 4 Signal: 3 | OU: 2 Ports: 1,2,3"))
        self.assertEqual((got["Mast 67"]["system_name"], got["Mast 67"]["node"]),
                         ("IF$shsm:basic:one-searchlight(IH467)", "4"))
        self.assertEqual(ms[1]["signal_kind"], "field")

    def test_a_wired_head_the_rule_does_not_place_stops(self):
        """A head wired by an ID the rule's masts do not give (a mast gone, or the rule now gives it other heads)."""
        for ident in ("mast:1:A:west:single", "mast:97:A:west:single"):
            wired = {ident: dict(system_name="IH432", jmri_name="IH432", node="4", comment="Node: 4", notes="")}
            with self.subTest(ident=ident), self.assertRaisesRegex(dmm.RuleError, f"{ident}, which the rule does not"):
                dmm.device_rows(placed(), IDS, wired, {}, VIRTUAL)

    def test_mast_node(self):
        heads = [dict(node="4")]
        self.assertEqual(dmm.mast_node("Mast 6LB", None, []), "")
        self.assertEqual(dmm.mast_node("Mast 6LB", dict(node="7"), heads), "7")
        self.assertEqual(dmm.mast_node("Mast 6LB", dict(node=""), heads), "4")
        with self.assertRaisesRegex(dmm.RuleError, "set the mast's node"):
            dmm.mast_node("Mast 6LB", None, [dict(node="4"), dict(node="5")])

    def test_mast_ids_from_the_plan_the_half_and_the_block_faced(self):
        """A home mast's ID is the switch label, leg and way it looks at its node, at a staging crossover's half with
        the half its OS block's ID has (both halves carry label 7); any other mast's the ID of the block it faces. A
        facing block with no ID stops."""
        band = {"nodes": {"n7": {"label": "7*"}, "n1": {"label": "1"}}}
        ms = [dict(mast="Mast 8LA", role="home", node="n7", leg="A", dir="west"),
              dict(mast="Mast 2L", role="home", node="n1", leg="A", dir="west"),
              dict(mast="Mast 67", role="intermediate", facing="Track K-2", dir="west"),
              dict(mast="Mast 4LA", role="hidden", facing="Track W-1", dir="west")]
        keys = {"n7": ("OS 7 A-13C", "os:7:A-13C"), "n1": ("OS Switch 1", "os:1")}
        with unittest.mock.patch.object(dmm.sdm, "os_keys", lambda band: keys):
            got = dmm.mast_ids(band, ms, {"Track K-2": "block:37C-39C#1", "Track W-1": "block:3B-end"})
            self.assertEqual(got, ["mast:7:A-13C:A:west", "mast:1:A:west", "mast:block:37C-39C#1:west",
                                   "mast:block:3B-end:west"])
            with self.assertRaisesRegex(dmm.RuleError, "Mast 67 faces Track K-2, which has no staging block row"):
                dmm.mast_ids(band, ms[2:3], {})
            with self.assertRaisesRegex(dmm.RuleError, "two masts have device ID mast:1:A:west"):
                dmm.mast_ids(band, ms[1:2] * 2, {})

    def test_the_owners_name_wins_and_must_be_one(self):
        ms = placed()
        dmm.owner_names(ms, [IDS[m["mast"]] for m in ms], {"mast:1:A:west": dict(user_name="Mast 2LX")})
        self.assertEqual([m["mast"] for m in ms], ["Mast 2LX", "Mast 67", "Mast 4LA"])
        self.assertEqual(ms[0]["generated"], "Mast 2L")
        for name, msg in (("Mast 67", "two masts are named Mast 67"), ("Signal 2", "not Mast <number>")):
            with self.subTest(name=name), self.assertRaisesRegex(dmm.RuleError, msg):
                dmm.owner_names(placed(), list(IDS.values()), {"mast:1:A:west": dict(user_name=name)})

    def test_heads_are_named_from_the_owners_name(self):
        ms = placed()
        dmm.owner_names(ms, list(IDS.values()), {"mast:1:A:west": dict(user_name="Mast 2LX")})
        ids = {m["mast"]: i for m, i in zip(ms, IDS.values())}
        got = {r["user_name"]: r for r in dmm.device_rows(ms, ids, {}, {}, VIRTUAL)}
        self.assertEqual(got["Head 2LX Top"]["jmri_name"], "IH:HART:C1:2LX_Top")
        self.assertEqual(got["Mast 2LX"]["id"], "mast:1:A:west")

    def test_a_virtual_mast_keeps_its_ordinal_by_id(self):
        """A virtual mast keeps the system name its row had by its ID, so a letter that changes moves no ordinal."""
        vgen = [dict(mast="Mast 4LA"), dict(mast="Mast 4LB")]
        ids = {"Mast 4LA": "mast:block:3C-end:west", "Mast 4LB": "mast:block:3B-end:west"}
        old = [dict(layer="mast", id="mast:block:3B-end:west", user_name="Mast 4LA",
                    system_name="IF$vsm:basic:one-low($1001)"),
               dict(layer="mast", id="mast:block:3C-end:west", user_name="Mast 4LB",
                    system_name="IF$vsm:basic:one-low($1002)")]
        got = dmm.virtual_names(vgen, ids, old)
        self.assertEqual(got, {"Mast 4LA": "IF$vsm:basic:one-low($1002)", "Mast 4LB": "IF$vsm:basic:one-low($1001)"})


class OneNameSource(unittest.TestCase):
    """Staging names its virtual masts and mast system names by the main and upper rules (device_map_level_masts)."""

    def test_an_old_virtual_name_out_of_every_levels_thousand_is_a_rule_error(self):
        old = [dict(layer="mast", id="mast:block:3B-end:west", user_name="Mast 4LA",
                    system_name="IF$vsm:basic:one-low($5001)")]
        with self.assertRaisesRegex(dmm.RuleError, r"\$5001\) \(id mast:block:3B-end:west"):
            dmm.virtual_names([dict(mast="Mast 4LA")], {"Mast 4LA": "mast:block:3B-end:west"}, old)

    def test_an_old_staging_row_with_another_levels_virtual_name_is_a_rule_error(self):
        old = [dict(layer="mast", id="mast:block:3B-end:west", user_name="Mast 4LA",
                    system_name="IF$vsm:basic:one-low($2001)")]
        with self.assertRaisesRegex(dmm.RuleError, r"staging's old mast rows hold virtual system names of level 2"):
            dmm.virtual_names([dict(mast="Mast 4LA")], {"Mast 4LA": "mast:block:3B-end:west"}, old)

    def test_a_new_virtual_mast_takes_the_next_ordinal(self):
        got = dmm.virtual_names([dict(mast="Mast 4LA")], {"Mast 4LA": "mast:block:3B-end:west"}, [])
        self.assertEqual(list(got), ["Mast 4LA"])        # an ordinal of staging's thousand past the retired ones
        self.assertEqual(level_masts.virtual_level(got["Mast 4LA"]), 1)

    def test_mast_numbers_and_system_names(self):
        self.assertEqual(dmm.mast_number("Mast 24RA"), 24)
        with self.assertRaisesRegex(dmm.RuleError, "has no number"):
            dmm.mast_number("Mast X")
        self.assertEqual(dmm.mast_system_name("one-low", ["IH:HART:C1:2R"]), "IF$shsm:basic:one-low(IH:HART:C1:2R)")


class EdgeCases(unittest.TestCase):
    """Names and IDs the rule must refuse rather than guess."""
    V = "IF$vsm:basic:one-low(${})"

    def test_a_mast_at_a_switch_with_no_control_point_stops(self):
        gen = [dict(mast="Mast 2R", toward="1"), dict(mast="Mast 34L", toward="33")]
        planned = dict(virtual=[dict(name="12L", switch="11")])
        dmm.check_control_points(gen, planned, {"1": "Brick", "11": "Barn", "33": "East End"})
        with self.assertRaisesRegex(dmm.RuleError, r"switch\(es\) 9, 33, which no staging station names"):
            dmm.check_control_points(gen + [dict(mast="Mast 10L", toward="9")], planned, {"1": "Brick", "11": "Barn"})
        with self.assertRaisesRegex(dmm.RuleError, r"switch\(es\) 11, which no staging station names"):
            dmm.check_control_points(gen, planned, {"1": "Brick", "33": "East End"})

    def test_a_dropped_virtual_masts_name_taken_by_a_new_mast_stops(self):
        """A dropped mast's ordinal must not go silently to a new mast (a new ID) that takes its name."""
        vgen = [dict(mast="Mast 4LA")]
        ids = {"Mast 4LA": "mast:block:new-end:west"}
        old = [dict(layer="mast", id="mast:block:3B-end:west", user_name="Mast 4LA", system_name=self.V.format(1001))]
        with self.assertRaisesRegex(dmm.RuleError, "Mast 4LA: the virtual mast of id mast:block:3B-end:west"):
            dmm.virtual_names(vgen, ids, old)
        virtual = [dict(id="mast:block:new-end:west", name="210LA")]
        with self.assertRaisesRegex(bdm.MapError, "Mast 210LA: the virtual mast of id mast:block:209B-end:west"):
            bdm.virtual_memory(virtual, {"mast:block:209B-end:west": ("Mast 210LA", self.V.format(3003))})

    def test_a_half_takes_every_end_end_key_gives(self):
        from hartlib import device_ids
        for half in ("A-13C", "A-121AB", "A-helix", "A-end"):
            self.assertEqual(device_ids.home_mast_id("7", "B", "east", half), f"mast:7:{half}:B:east")

    def test_a_bad_id_is_a_rule_error(self):
        band = {"nodes": {"n7": {"label": "7"}}}
        ms = [dict(mast="Mast 8LA", role="home", node="n7", leg="E", dir="west")]
        with unittest.mock.patch.object(dmm.sdm, "os_keys", lambda band: {}), \
                self.assertRaisesRegex(dmm.RuleError, "Mast 8LA: no device ID for a home mast"):
            dmm.mast_ids(band, ms, {})

    def test_the_levels_are_read_on_first_use(self):
        self.assertFalse(hasattr(dmm, "LEVELS"))
        self.assertEqual(dmm.levels(), {"Staging level": 1})


class MainUpperMemory(unittest.TestCase):
    """build_device_map.virtual_memory: a main or upper virtual mast keeps its ordinal by its ID too."""
    V = "IF$vsm:basic:one-low(${})"

    def test_an_ordinal_follows_its_id_not_its_letter(self):
        virtual = [dict(id="mast:block:209B-end:west", name="210LA"), dict(id="mast:block:209C-end:west", name="210LB")]
        old = {"mast:block:209C-end:west": ("Mast 210LA", self.V.format(3002)),
               "mast:block:209B-end:west": ("Mast 210LB", self.V.format(3003)),
               "mast:block:gone:west": ("Mast 299L", self.V.format(3009))}     # gone: kept by its old name
        self.assertEqual(bdm.virtual_memory(virtual, old),
                         {3: {"Mast 210LA": self.V.format(3003), "Mast 210LB": self.V.format(3002),
                              "Mast 299L": self.V.format(3009)}})

    def test_a_gone_masts_old_name_that_another_mast_has_now_stops(self):
        virtual = [dict(id="mast:block:209B-end:west", name="210LA")]
        old = {"mast:block:209B-end:west": ("Mast 210LB", self.V.format(3003)),
               "mast:block:gone:west": ("Mast 210LA", self.V.format(3002))}
        with self.assertRaisesRegex(bdm.MapError, "Mast 210LA: the virtual mast of id mast:block:gone:west"):
            bdm.virtual_memory(virtual, old)

    def test_an_old_name_out_of_the_levels_thousands_stops(self):
        """An old system name whose ordinal is in no main or upper thousand is named, not filed under no level."""
        old = {"mast:block:209B-end:west": ("Mast 210LA", self.V.format(5003))}
        with self.assertRaisesRegex(bdm.MapError, r"Mast 210LA: IF\$vsm:basic:one-low\(\$5003\) \(id mast:block:209B-end"):
            bdm.virtual_memory([], old)


class CommittedData(unittest.TestCase):
    """Data checks, not rule tests: staging_masts over the repo's committed plan and master (built once). A failure
    here can mean the data changed, not the code."""

    @classmethod
    def setUpClass(cls):
        bands, joined, runs, _corners = bdm.solve()
        files = devices.Files.here()
        cls.master = [r.cells() for r in devices.load(files)]
        cls.got = dmm.staging_masts(bands, joined, runs, cls.master, files)

    def test_the_builder_wrote_these_rows(self):
        """The master's staging mast and head rows are the ones the rule makes now (build_device_map.py wrote them)."""
        have = {r["id"]: (r["user_name"], r["system_name"], r["role"]) for r in self.master
                if r["level"] == "1" and r["layer"] in ("mast", "head") and r["written_by"] == dmm.WRITER}
        want = {r["id"]: (r["user_name"], r["system_name"], r["role"]) for r in self.got["rows"]}
        self.assertEqual(have, want)

    def test_masts_are_in_number_then_name_order_each_named_once(self):
        names = [m["mast"] for m in self.got["placed"]]
        self.assertEqual(names, sorted(names, key=lambda n: (int(re.search(r"\d+", n).group()), n)))
        self.assertEqual(len(set(names)), len(names))
        self.assertEqual(set(self.got["facts"]), {(1, n) for n in names})

    def test_virtual_masts_are_hidden_one_low_and_in_a_control_point(self):
        stations = sdm.switch_areas(dmm.STATIONS)
        for m in (m for m in self.got["placed"] if m["role"] == "hidden"):
            self.assertEqual((m["kind"], m["heads"], m["signal_kind"]), ("one-low", 1, "virtual"), m["mast"])
            self.assertIn(m["cp"], set(stations.values()), m["mast"])

    def test_home_masts_stand_only_at_switches_of_an_interlocking(self):
        stations = sdm.switch_areas(dmm.STATIONS)
        locks = dmm.interlockings(set(stations))
        self.assertLessEqual(set(locks), set(stations))
        for m in (m for m in self.got["placed"] if m["role"] == "home"):
            self.assertIn(m["toward"], locks, m["mast"])
            self.assertEqual(m["cp"], stations[m["toward"]], m["mast"])       # the cp column is the station

    def test_kind_follows_heads_and_running_track(self):
        for m in (m for m in self.got["placed"] if m["role"] != "hidden"):
            if "milepost" in m:
                self.assertEqual((m["kind"], m["heads"], m["switch"]), ("one-searchlight", 1, ""), m["mast"])
            else:
                want = f"{'two' if m['heads'] == 2 else 'one'}-{'searchlight' if m['running'] else 'low'}"
                self.assertEqual(m["kind"], want, m["mast"])

    def test_intermediates_come_in_pairs_odd_west_even_east(self):
        inter = [m for m in self.got["placed"] if "milepost" in m]
        self.assertEqual(len(inter) % 2, 0)
        for m in inter:
            number = int(m["mast"].removeprefix("Mast "))
            self.assertEqual(number % 2, 1 if m["dir"] == "west" else 0, m["mast"])
            self.assertLess(number, 100)

    def test_the_owners_names_keep_staging_letters(self):
        """The plan's letter order (plan_tracks.letter_order) would give staging's 6L and 8R pairs the other letters;
        the owner's names in the field file keep them, and the generated ones are kept on
        the masts the rule places."""
        renamed = {m["mast"]: m["generated"] for m in self.got["placed"] if "generated" in m}
        self.assertEqual(renamed, {"Mast 6LA": "Mast 6LB", "Mast 6LB": "Mast 6LA", "Mast 8RA": "Mast 8RB",
                                   "Mast 8RB": "Mast 8RA"})


if __name__ == "__main__":
    unittest.main()

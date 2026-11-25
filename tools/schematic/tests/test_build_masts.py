"""build_masts.py: staging's masts by rule. The rule functions on small hand-written inputs (names, numbers,
control points, ordering, the rows it writes), main() on temporary files, and, as data checks under a guard that fails
any write into the repo (repo_read_only.py), the repo's committed data.
The wired heads have their own tests (tools/audit/tests/test_staging_wired_heads.py)."""
from __future__ import annotations

import contextlib
import csv
import io
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import build_device_map as bdm  # noqa: E402
import build_masts as bsm  # noqa: E402
import mast_plan  # noqa: E402
import staging_device_map as sdm  # noqa: E402
from hartlib import level_masts  # noqa: E402
from hartlib import devices  # noqa: E402
from repo_read_only import RepoReadOnly, in_repo, repo_read_only  # noqa: E402

CM_PER_SCALE_MILE = 63360 * 2.54 / 87.1


def sw(label):
    return dict(kind="switch", label=label)


def strand(edge, name, cm=100.0):
    return dict(edge=edge, name=name, cm=cm)


def rows_of(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def write_rows(path: Path, columns, rows) -> Path:
    path.write_text(bsm.csv_text(rows, columns), encoding="utf-8")
    return path


class Carried(unittest.TestCase):
    """The one place a rebuild reads a prior row's hand-owned cells (CARRIED)."""

    def test_a_mast_keeps_its_node_and_a_head_its_notes(self):
        prior = dict(layer="head", node="4", notes="one high head", comment="Node: 4")
        self.assertEqual(bsm.carried(prior, "head"), {"notes": "one high head"})
        self.assertEqual(bsm.carried(dict(prior, layer="mast"), "mast"), {"node": "4"})
        self.assertEqual(bsm.carried(None, "head"), {})
        self.assertEqual(bsm.CARRIED, {"mast": ("node",), "head": ("notes",)})


class Names(unittest.TestCase):
    def test_internal_head_names(self):
        self.assertEqual(bsm.internal_head("Head 2R"), "IH:HART:C1:2R")
        self.assertEqual(bsm.internal_head("Head 24RA Top"), "IH:HART:C1:24RA_Top")
        self.assertEqual(bsm.internal_head("Head 67"), "IH:HART:C1:67")
        for bad in ("Mast 2R", "Head", "Head 2R Middle", "Head 2r", "head 2R", "Head 2R "):
            with self.assertRaisesRegex(bsm.RuleError, r"is not named Head <mast key>"):
                bsm.internal_head(bad)

    def test_one_head_takes_the_masts_key_two_take_top_and_bottom(self):
        self.assertEqual(bsm.head_users("Mast 4RA", 1), ["Head 4RA"])
        self.assertEqual(bsm.head_users("Mast 2L", 2), ["Head 2L Top", "Head 2L Bottom"])
        self.assertEqual(bsm.head_users("Mast 67", 1), ["Head 67"])

    def test_an_unwired_mast_gets_internal_heads(self):
        self.assertEqual(bsm.head_names("Mast 2L", 2, {}),
                         [("IH:HART:C1:2L_Top", "Head 2L Top"), ("IH:HART:C1:2L_Bottom", "Head 2L Bottom")])
        self.assertEqual(bsm.head_names("Mast 4RA", 1, {"Mast 6LB": {}}), [("IH:HART:C1:4RA", "Head 4RA")])


class PlanEdge(unittest.TestCase):
    # the drawing's own names are not read (naming-layers step 3b): the name store's, by strand, are STORED
    BAND = {"strands": {"a": strand("e16.0", "Drawn"), "b": strand("e16.1", ""), "c": strand("e16.2", "Drawn"),
                        "d": strand("e9+e10", ""), "e": strand("e160", "")}}
    STORED = {"a": "K-1", "b": "K-2", "d": "Main West", "e": "Other"}

    def test_one_edge_with_every_name_the_store_gives_it(self):
        edge = lambda sids: bsm.plan_edge(self.BAND, sids, self.STORED)     # noqa: E731
        self.assertEqual(edge(["a"]), ("e16", ["K-1", "K-2"]))       # the unnamed part left out
        self.assertEqual(edge(["b", "c"]), ("e16", ["K-1", "K-2"]))
        self.assertEqual(edge(["d"]), ("e9+e10", ["Main West"]))
        self.assertEqual(edge(["e"]), ("e160", ["Other"]))           # e160 is not e16
        self.assertEqual(bsm.plan_edge(self.BAND, ["a"], {}), ("e16", []))     # a drawn name is no name

    def test_a_run_over_two_edges_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, r"spans plan edges \['e16', 'e9\+e10'\]"):
            bsm.plan_edge(self.BAND, ["a", "d"], self.STORED)


class Interlockings(unittest.TestCase):
    """interlockings.csv (every level; hartlib.railroad.read_interlockings checks it): staging's are its level 1
    rows, each switch a staging switch."""
    HEADER = "level,interlocking,switches,area,notes\n"

    def read(self, text, switches):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "interlockings.csv"
            path.write_text(self.HEADER + text, encoding="utf-8")
            return bsm.interlockings(set(switches), path)

    def test_each_staging_switch_maps_to_its_interlocking(self):
        got = self.read('1,Brick,"1, 3,5",,\n1,Barn,7,,\n2,CP 107,107,West,\n', {"1", "3", "5", "7", "9"})
        self.assertEqual(got, {"1": "Brick", "3": "Brick", "5": "Brick", "7": "Barn"})   # 9 in none, 107 not staging

    def test_a_switch_that_is_no_staging_switch_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, r"interlockings.csv: Brick: switch 101 is no staging switch"):
            self.read('1,Brick,"1,101",,\n', {"1"})

    def test_the_file_is_checked_whole(self):
        for text, msg in (('1,Brick,"1,3",,\n1,Plane,3,,\n', "switch 3 is in Brick and Plane"),
                          ("1,Brick,1,Brick,\n", "a staging interlocking has no area"),
                          ("2,CP 107,107,,\n", "no area"),
                          ("4,X,1,,\n", "level is 1, 2 or 3"),
                          ("1,Brick,,,\n", "switches is a list of switch numbers"),
                          ("1,Brick,1,,\n1,Brick,3,,\n", "named, once per level")):
            with self.assertRaisesRegex(bsm.RuleError, msg):
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
    CPS = {"1": "Brick", "3": "Brick", "5": "Brick"}

    def generate(self, homes, wired=None, cm=None, runs=None, inter=(), parts=None):
        """generate() over the home masts `homes` and intermediates `inter`, as mast_plan.plan gives them."""
        patch = unittest.mock.patch.object
        with patch(mast_plan, "run_blocks", lambda band, names: list(self.RUNS if runs is None else runs)), \
                patch(bsm, "run_strands", lambda band: dict(self.CHAINS)):
            return bsm.generate(self.BAND, self.NAMES, {"home": [dict(m) for m in homes],
                                                        "intermediates": [dict(m) for m in inter]},
                                dict(self.CM if cm is None else cm), wired or {}, dict(parts or {}),
                                {sid: s["name"] for sid, s in self.BAND["strands"].items() if s["name"]})

    def one(self, m, **kw):
        (got,) = self.generate([m], **kw)
        return got

    def test_a_turnout_mast_where_the_block_boundary_is_at_the_leg(self):
        got = self.one(home("2L", "N1", "A", heads=2, kind="two-searchlight", running=True))
        self.assertEqual(got, dict(mast="Mast 2L", cp="Brick", switch="1", facing="Track Main West",
                                   protects="OS Switch 1", kind="two-searchlight", heads=2, dir="west", toward="1",
                                   run="1;", names=["Main West"], edge_cm=300.0, cm_from_toward=0.0, edge="e1",
                                   node="N1", leg="A", strand="s", running=True, role="home", signal_kind="planned"))

    def test_an_anchor_mast_where_the_os_block_runs_past_the_leg(self):
        got = self.one(home("2R", "N1", "B"))
        self.assertEqual((got["switch"], got["toward"], got["facing"], got["protects"]),
                         ("", "1", "Track Scale", "OS Switch 1"))
        self.assertEqual((got["run"], got["dir"], got["edge_cm"], got["cm_from_toward"]), ("1;3", "east", 150.0, 20.0))

    def test_a_part_is_inside_its_block_and_a_mast_faces_the_jmri_block_beyond(self):
        """A part is a JMRI block of its own (owner, 2026-11-20): a mast at the switch whose OS block holds it stands
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
        with self.assertRaisesRegex(bsm.RuleError, "switch 5 leg B: no block to face"):
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
                                   role="intermediate", signal_kind="planned"))

    def test_direction_comes_from_the_rule(self):
        self.assertEqual(self.one(home("2L", "N1", "A"))["dir"], "west")
        self.assertEqual(self.one(home("2R", "N1", "A"))["dir"], "east")

    def test_a_mast_with_wired_heads_is_a_field_signal(self):
        homes = [home("2L", "N1", "A"), home("2R", "N1", "B")]
        got = self.generate(homes, wired={"Mast 2R": {"Head 2R": {}}})
        self.assertEqual([(m["mast"], m["signal_kind"]) for m in got], [("Mast 2L", "planned"), ("Mast 2R", "field")])

    def test_order_by_number_then_name(self):
        homes = [home(n, "N1", "A") for n in ("24L", "4RB", "8RA", "4RA", "2R", "24RA", "2L", "36RA", "8LA")]
        self.assertEqual([m["mast"] for m in self.generate(homes)],
                         ["Mast 2L", "Mast 2R", "Mast 4RA", "Mast 4RB", "Mast 8LA", "Mast 8RA", "Mast 24L", "Mast 24RA",
                          "Mast 36RA"])

    def test_a_name_given_twice_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, r"the rule names a mast twice: \['Mast 2L'\]"):
            self.generate([home("2L", "N1", "A"), home("2L", "N1", "B")])


GEN = [dict(mast="Mast 2L", cp="Brick", switch="1", facing="Track Main West", protects="OS Switch 1",
            kind="two-searchlight", heads=2, dir="west", toward="1", run="1;23", names=["Main West"], edge_cm=551.9,
            cm_from_toward=0.0, edge="e9+e10", node="N1", signal_kind="planned"),
       dict(mast="Mast 67", cp="Princess", switch="", facing="Track K-2", protects="Track K-1",
            kind="one-searchlight", heads=1, dir="west", toward="39", run="39;37", names=["K-1", "K-2"], edge_cm=602.94,
            cm_from_toward=314.25, edge="e16", node="N39", signal_kind="field")]
SHSM_2L = "IF$shsm:basic:two-searchlight(IH:HART:C1:2L_Top)(IH:HART:C1:2L_Bottom)"
VIRTUAL = dict(mast="Mast 4LA", cp="Brick", switch="", facing="Track W-1", protects="", dir="west", leg="",
               system_name="IF$vsm:basic:one-low($1001)", head_system_names="",
               device_system_name="IF$vsm:basic:one-low($1001)")


def device(layer, user, system, **more):
    r = dict(level="1", cp="Brick", layer=layer, user_name=user, system_name=system, jmri_name=system, node="", dcc="",
             comment="", trial_name="", notes="", **dict.fromkeys(bdm.railroad.DEVICE_FACTS, ""))
    r.update(more)
    return r


class Rows(unittest.TestCase):
    """The rows written to masts.csv (the mast columns and the plan facts) and the staging rows of devices.csv."""

    def test_mast_rows(self):
        wired = {"Mast 67": {"Head 67": device("head", "Head 67", "IH467")}}
        self.assertEqual(bsm.mast_rows(GEN, wired), [
            dict(mast="Mast 2L", cp="Brick", switch="1", facing="Track Main West", protects="OS Switch 1", dir="west",
                 leg="", system_name=SHSM_2L, device_system_name=SHSM_2L,
                 head_system_names="IH:HART:C1:2L_Top=Head 2L Top;IH:HART:C1:2L_Bottom=Head 2L Bottom"),
            dict(mast="Mast 67", cp="Princess", switch="", facing="Track K-2", protects="Track K-1", dir="west",
                 leg="", system_name="IF$shsm:basic:one-searchlight(IH467)", head_system_names="IH467=Head 67",
                 device_system_name="IF$shsm:basic:one-searchlight(IH467)")])
        self.assertEqual(list(bsm.mast_rows(GEN, {})[0]), level_masts.MAST_FIELDS)

    def test_plan_facts(self):
        """Each placed mast's plan facts, keyed by level and mast; its signal name, kind and heads are not facts of
        their own (level_masts.signal_name, signal_kind, head_count give them from the row)."""
        self.assertEqual(bsm.plan_facts(GEN), {
            (1, "Mast 2L"): dict(toward="1", run="1;23", names="Main West", edge_cm="551.9", cm_from_toward="0.0",
                                 schematic_edge="e9+e10", schematic_toward_node="N1"),
            (1, "Mast 67"): dict(toward="39", run="39;37", names="K-1;K-2", edge_cm="602.9", cm_from_toward="314.2",
                                 schematic_edge="e16", schematic_toward_node="N39")})
        self.assertEqual(list(bsm.plan_facts(GEN)[(1, "Mast 2L")]), level_masts.PLAN_FIELDS)
        self.assertEqual(set(bsm.plan_facts(GEN, level=2)), {(2, "Mast 2L"), (2, "Mast 67")})

    def test_csv_text_has_lf_ends_and_quotes_only_what_needs_it(self):
        text = bsm.csv_text([dict(a="1", b="x,y"), dict(a="", b='say "hi"')], ("a", "b"))
        self.assertEqual(text, 'a,b\n1,"x,y"\n,"say ""hi"""\n')
        self.assertEqual(bsm.csv_text([], ("a", "b")), "a,b\n")

    def test_device_rows_replace_mast_and_head_rows_and_keep_the_rest_in_place(self):
        old = [device("turnout", "Switch 1", "MT100", notes="kept"),
               device("mast", "Mast 99L", "IF$shsm:basic:one-low(IH:HART:C1:99L)", notes="an old mast"),
               device("block", "Track W-1", "IB7", notes="kept too"),
               device("head", "Head 99L", "IH:HART:C1:99L", notes="an old head")]
        masts = [dict(mast="Mast 67", cp="Princess", switch="", facing="Track K-2", protects="Track K-1",
                      dir="west", system_name="IF$shsm:basic:one-searchlight(IH:HART:C1:67)",
                      head_system_names="IH:HART:C1:67=Head 67"),
                 dict(mast="Mast 2L", cp="Brick", switch="1", facing="Track Main West", protects="OS Switch 1",
                      dir="west", system_name=SHSM_2L,
                      head_system_names="IH:HART:C1:2L_Top=Head 2L Top;IH:HART:C1:2L_Bottom=Head 2L Bottom")]
        ids = {"Mast 67": "mast:block:37C-39C#1:west", "Mast 2L": "mast:1:A:west",
               "Mast 4LA": "mast:block:3B-end:west"}
        counts = {"Mast 67": 1, "Mast 2L": 2}
        got = bsm.device_rows(masts, [VIRTUAL], old, {}, ids=ids, head_counts=counts)
        with self.assertRaisesRegex(bsm.RuleError, r"Mast 2L: 2 head\(s\) listed, the rule gives it 1"):
            bsm.device_rows(masts, [VIRTUAL], old, {}, ids=ids, head_counts=dict(counts, **{"Mast 2L": 1}))
        with self.assertRaisesRegex(bsm.RuleError, r"mast\(s\) Mast 4LA have no device ID"):
            bsm.device_rows(masts, [VIRTUAL], old, {}, ids={k: v for k, v in ids.items() if k != "Mast 4LA"},
                            head_counts=counts)
        # the device-map columns, and the id (hartlib.device_ids) on the mast and head rows this script writes
        self.assertEqual([[c for c in r if c != "id"] for r in got], [bdm.COLUMNS] * len(got))
        self.assertEqual({r["user_name"]: r["id"] for r in got if "id" in r},
                         {**ids, "Head 67": "mast:block:37C-39C#1:west:single", "Head 2L Top": "mast:1:A:west:top",
                          "Head 2L Bottom": "mast:1:A:west:bottom"})
        got = [{k: v for k, v in r.items() if k != "id"} for r in got]
        # the other rows first and unchanged, then the masts by user name, then the heads by user name (plain string
        # order: Mast 2L, Mast 4LA, Mast 67)
        self.assertEqual(got[:2], [old[0], old[2]])
        self.assertEqual([(r["layer"], r["user_name"]) for r in got[2:]],
                         [("mast", "Mast 2L"), ("mast", "Mast 4LA"), ("mast", "Mast 67"), ("head", "Head 2L Bottom"),
                          ("head", "Head 2L Top"), ("head", "Head 67")])
        by = {r["user_name"]: r for r in got}
        self.assertEqual(by["Mast 2L"], device("mast", "Mast 2L", SHSM_2L, comment="Brick | Switch 1",
                                               notes="facing Track Main West into OS Switch 1", switch="1",
                                               facing="Track Main West", protects="OS Switch 1", dir="west"))
        self.assertEqual(by["Mast 67"]["comment"], "Princess")              # an anchor mast names no switch
        self.assertEqual(by["Mast 4LA"], device("mast", "Mast 4LA", "IF$vsm:basic:one-low($1001)", comment="Brick",
                                                notes="facing Track W-1, buffer stop", facing="Track W-1",
                                                dir="west"))
        self.assertEqual(by["Head 2L Top"], device("head", "Head 2L Top", "IH:HART:C1:2L_Top",
                                                   comment="Brick | Switch 1",
                                                   notes="internal, not wired (owner, 2026-11-19)"))   # with its date

    def test_mast_ids_from_the_plan_and_the_block_faced(self):
        """A home mast's ID is the switch label, leg and way it looks at its node; any other mast's the ID of the
        block it faces. A facing block with no ID stops."""
        band = {"nodes": {"n7": {"label": "7*"}}}
        placed = [dict(mast="Mast 8LA", role="home", node="n7", leg="A", dir="west"),
                  dict(mast="Mast 67", role="intermediate", facing="Track K-2", dir="west"),
                  dict(mast="Mast 4LA", role="hidden", facing="Track W-1", dir="west")]
        got = bsm.mast_ids(band, placed, {"Track K-2": "block:37C-39C#1", "Track W-1": "block:3B-end"})
        self.assertEqual(got, {"Mast 8LA": "mast:7:A:west", "Mast 67": "mast:block:37C-39C#1:west",
                               "Mast 4LA": "mast:block:3B-end:west"})
        with self.assertRaisesRegex(bsm.RuleError, "Mast 67 faces Track K-2, which has no staging block row"):
            bsm.mast_ids(band, placed[1:2], {})

    def test_with_roles_gives_each_row_the_role_the_rule_placed_it_with(self):
        """A mast row's role is the one generate() or virtual_masts() placed it with, a head row's head: none is read
        off a name (Mast 67 and Mast 2L are both named like the other kind on main and upper)."""
        rows = [device("mast", "Mast 67", "x"), device("mast", "Mast 2L", SHSM_2L), device("head", "Head 67", "IH467")]
        got = bsm.with_roles(rows, [dict(mast="Mast 67", role="home"), dict(mast="Mast 2L", role="intermediate")])
        self.assertEqual([r["role"] for r in got], ["home", "intermediate", "head"])
        self.assertEqual([{k: v for k, v in r.items() if k != "role"} for r in got], rows)
        with self.assertRaisesRegex(bsm.RuleError, r"mast row\(s\) \['Mast 2L'\] the rule did not place"):
            bsm.with_roles(rows, [dict(mast="Mast 67", role="home")])

    def test_device_rows_sort_by_plain_string_order(self):
        masts = [dict(mast=f"Mast {n}", cp="", switch="", facing="x", protects="", dir="east", system_name="IF$vsm:basic:one-low($1)",
                      head_system_names="") for n in ("8LA", "24L", "2L", "36RA", "4RA")]
        got = bsm.device_rows(masts, [], [], {}, ids={m["mast"]: f"mast:block:x{i}:east" for i, m in enumerate(masts)})
        self.assertEqual([r["user_name"] for r in got], ["Mast 24L", "Mast 2L", "Mast 36RA", "Mast 4RA", "Mast 8LA"])


class Cli(unittest.TestCase):
    """main() on temporary files (build() stubbed): --check and --show write nothing; a rule error is exit 2."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.current = self.dir / "current.csv"
        self.current.write_text("mast\nMast 2L\n", encoding="utf-8")
        self.stale = self.dir / "masts.csv"
        self.stale.write_text("mast\nold\n", encoding="utf-8")
        self.missing = self.dir / devices.MASTER_FILE
        want = {self.current: "mast\nMast 2L\n", self.stale: "mast\nnew\n", self.missing: "level\n1\n"}
        gen = [dict(GEN[0]), dict(GEN[1], milepost=6.714)]
        patch = unittest.mock.patch.object(bsm, "build", lambda check=False: (want, gen, []))
        patch.start()
        self.addCleanup(patch.stop)

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        # main() looks for the plugin first, which prints where it was found; these tests are about what follows
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                unittest.mock.patch.object(bsm.sdm.lc, "plugin", lambda: None):
            code = bsm.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_check_names_each_stale_or_missing_file_and_writes_nothing(self):
        code, out, err = self.run_main("--check")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err.splitlines(),
                         ["masts.csv is stale: run python3 tools/schematic/build_masts.py",
                          "devices_generated.csv is stale: run python3 tools/schematic/build_masts.py"])
        self.assertEqual(self.stale.read_text(encoding="utf-8"), "mast\nold\n")
        self.assertFalse(self.missing.exists())

    def test_a_run_writes_only_the_stale_files_and_then_check_passes(self):
        before = self.current.stat().st_mtime_ns
        code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), ["wrote masts.csv", "wrote devices_generated.csv"])
        self.assertEqual(self.stale.read_text(encoding="utf-8"), "mast\nnew\n")
        self.assertEqual(self.missing.read_text(encoding="utf-8"), "level\n1\n")
        self.assertEqual(self.current.stat().st_mtime_ns, before)
        self.assertEqual(self.run_main("--check"), (0, "", ""))
        self.assertEqual(self.run_main(), (0, "", ""))

    def test_show_prints_the_masts_and_writes_nothing(self):
        code, out, _err = self.run_main("--show")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].split(), ["Mast", "2L", "two-searchlight", "2h", "Track", "Main", "West", "->", "OS",
                                            "Switch", "1", "switch", "1", "west"])
        self.assertTrue(lines[1].endswith("anchor     west  MP 6.714"), lines[1])
        self.assertEqual(self.stale.read_text(encoding="utf-8"), "mast\nold\n")
        self.assertFalse(self.missing.exists())

    def test_check_and_show_do_not_go_together(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            bsm.main(["--check", "--show"])

    def test_a_rule_error_is_exit_2(self):
        def stop(check=False):
            raise bsm.RuleError("the rule names a mast twice: ['Mast 2L']")
        with unittest.mock.patch.object(bsm, "build", stop):
            code, out, err = self.run_main("--check")
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err.strip(), "build_masts.py: the rule names a mast twice: ['Mast 2L']")


class WriteGuard(unittest.TestCase):
    """The guard the data checks run under: a write inside the repo fails, one outside it goes through."""

    def test_a_write_inside_the_repo_is_refused_before_it_happens(self):
        target = Path(__file__).with_name("never_written.tmp")
        self.assertTrue(in_repo(target))
        with repo_read_only():
            for write in (lambda: target.write_text("x", encoding="utf-8"), lambda: target.write_bytes(b"x"),
                          lambda: open(target, "w"), lambda: target.open("a"), target.touch, target.mkdir,
                          lambda: Path(__file__).rename(target)):
                with self.assertRaisesRegex(AssertionError, "data checks only read it"):
                    write()
            self.assertEqual(Path(__file__).read_text(encoding="utf-8")[:3], '"""')      # reading still works
        self.assertFalse(target.exists())

    def test_a_write_outside_the_repo_goes_through(self):
        with tempfile.TemporaryDirectory() as d, repo_read_only():
            self.assertFalse(in_repo(d))
            (Path(d) / "sub").mkdir()
            (Path(d) / "sub" / "a.txt").write_text("x", encoding="utf-8")
            self.assertEqual((Path(d) / "sub" / "a.txt").read_text(encoding="utf-8"), "x")

    def test_a_link_outside_the_repo_that_points_into_it_may_be_swapped_but_not_written_through(self):
        """layer_files.view replaces a cache link to the checkout's data: the link moves, the repo does not."""
        stray = Path(__file__).with_name("never_written.tmp")
        self.addCleanup(lambda: stray.unlink(missing_ok=True))      # only there if the guard let it through
        with tempfile.TemporaryDirectory() as d, repo_read_only():
            tmp, link = Path(d) / "tmp.link", Path(d) / "view"
            os.symlink(Path(__file__).parent, tmp)
            os.replace(tmp, link)
            self.assertEqual(Path(__file__).parent, Path(os.readlink(link)))
            with self.assertRaisesRegex(AssertionError, "data checks only read it"):
                open(link / "never_written.tmp", "w")
            link.unlink()
            with self.assertRaisesRegex(AssertionError, "data checks only read it"):
                os.symlink(d, stray)                # a link made inside the repo is a write


class CommittedData(RepoReadOnly, unittest.TestCase):
    """Data checks, not rule tests: the real build() over the repo's committed plan and data (built once), under
    RepoReadOnly, so a write into the repo fails the test instead of changing a file. A failure here can mean the data
    changed, not the code. These hold whatever masts the rule places; they name no mast."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.files = {p: p.read_bytes() for p in (bsm.MASTS, bsm.DEVICE_MAP, bsm.device_files().master)}
        cls.want, cls.gen, cls.virtual = bsm.build()

    def test_check_reports_the_committed_files_current_and_writes_nothing(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bsm.main(["--check"])
        self.assertEqual((code, err.getvalue()), (0, ""))
        for path, data in self.files.items():
            self.assertEqual(path.read_bytes(), data, path.name)

    def test_build_gives_the_masts_and_master(self):
        f = bsm.device_files()
        self.assertEqual(set(self.want), {bsm.MASTS, f.master})

    def test_masts_are_in_number_then_name_order_each_named_once(self):
        for masts in (self.gen, self.virtual):
            names = [m["mast"] for m in masts]
            self.assertEqual(names, sorted(names, key=lambda n: (int("".join(c for c in n[5:] if c.isdigit())), n)))
        names = [m["mast"] for m in self.gen + self.virtual]
        self.assertEqual(len(set(names)), len(names))

    def test_virtual_masts_are_hidden_one_low_and_in_a_control_point(self):
        stations = sdm.switch_areas(bsm.STATIONS)
        for m in self.virtual:
            self.assertEqual((m["kind"], m["heads"], m["signal_kind"]), ("one-low", 1, "virtual"), m["mast"])
            self.assertIn(m["cp"], set(stations.values()), m["mast"])

    def test_home_masts_stand_only_at_switches_of_an_interlocking(self):
        # the signal rule's control points are interlockings.csv (level 1), not the stations the drawings group by
        stations = sdm.switch_areas(bsm.STATIONS)
        locks = bsm.interlockings(set(stations))
        # every interlocking switch is a station switch; how many station switches stay outside is the data's choice
        self.assertLessEqual(set(locks), set(stations))
        for m in self.gen:
            self.assertIn(m["toward"], locks, m["mast"])
            self.assertEqual(m["cp"], stations[m["toward"]], m["mast"])       # the cp column is the station

    def test_kind_follows_heads_and_running_track(self):
        for m in self.gen:
            if "milepost" in m:
                self.assertEqual((m["kind"], m["heads"], m["switch"]), ("one-searchlight", 1, ""), m["mast"])
            else:
                want = f"{'two' if m['heads'] == 2 else 'one'}-{'searchlight' if m['running'] else 'low'}"
                self.assertEqual(m["kind"], want, m["mast"])
                self.assertIn(m["heads"], (1, 2))

    def test_intermediates_come_in_pairs_odd_west_even_east(self):
        inter = [m for m in self.gen if "milepost" in m]
        self.assertEqual(len(inter) % 2, 0)
        for m in inter:
            number = int(m["mast"].removeprefix("Mast "))
            self.assertEqual(number % 2, 1 if m["dir"] == "west" else 0, m["mast"])
            self.assertLess(number, 100)

    def test_the_file_holds_every_level_in_level_number_and_name_order_the_placed_ones_with_plan_facts(self):
        rows = rows_of(self.want[bsm.MASTS])
        key = lambda r: (int(r["level"]), int("".join(c for c in r["mast"][5:] if c.isdigit())), r["mast"])  # noqa: E731
        self.assertEqual(rows, sorted(rows, key=key))
        self.assertEqual({r["level"] for r in rows}, {"1", "2", "3"})
        placed = {m["mast"] for m in self.gen + self.virtual}
        mine = [r for r in rows if r["level"] == str(bsm.PLANNED_LEVEL)]
        self.assertEqual({r["mast"] for r in mine}, placed)
        virtual = {m["mast"] for m in self.virtual}
        for r in rows:
            self.assertEqual(all(r[c] for c in ("toward", "run", "edge_cm")), r["mast"] in placed, r["mast"])
            if r["mast"] in placed:
                self.assertEqual(r["system_name"].startswith("IF$vsm:"), r["mast"] in virtual, r["mast"])
        kinds = {m["mast"]: m["signal_kind"] for m in self.gen + self.virtual}
        self.assertEqual({r["mast"]: level_masts.signal_kind(r) for r in mine}, kinds)

    def test_no_hand_kept_virtual_files_are_left(self):
        """The helix-foot masts were the last hand-kept ones (2026-11-20): the files that held them are gone."""
        self.assertFalse((bsm.DATA / "staging_masts_virtual.csv").exists())
        self.assertFalse((bsm.DATA / "staging_signals_virtual.csv").exists())

    def test_the_device_map_keeps_other_rows_then_masts_then_heads_by_name(self):
        old = bsm.devices.device_map_rows(bsm.devices.load(bsm.DEVICE_MAP), ("1",))     # the master's staging rows
        f = bsm.device_files()
        new = bsm.devices.device_map_rows(bsm.devices.parse(self.want[f.master], f.master.name, f), ("1",))  # built
        other = [r for r in old if r["layer"] not in ("mast", "head")]
        self.assertEqual(new[:len(other)], other)
        masts = [r["user_name"] for r in new if r["layer"] == "mast"]
        heads = [r["user_name"] for r in new if r["layer"] == "head"]
        self.assertEqual([r["layer"] for r in new[len(other):]], ["mast"] * len(masts) + ["head"] * len(heads))
        self.assertEqual(masts, sorted(masts))
        self.assertEqual(heads, sorted(heads))
        self.assertEqual(sorted(masts), sorted(r["mast"] for r in rows_of(self.want[bsm.MASTS]) if r["level"] == "1"))


if __name__ == "__main__":
    unittest.main()

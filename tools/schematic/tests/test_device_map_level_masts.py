"""device_map_level_masts.py: the main and upper masts' IDs and names and their rows, run over a small MapBuild with
a stand-in node allocator (no plugin, no data file)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[2] / "tools/hartlib/src")]
import device_map_level_masts as lm  # noqa: E402
import device_map_records as rec  # noqa: E402
import mast_plan  # noqa: E402
from device_map_nodes import NoBoardRoom  # noqa: E402
from hartlib import device_ids  # noqa: E402
from mast_rule import MapError  # noqa: E402

GROUP = rec.Group(2, "North", "CP 201")


class Nodes:
    """A stand-in for device_map_nodes.Nodes: masts go on node 7 from signal 0, board 3, pins 1, 4, ...; `full`
    leaves no board room."""

    def __init__(self, frozen=None, full=False):
        self.frozen = dict(frozen or {})
        self.full = full

    def take_frozen(self, kind, device):
        return self.frozen.get((kind, device))

    def pick_mast(self, level, area, heads, prefer=()):
        if self.full:
            raise NoBoardRoom(f"no board room in {area}")
        return 7

    def place_mast(self, node, heads):
        return [(k, node * 100 + 32 + k, 3, 1 + 3 * k) for k in range(heads)]


def state(**over) -> rec.MapBuild:
    blank = rec.MapBuild(*[None] * len(rec.MapBuild._fields))
    start = dict(rows=[], block_ids={}, home={"201": 4}, nodes=Nodes(), loc={}, switches={})
    return blank._replace(**{**start, **over})


def home(name="202L", heads=1, **over):
    start = dict(name=name, heads=heads, kind="one-searchlight" if heads == 1 else "two-searchlight", level=2,
                 cp="CP 201", switch="201", track="Track 201-203", facing="Track 201-203",
                 protects="OS Switch 201", dir="west", id=f"mast:{name}")
    return {**start, **over}


def frozen_head(node, index):
    return SimpleNamespace(node=node, index=index, address=f"IH{node * 100 + 32 + index}",
                           port_text=f"OU: 2 Ports: {1 + 3 * index},{2 + 3 * index},{3 + 3 * index}")


class Names(unittest.TestCase):
    def test_a_head_is_named_by_its_levels_prefix(self):
        self.assertEqual(lm.head_name("Head 108R Top", "3"), "IH:HART:C3:108R_Top")
        with self.assertRaises(MapError):
            lm.head_name("Top 108R", 3)

    def test_a_masts_system_name_lists_its_heads(self):
        self.assertEqual(lm.mast_system_name("two-searchlight", ["IH432", "IH433"]),
                         "IF$shsm:basic:two-searchlight(IH432)(IH433)")

    def test_the_block_a_mast_faces_is_found_on_its_level_then_on_the_other(self):
        st = state(block_ids={("2", "Track 1-3"): "block:a", ("3", "Track Helix Outer"): "block:h",
                              ("2", "Track 5-7"): "block:x", ("3", "Track 5-7"): "block:y"})
        self.assertEqual(lm.facing_id(st, 2, "Track 1-3"), "block:a")
        self.assertEqual(lm.facing_id(st, 2, "Track Helix Outer"), "block:h")
        self.assertEqual(lm.facing_id(st, "3", "Track 5-7"), "block:y")
        with self.assertRaisesRegex(MapError, "a mast faces Track 9-11, which has 0 block rows"):
            lm.facing_id(st, 2, "Track 9-11")
        with self.assertRaisesRegex(MapError, "a mast faces Track 5-7, which has 2 block rows"):
            lm.facing_id(st, 1, "Track 5-7")

    def test_a_home_mast_is_keyed_by_its_switch_leg_and_the_others_by_their_block(self):
        bands = [("Main", {"nodes": {"n1": {"label": "201A"}}}, {})]
        st = state(bands=bands, block_ids={("2", "Track 1-3"): "block:a"})
        mast = dict(band=0, node="n1", leg="B", dir="west", level=2, facing="Track 1-3")
        self.assertEqual(lm.home_mast_id(st, mast), device_ids.home_mast_id("201A", "B", "west"))
        self.assertEqual(lm.block_mast_id(st, mast), device_ids.block_mast_id("block:a", "west"))
        home, line, virtual = dict(mast), dict(mast), dict(mast)
        got = list(lm.mast_ids(st, [home], [line], [virtual]))
        self.assertEqual([ident for _m, ident in got], [device_ids.home_mast_id("201A", "B", "west")]
                         + [device_ids.block_mast_id("block:a", "west")] * 2)
        for (m, _ident), given in zip(got, (home, line, virtual)):
            self.assertIs(m, given)

    def test_a_mast_id_is_worked_out_as_its_mast_is_reached(self):
        bands = [("Main", {"nodes": {"n1": {"label": "201"}}}, {})]
        home = dict(band=0, node="n1", leg="B", dir="west")
        ids = lm.mast_ids(state(bands=bands), [home], [dict(level=2, facing="Track 9-11", dir="west")], [])
        self.assertEqual(next(ids)[1], device_ids.home_mast_id("201", "B", "west"))
        with self.assertRaisesRegex(MapError, "a mast faces Track 9-11"):
            next(ids)

    def named(self, owner, ms=None, virtual=()):
        bands = [("Main", {"nodes": {"n1": {"label": "201"}, "n2": {"label": "203"}}}, {})]
        ms = ms or [dict(home("202L"), band=0, node="n1", leg="B"), dict(home("204L"), band=0, node="n2", leg="B")]
        st = state(bands=bands)
        ids = [device_ids.home_mast_id(label, "B", "west") for label in ("201", "203")]
        return ms, ids, lambda: lm.name_masts(st, ms, [], list(virtual), owner(ids), {})

    def test_the_owners_name_goes_over_the_generated_one(self):
        ms, ids, run = self.named(lambda ids: {ids[0]: "Mast 300R", ids[1]: "Mast 204L"})
        self.assertEqual(run(), {})
        self.assertEqual([(m["id"], m["name"]) for m in ms], [(ids[0], "300R"), (ids[1], "204L")])

    def test_an_owners_name_out_of_the_grammar_stops(self):
        _ms, ids, run = self.named(lambda ids: {ids[0]: "Signal 300"})
        with self.assertRaisesRegex(MapError, f"mast {ids[0]} named 'Signal 300', not Mast <number>"):
            run()

    def test_two_masts_with_one_name_stop(self):
        _ms, _ids, run = self.named(lambda ids: {ids[0]: "Mast 204L"})
        with self.assertRaisesRegex(MapError, "two masts are named Mast 204L"):
            run()

    def test_owner_renames_reach_a_virtual_masts_needed_by(self):
        ms = [dict(home("202L"), band=0, node="n1", leg="B")]
        st = state(bands=[("Main", {"nodes": {"n1": {"label": "201"}}}, {})], block_ids={("2", "Track 201 Spur"): "block:s"})
        virtual = [dict(name="2001", level=2, facing="Track 201 Spur", dir="east", needed_by=["202L"])]
        owner = {device_ids.home_mast_id("201", "B", "west"): "Mast 300R"}
        self.assertEqual(lm.owner_renames(lm.mast_ids(st, ms, [], virtual), owner), {"202L": "300R"})
        self.assertEqual(virtual[0]["id"], device_ids.block_mast_id("block:s", "east"))


class VirtualMemory(unittest.TestCase):
    OLD = "IF$vsm:basic:one-low($2001)"

    def test_a_mast_keeps_its_system_name_by_its_id(self):
        virtual = [{"id": "mast:block:x:east", "name": "210R"}]
        self.assertEqual(lm.virtual_memory(virtual, {"mast:block:x:east": ("Mast 208R", self.OLD)}),
                         {2: {"Mast 210R": self.OLD}})

    def test_a_name_that_is_no_virtual_masts_stops(self):
        with self.assertRaisesRegex(MapError, "is not a main or upper virtual mast's system name"):
            lm.virtual_memory([], {"mast:block:x:east": ("Mast 208R", "IF$shsm:basic:one-low(IH1)")})

    def test_an_old_name_another_mast_now_has_stops(self):
        virtual = [{"id": "mast:block:y:east", "name": "208R"}]
        with self.assertRaisesRegex(MapError, "Mast 208R: the virtual mast of id mast:block:x:east had that name"):
            lm.virtual_memory(virtual, {"mast:block:x:east": ("Mast 208R", self.OLD)})


class HeadWiring(unittest.TestCase):
    USERS = ["Head 202L Top", "Head 202L Bottom"]

    def test_free_heads_take_board_room_on_one_node(self):
        got = lm.head_wiring(state(), GROUP, "201", home(heads=2), self.USERS)
        self.assertEqual((got.node, got.mast), (7, "IF$shsm:basic:two-searchlight(IH732)(IH733)"))
        self.assertEqual(got.heads[1], lm.Head("Head 202L Bottom", "IH733", 1, "OU: 3 Ports: 4,5,6"))

    def test_a_frozen_mast_keeps_its_wiring(self):
        frozen = {("head", u): frozen_head(4, i) for i, u in enumerate(self.USERS)}
        got = lm.head_wiring(state(nodes=Nodes(frozen)), GROUP, "201", home(heads=2), self.USERS)
        self.assertEqual((got.node, [h.system for h in got.heads]), (4, ["IH432", "IH433"]))
        self.assertEqual(got.heads[0].ports, "OU: 2 Ports: 1,2,3")

    def test_a_mast_frozen_in_part_or_on_two_nodes_stops(self):
        part = {("head", self.USERS[0]): frozen_head(4, 0)}
        two = {("head", self.USERS[0]): frozen_head(4, 0), ("head", self.USERS[1]): frozen_head(5, 0)}
        for name, frozen in (("part", part), ("two nodes", two)):
            with self.subTest(name), self.assertRaisesRegex(MapError, "Mast 202L: wiring.csv freezes . of its 2"):
                lm.head_wiring(state(nodes=Nodes(frozen)), GROUP, "201", home(heads=2), self.USERS)

    def test_with_no_board_room_the_heads_wait(self):
        got = lm.head_wiring(state(nodes=Nodes(full=True)), GROUP, "201", home(heads=2), self.USERS)
        self.assertEqual((got.node, got.mast), ("", ""))
        self.assertEqual(got.heads, [lm.Head(u, "", None, None) for u in self.USERS])


class Rows(unittest.TestCase):
    def test_a_home_mast_and_its_heads(self):
        st = state()
        lm.mast_rows(st, GROUP, "201", home(heads=2))
        mast, top, bottom = st.rows
        self.assertEqual((mast["user_name"], mast["role"], mast["comment"], mast["notes"]),
                         ("Mast 202L", "home", "CP 201 | Switch 201", "home signal from Track 201-203 into OS Switch 201"))
        self.assertEqual((mast["system_name"], mast["jmri_name"], mast["node"]),
                         ("IF$shsm:basic:two-searchlight(IH732)(IH733)",
                          "IF$shsm:basic:two-searchlight(IH:HART:C3:202L_Top)(IH:HART:C3:202L_Bottom)", 7))
        self.assertEqual((mast["switch"], mast["facing"], mast["protects"], mast["dir"]),
                         ("201", "Track 201-203", "OS Switch 201", "west"))
        self.assertEqual((top["user_name"], top["system_name"], top["comment"], top["jmri_name"]),
                         ("Head 202L Top", "IH732", "Node: 7 Signal: 0 | OU: 3 Ports: 1,2,3", "IH:HART:C3:202L_Top"))
        self.assertEqual([r["id"] for r in (top, bottom)],
                         [device_ids.head_id("mast:202L", device_ids.head_place(i, 2)) for i in (0, 1)])

    def test_an_intermediate_mast_names_its_milepost_and_no_switch(self):
        st = state()
        mast = home("1L", switch="", intermediate=True, milepost=1.5, protects="Track 3-5")
        lm.mast_rows(st, rec.Group(2, "North", ""), "201", mast)
        row = st.rows[0]
        self.assertEqual((row["role"], row["comment"], row["switch"]), ("intermediate", "North | intermediate", ""))
        self.assertEqual(row["notes"], "intermediate signal from Track 201-203 into Track 3-5 at MP 1 1.50")

    def test_heads_with_no_board_room_wait_under_their_virtual_names(self):
        st = state(nodes=Nodes(full=True))
        lm.mast_rows(st, GROUP, "201", home())
        mast, head = st.rows
        self.assertEqual((mast["system_name"], mast["node"]), ("", ""))
        self.assertEqual(mast["jmri_name"], "IF$shsm:basic:one-searchlight(IH:HART:C3:202L)")
        self.assertEqual((head["system_name"], head["notes"], head["comment"], head["jmri_name"]),
                         ("", lm.HEAD_NOT_WIRED, "CP 201 | Switch 201", "IH:HART:C3:202L"))

    def test_two_head_masts_are_placed_before_one_head_masts(self):
        cp = SimpleNamespace(level=2, area="North", name="CP 201", switches=("201",))
        local = SimpleNamespace(level=2, area="Yard")
        st = state(loc={"9": local}, home={"201": 4, "9": 5})
        ms = [home("202L"), home("202R", heads=2), home("10L", cp="", switch="9", heads=2), home("10R", cp="", switch="9")]
        lm.head_rows(st, [cp], ms)
        self.assertEqual([r["user_name"] for r in st.rows if r["layer"] == "mast"],
                         ["Mast 202R", "Mast 10L", "Mast 202L", "Mast 10R"])
        self.assertEqual({r["user_name"]: r["comment"] for r in st.rows if r["layer"] == "mast"}["Mast 10L"],
                         "Yard | Switch 9")

    def test_a_virtual_mast_is_hidden_with_no_heads(self):
        st = state(switches={"201": SimpleNamespace(cp="", area="Yard")})
        virtual = [dict(name="2001", level=2, switch="201", facing="Track 201 Spur", dir="east", id="mast:v",
                        needed_by=["202L", "204L"])]
        lm.virtual_mast_rows(st, virtual, {"2001": "IF$vsm:basic:one-low($2001)"})
        (row,) = st.rows
        self.assertEqual((row["user_name"], row["role"], row["system_name"], row["jmri_name"], row["node"]),
                         ("Mast 2001", "hidden", "IF$vsm:basic:one-low($2001)", "IF$vsm:basic:one-low($2001)", ""))
        self.assertEqual((row["comment"], row["notes"]),
                         ("Yard | buffer stop", "virtual bumper mast facing Track 201 Spur at its buffer stop: the "
                                                "destination of Mast 202L, Mast 204L"))


class PlanRows(unittest.TestCase):
    """plan_rows over a mast_plan.MastPlan with one mast of each kind, as mast_plan.plan returns it."""

    def plan(self) -> mast_plan.MastPlan:
        home_mast = dict(home("202L", heads=2), band=0, node="n1", leg="B")
        del home_mast["id"]                      # the plan gives no IDs: the device map does
        line = mast_plan.Intermediate(name="A83", level=2, band=0, dir="west", protects="Track 3-5",
                                      facing="Track 201-203", milepost=8.39, start=("n1", "A"), end=("n2", "A"),
                                      to=("n1", "A"), toward="201", other="203", dist=120.0, total=400.0, cp="CP 201")
        virtual = mast_plan.VirtualMast(name="952L", level=2, band=0, node="n1", leg="C", switch="201",
                                        bumper="e1", dir="east", facing="Track 201 Spur", seq=["Track 201 Spur"],
                                        total=90.0, needed_by=["202L"])
        return mast_plan.MastPlan(home=[home_mast], intermediates=[line], virtual=[virtual])

    def rows(self, owner):
        st = state(bands=[("Main", {"nodes": {"n1": {"label": "201"}}}, {})],
                   block_ids={("2", "Track 201-203"): "block:a", ("2", "Track 201 Spur"): "block:s"},
                   switches={"201": SimpleNamespace(cp="CP 201", area="North")})
        plan = self.plan()
        lm.plan_rows(st, [SimpleNamespace(level=2, area="North", name="CP 201", switches=("201",))], plan, owner, {})
        return plan, st.rows

    def test_each_kind_of_mast_gets_its_rows_and_its_id(self):
        plan, rows = self.rows({})
        ids = {"home": device_ids.home_mast_id("201", "B", "west"), "line": device_ids.block_mast_id("block:a", "west"),
               "virtual": device_ids.block_mast_id("block:s", "east")}
        self.assertEqual([(r["layer"], r["user_name"], r["role"]) for r in rows],
                         [("mast", "Mast 202L", "home"), ("head", "Head 202L Top", "head"),
                          ("head", "Head 202L Bottom", "head"), ("mast", "Mast A83", "intermediate"),
                          ("head", "Head A83", "head"), ("mast", "Mast 952L", "hidden")])
        self.assertEqual([r["id"] for r in rows if r["layer"] == "mast"], list(ids.values()))
        self.assertEqual((plan["home"][0]["id"], plan["virtual"][0]["id"]), (ids["home"], ids["virtual"]))
        line = rows[3]
        self.assertEqual((line["notes"], line["switch"], line["comment"]),
                         ("intermediate signal from Track 201-203 into Track 3-5 at MP A 8.39", "",
                          "CP 201 | intermediate"))
        self.assertEqual(line["jmri_name"], "IF$shsm:basic:one-searchlight(IH:HART:C3:A83)")

    def test_the_plans_intermediate_is_placed_as_a_copy(self):
        plan, _rows = self.rows({})
        self.assertEqual({"id", "heads", "kind", "switch", "intermediate"} & set(plan["intermediates"][0]), set())

    def test_an_owners_name_reaches_the_heads_and_the_virtual_masts_note(self):
        plan, rows = self.rows({device_ids.home_mast_id("201", "B", "west"): "Mast 300R"})
        self.assertEqual([r["user_name"] for r in rows[:3]], ["Mast 300R", "Head 300R Top", "Head 300R Bottom"])
        self.assertEqual(plan["virtual"][0]["needed_by"], ["300R"])
        self.assertTrue(rows[-1]["notes"].endswith("the destination of Mast 300R"))


if __name__ == "__main__":
    unittest.main()

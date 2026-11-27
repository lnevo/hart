"""masts.csv, every level's masts in one file: build_masts.file_rows, the one transform from the
mast and head rows of devices.csv for every level, and hartlib.level_masts.read, its reader. First written to pin
build_main_upper_masts.py before the builders merged (AGENTS.md, "Working on existing scripts"); its rows, order,
legs and stops hold for every level now. Small hand-written device rows (the master's columns), and the committed
file as a data check."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import build_masts as bmm  # noqa: E402
from hartlib import devices, level_masts, railroad  # noqa: E402
from repo_read_only import RepoReadOnly  # noqa: E402


def row(layer, user, jmri, system="", level=2, role=None, **kw):
    """A master row (the columns file_rows reads) with the role its writer gives it (a head's is head)."""
    r = dict(level=str(level), layer=layer, user_name=user, jmri_name=jmri, system_name=system, cp="", switch="",
             facing="", protects="", dir="", role="head" if role is None and layer == "head" else role)
    if r["role"] is None:
        raise ValueError(f"row {layer} {user}: give it its role")
    r.update(kw)
    r.setdefault("assignment", devices.assignment_of(jmri))
    return r


def block(user, role, level=1, ident=None):
    """A block row a mast may protect, with its role and device ID (an OS block's os:<switch>)."""
    if ident is None:
        number = user.removeprefix("OS Switch ")
        ident = f"os:{number}" if role == "os" and number.isdigit() else "block:" + user.replace(" ", "-")
    return row("block", user, "", level=level, role=role, id=ident)


def home(user, switch, facing, kind="one-searchlight", level=2, protects="", physical=True, role="home"):
    key = user.removeprefix("Mast ")
    head = level_masts.head_name(f"Head {key}", level) if level_masts.HEAD_USER.fullmatch(f"Head {key}") \
        else f"IH:HART:C3:{key}"
    lcos = "IH" + "".join(str(ord(c)) for c in key)        # a planned physical head, one per mast name
    return [row("mast", user, f"IF$shsm:basic:{kind}({head})", f"IF$shsm:basic:{kind}({lcos})"
                if physical else "", level=level, cp="CP 1", switch=switch, facing=facing, protects=protects,
                dir="west", role=role),
            row("head", f"Head {key}", head, lcos if physical else "", level=level)]


def run(rows, plan=None) -> list[dict]:
    """file_rows over device rows `rows`, each row in its mast columns (the level and plan facts left out)."""
    return [{c: r[c] for c in level_masts.MAST_FIELDS} for r in bmm.file_rows(rows, plan or {})]


class Committed(RepoReadOnly, unittest.TestCase):
    def test_the_committed_file_is_every_level_from_the_master_with_staging_plan_facts(self):
        text = level_masts.PATH.read_text(encoding="utf-8")
        plan = {(r["level"], r["mast"]): {c: r[c] for c in level_masts.PLAN_FIELDS}
                for r in level_masts.read() if level_masts.placed(r)}
        got = bmm.csv_text(bmm.file_rows([r.cells() for r in devices.load()], plan), level_masts.FIELDS)
        self.assertEqual(got, text)
        self.assertEqual(text.splitlines()[0], ",".join(level_masts.FIELDS))

    def test_the_levels_and_counts(self):
        rows = level_masts.read()
        self.assertEqual({lv: sum(r["level"] == lv for r in rows) for lv in level_masts.LEVELS}, {1: 30, 2: 27, 3: 41})
        # staging's are placed from plan facts of its own; main and upper's by build_signals.py from the plan graph
        self.assertEqual({r["level"] for r in rows if level_masts.placed(r)}, {1})


class Rows(unittest.TestCase):
    def test_a_home_mast_takes_its_heads_virtual_names_and_keeps_the_physical_one(self):
        (r,) = run(home("Mast 110L", "109", "Track 105-109"))
        self.assertEqual(r, dict(mast="Mast 110L", cp="CP 1", switch="109", facing="Track 105-109",
                                 protects="OS Switch 109", dir="west", leg="",
                                 system_name="IF$shsm:basic:one-searchlight(IH:HART:C3:110L)",
                                 head_system_names="IH:HART:C3:110L=Head 110L",
                                 device_system_name="IF$shsm:basic:one-searchlight(IH49494876)"))

    def test_a_staging_mast_is_its_own_jmri_name_and_takes_its_plan_facts(self):
        rows = home("Mast 2L", "1", "Track Main West", level=1, protects="OS Switch 1", physical=False)
        rows = [dict(r, system_name=r["jmri_name"]) for r in rows]          # staging: the live names in both
        plan = {(1, "Mast 2L"): dict(toward="1", run="1;23", names="Main West", edge_cm="5.0", cm_from_toward="0.0",
                                     schematic_edge="e1", schematic_toward_node="N1")}
        (r,) = bmm.file_rows(rows, plan)
        self.assertEqual((r["level"], r["system_name"], r["device_system_name"], r["head_system_names"], r["run"]),
                         ("1", "IF$shsm:basic:one-searchlight(IH:HART:C1:2L)",
                          "IF$shsm:basic:one-searchlight(IH:HART:C1:2L)", "IH:HART:C1:2L=Head 2L", "1;23"))

    def test_a_wired_head_is_kept_on_any_level(self):
        rows = home("Mast 6LB", "5", "Track East Ext", level=1, protects="OS Switch 5", physical=False)
        rows = [dict(rows[0], jmri_name="IF$shsm:basic:one-searchlight(IH432)",
                     system_name="IF$shsm:basic:one-searchlight(IH432)"),
                dict(rows[1], jmri_name="IH432", system_name="IH432", assignment="field")]
        (r,) = run(rows)
        self.assertEqual(r["head_system_names"], "IH432=Head 6LB")
        for level in (1, 2):    # a wired head on a row that is not a field device: refused on every level
            virtual = [dict(x, level=str(level), assignment="virtual") for x in rows]
            with self.subTest(level=level), self.assertRaisesRegex(bmm.RuleError, "wired LCOS head 'IH432'"):
                run(virtual)

    def test_a_row_on_no_level_is_left_out(self):
        """A device a PanelPro Store added and nobody placed has no level (hartlib.devices is_unplaced): no map's."""
        unplaced = row("mast", "Mast 999L", "IF$shsm:basic:one-low(IH:X)", level="", role="")   # a Store's: no role
        got = run(home("Mast 110L", "109", "T") + [unplaced, row("head", "Head 999L", "IH:X", level="")])
        self.assertEqual([r["mast"] for r in got], ["Mast 110L"])

    def test_a_mast_with_no_physical_heads_is_read_by_its_virtual_names(self):
        (r,) = run(home("Mast 110L", "109", "Track 105-109", physical=False))
        self.assertEqual((r["system_name"], r["device_system_name"]),
                         ("IF$shsm:basic:one-searchlight(IH:HART:C3:110L)", ""))

    def test_a_given_protected_block_is_kept(self):
        (r,) = run(home("Mast 226L", "225", "Track 223-225", protects="OS Switch 225a"))
        self.assertEqual(r["protects"], "OS Switch 225a")

    def test_a_home_mast_protects_its_switchs_os_block_by_its_id(self):
        """The OS block of the mast's switch is found by its device ID (os:<switch>), so the
        owner's name for it is the one written; with no such block row, the generated name."""
        (r,) = run(home("Mast 110L", "109", "Track 105-109") + [block("OS Ladder", "os", level=2, ident="os:109")])
        self.assertEqual(r["protects"], "OS Ladder")
        (r,) = run(home("Mast 110L", "109", "Track 105-109"))
        self.assertEqual(r["protects"], "OS Switch 109")

    def test_an_anchor_mast_protects_its_os_block_at_no_switch(self):
        (r,) = run(home("Mast 8RA", "", "Track Scale", level=1, protects="OS Switch 7", physical=False)
                   + [block("OS Switch 7", "os")])
        self.assertEqual((r["switch"], r["protects"]), ("", "OS Switch 7"))

    def test_a_virtual_mast(self):
        (r,) = run([row("mast", "Mast 102RA", "IF$vsm:basic:one-low($2001)", "IF$vsm:basic:one-low($2001)",
                        facing="Track 101 Spur 1", dir="east", role="hidden")])
        self.assertEqual(r, dict(mast="Mast 102RA", cp="", switch="", facing="Track 101 Spur 1", protects="",
                                 dir="east", leg="", system_name="IF$vsm:basic:one-low($2001)", head_system_names="",
                                 device_system_name="IF$vsm:basic:one-low($2001)"))

    def test_an_intermediate(self):
        rows = home("Mast A83", "", "Track 107 Loop 2", protects="Track 107 Loop 1", physical=False,
                    role="intermediate")
        (r,) = run(rows)
        self.assertEqual((r["switch"], r["protects"]), ("", "Track 107 Loop 1"))

    def test_an_a_and_a_b_mast_on_one_block_pair_get_their_legs(self):
        got = run(home("Mast 120RA", "119", "Track X") + home("Mast 120RB", "119", "Track X"))
        self.assertEqual({r["mast"]: r["leg"] for r in got}, {"Mast 120RA": "normal", "Mast 120RB": "diverging"})

    def test_order_is_level_then_number_then_name(self):
        got = run(home("Mast 230L", "229", "T1", level=3) + home("Mast 120RB", "119", "T2")
                  + home("Mast 110L", "109", "T3") + home("Mast 120RA", "119", "T4")
                  + home("Mast 2L", "1", "T5", level=1, physical=False))
        self.assertEqual([r["mast"] for r in got], ["Mast 2L", "Mast 110L", "Mast 120RA", "Mast 120RB", "Mast 230L"])


class Stops(unittest.TestCase):
    def stops(self, rows, pattern, plan=None):
        with self.assertRaisesRegex(bmm.RuleError, pattern):
            run(rows, plan)

    def test_a_virtual_mast_at_a_switch_or_with_another_levels_ordinal(self):
        for jmri, switch in (("IF$vsm:basic:one-low($2001)", "101"), ("IF$vsm:basic:one-low($1001)", "")):
            with self.subTest(jmri=jmri):
                self.stops([row("mast", "Mast 102RA", jmri, jmri, facing="T", switch=switch, dir="east",
                                role="hidden")],
                           "level 2 mast Mast 102RA: .* VirtualSignalMast of its level's thousand")

    def test_a_home_mast_at_no_switch_that_protects_no_os_block(self):
        """An OS block by its row's role, not its name: a block named like one but a track block stops too, and so
        does a protected block the level has no row for."""
        for name, role in (("Track Scale", "track"), ("OS Switch 7", "track"), ("OS Switch 7", "part")):
            with self.subTest(name=name, role=role):
                self.stops(home("Mast 8RA", "", "T", level=1, protects=name, physical=False) + [block(name, role)],
                           f"so an anchor mast, but protects {name}, no OS block")
        self.stops(home("Mast 8RA", "", "T", level=1, protects="OS Switch 7", physical=False),
                   "is an anchor mast protecting OS Switch 7, which is no level 1 block row")
        self.stops(home("Mast 8RA", "", "T", level=1, protects="OS Switch 7", physical=False)
                   + [block("OS Switch 7", "os", level=2)], "which is no level 1 block row")

    def test_one_anchor_rule_on_every_level(self):
        """One anchor rule on every level (owner, 2026-11-23): a main or upper home mast at no
        switch is an anchor mast as a staging one is, and must protect an OS block of its level; an intermediate (its
        role) protects a track block."""
        for level in (2, 3):
            with self.subTest(level=level):
                (r,) = run(home("Mast 110L", "", "T", level=level, protects="OS Switch 109")
                           + [block("OS Switch 109", "os", level=level, ident="os:109")])
                self.assertEqual((r["switch"], r["protects"]), ("", "OS Switch 109"))
                self.stops(home("Mast 110L", "", "T", level=level, protects="OS Switch 109"),
                           f"is an anchor mast protecting OS Switch 109, which is no level {level} block row")
                self.stops(home("Mast 110L", "", "T", level=level, protects="Track 105-109")
                           + [block("Track 105-109", "track", level=level, ident="block:105B-109A")],
                           "so an anchor mast, but protects Track 105-109, no OS block")
        (r,) = run(home("Mast A83", "", "Track 107 Loop 2", protects="Track 107 Loop 1", physical=False,
                        role="intermediate"))
        self.assertEqual(r["mast"], "Mast A83")

    def test_a_mast_protecting_two_blocks_or_none_at_no_switch(self):
        self.stops(home("Mast 110L", "109", "T", protects="A;B"), "protects .* a home signal is at a switch")
        self.stops(home("Mast 110L", "", "T"), "protects nothing")

    def test_a_system_name_not_over_heads(self):
        rows = home("Mast 110L", "109", "T")
        rows[0] = row("mast", "Mast 110L", "IF$shsm:basic:one-searchlight", "IF$shsm:basic:one-searchlight",
                      switch="109", facing="T", dir="west", role="home")
        self.stops(rows, "is not a SignalHeadSignalMast over its heads")

    def test_a_head_with_no_row_or_another_name(self):
        self.stops(home("Mast 110L", "109", "T")[:1], r"heads \['IH:HART:C3:110L'\] have no head row")
        rows = [dict(r, jmri_name=r["jmri_name"].replace("C3:110L", "C3:110LX")) for r in home("Mast 110L", "109", "T")]
        self.stops(rows, "head Head 110L is 'IH:HART:C3:110LX', neither its internal name IH:HART:C3:110L")
        rows = home("Mast 2L", "1", "T", level=1, protects="OS Switch 1", physical=False)
        rows = [dict(r, jmri_name=r["jmri_name"].replace("C1", "C3")) for r in rows]    # another level's prefix
        self.stops(rows, "neither its internal name IH:HART:C1:2L")

    def test_a_physical_mast_that_is_not_the_jmri_masts(self):
        rows = home("Mast 110L", "109", "T")
        rows[0] = row("mast", "Mast 110L", "IF$shsm:basic:one-low(IH:HART:C3:110L)", rows[0]["system_name"],
                      switch="109", facing="T", dir="west", role="home")
        self.stops(rows, "is not the planned physical mast of")

    def test_a_name_out_of_the_grammar(self):
        self.stops(home("Mast 1x0", "109", "T"), "the name is not Mast <number>")
        # a virtual mast too, before anything reads its number (the sort would fail on it)
        self.stops([row("mast", "Mast X", "IF$vsm:basic:one-low($2001)", "IF$vsm:basic:one-low($2001)",
                        facing="T", dir="east", role="hidden")], "level 2 mast Mast X: the name is not Mast <number>")

    def test_two_masts_on_one_pair_that_are_not_a_and_b(self):
        self.stops(home("Mast 120RA", "119", "X") + home("Mast 120RC", "119", "X"), "only an A and a B")

    def test_a_name_twice(self):
        self.stops(home("Mast 110L", "109", "T1") + home("Mast 110L", "109", "T2"), "mast Mast 110L is named twice")

    def test_plan_facts_for_a_mast_the_master_has_not(self):
        self.stops(home("Mast 110L", "109", "T"), "plan facts for level 1 mast Mast 9L",
                   plan={(1, "Mast 9L"): dict.fromkeys(level_masts.PLAN_FIELDS, "x")})


class Reader(unittest.TestCase):
    """hartlib.level_masts.read: the whole file checked, the rows of the levels asked for."""

    def write(self, text: str) -> Path:
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [p.unlink() for p in d.iterdir()] and d.rmdir())
        p = d / "masts.csv"
        p.write_text(text, encoding="utf-8")
        return p

    def committed(self) -> str:
        return level_masts.PATH.read_text(encoding="utf-8")

    def fails(self, text: str, pattern: str):
        with self.assertRaisesRegex(railroad.FactsError, pattern):
            level_masts.read(self.write(text))

    def test_levels_filter_and_lines(self):
        p = self.write(self.committed())
        rows = level_masts.read(p, levels=(2, 3))
        self.assertEqual({r["level"] for r in rows}, {2, 3})
        self.assertTrue(all(isinstance(r["line"], int) and r["line"] > 31 for r in rows))
        with self.assertRaisesRegex(railroad.FactsError, r"levels \[4\] are not"):
            level_masts.read(p, levels=(4,))

    def test_the_header_must_be_the_fields(self):
        self.fails(self.committed().replace("level,mast,", "mast,level,", 1), "masts.csv line 1: columns mast,level")

    def test_a_bad_level_name_dir_or_leg(self):
        t = self.committed()
        self.fails(t.replace("1,Mast 2L,", "4,Mast 2L,", 1), "line 2: mast Mast 2L: level '4'")
        self.fails(t.replace("1,Mast 2L,", "1,Signal 2L,", 1), "line 2: mast Signal 2L: the name")
        self.fails(t.replace(",OS Switch 1,west,,", ",OS Switch 1,north,,", 1), "line 2: mast Mast 2L: dir 'north'")
        self.fails(t.replace(",OS Switch 1,west,,", ",OS Switch 1,west,left,", 1), "line 2: mast Mast 2L: leg 'left'")

    def test_a_name_twice_on_any_level(self):
        lines = self.committed().splitlines(keepends=True)
        self.fails("".join(lines + [lines[1]]), "line 100: mast Mast 2L is on line 2 already")

    def test_some_plan_facts_but_not_all(self):
        self.fails(self.committed().replace(",Main West,586.7,0.0,e16,TOL34067", ",Main West,,0.0,e16,TOL34067", 1),
                   "line 2: mast Mast 2L: plan facts")

    def test_heads_not_its_system_names_or_another_levels_names(self):
        t = self.committed()
        self.fails(t.replace("IH:HART:C1:2L_Top=Head 2L Top", "IH:HART:C1:2L_Top=Head 2R Top", 1),
                   "line 2: mast Mast 2L: head Head 2R Top is")
        self.fails(t.replace("=Head 2L Bottom", "", 1), "are not system=user pairs")

    def test_a_virtual_mast_out_of_its_levels_thousand(self):
        self.fails(self.committed().replace("one-low($1001)", "one-low($2999)"), "virtual mast")

    def test_derived_signal_facts(self):
        rows = {r["mast"]: r for r in level_masts.read(levels=(1,))}
        self.assertEqual([level_masts.signal_kind(rows[m]) for m in ("Mast 2L", "Mast 6LB", "Mast 4LA")],
                         ["planned", "field", "virtual"])
        self.assertEqual([level_masts.head_count(rows[m]) for m in ("Mast 2L", "Mast 6LB", "Mast 4LA")], [2, 1, 1])
        self.assertEqual(level_masts.signal_name("Mast 24RA"), "24RA")


if __name__ == "__main__":
    unittest.main()

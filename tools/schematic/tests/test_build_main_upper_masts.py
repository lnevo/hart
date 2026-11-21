"""build_main_upper_masts.py: main_upper_masts.csv from the main and upper mast and head rows of devices.csv. Pinned
before the mast builders merge (AGENTS.md, "Working on existing scripts"): the committed file is what build() gives,
and the rules it holds on small hand-written device maps (the virtual head names, the default protected block, the
virtual and intermediate masts, the A and B legs, the order, and every stop)."""
from __future__ import annotations

import csv
import io
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import build_main_upper_masts as bmm  # noqa: E402
from hartlib import level_masts, railroad  # noqa: E402
from repo_read_only import RepoReadOnly  # noqa: E402


def row(layer, user, jmri, system="", level=2, **kw):
    return railroad.DeviceRow(level=level, layer=layer, user_name=user, jmri_name=jmri, system_name=system, **kw)


def home(user, switch, facing, kind="one-searchlight", level=2, protects="", physical=True):
    key = user.removeprefix("Mast ")
    head = f"IH:HART:C3:{key}"
    lcos = "IH" + "".join(str(ord(c)) for c in key)        # a planned physical head, one per mast name
    return [row("mast", user, f"IF$shsm:basic:{kind}({head})", f"IF$shsm:basic:{kind}({lcos})"
                if physical else "", level=level, cp="CP 1", switch=switch, facing=facing, protects=protects,
                dir="west", comment=f"CP 1 | Switch {switch}"),
            row("head", f"Head {key}", head, lcos if physical else "", level=level)]


def run(rows) -> list[dict]:
    """build() over a device map of `rows`, as the CSV rows it writes."""
    dm = railroad.DeviceMap(rows=list(rows))
    fake = unittest.mock.Mock(device_map=dm)
    with unittest.mock.patch.object(bmm.railroad, "Railroad", return_value=fake):
        return list(csv.DictReader(io.StringIO(bmm.build())))


class Committed(RepoReadOnly, unittest.TestCase):
    def test_the_committed_file_is_what_build_gives(self):
        self.assertEqual(bmm.build(), level_masts.PATH.read_text(encoding="utf-8"))

    def test_columns(self):
        self.assertEqual(bmm.build().splitlines()[0], ",".join(level_masts.FIELDS))


class Rows(unittest.TestCase):
    def test_a_home_mast_takes_its_heads_virtual_names_and_keeps_the_physical_one(self):
        (r,) = run(home("Mast 110L", "109", "Track 105-109"))
        self.assertEqual(r, dict(mast="Mast 110L", cp="CP 1", switch="109", facing="Track 105-109",
                                 protects="OS Switch 109", dir="west", leg="",
                                 system_name="IF$shsm:basic:one-searchlight(IH:HART:C3:110L)",
                                 head_system_names="IH:HART:C3:110L=Head 110L",
                                 device_system_name="IF$shsm:basic:one-searchlight(IH49494876)"))

    def test_a_mast_with_no_physical_heads_is_read_by_its_virtual_names(self):
        (r,) = run(home("Mast 110L", "109", "Track 105-109", physical=False))
        self.assertEqual((r["system_name"], r["device_system_name"]),
                         ("IF$shsm:basic:one-searchlight(IH:HART:C3:110L)", ""))

    def test_a_given_protected_block_is_kept(self):
        (r,) = run(home("Mast 226L", "225", "Track 223-225", protects="OS Switch 225a"))
        self.assertEqual(r["protects"], "OS Switch 225a")

    def test_a_virtual_mast(self):
        (r,) = run([row("mast", "Mast 102RA", "IF$vsm:basic:one-low($2001)", "IF$vsm:basic:one-low($2001)",
                        cp="", facing="Track 101 Spur 1", dir="east")])
        self.assertEqual(r, dict(mast="Mast 102RA", cp="", switch="", facing="Track 101 Spur 1", protects="",
                                 dir="east", leg="", system_name="IF$vsm:basic:one-low($2001)", head_system_names="",
                                 device_system_name="IF$vsm:basic:one-low($2001)"))

    def test_an_intermediate(self):
        rows = home("Mast A83", "", "Track 107 Loop 2", protects="Track 107 Loop 1", physical=False)
        rows[0] = row("mast", "Mast A83", rows[0].jmri_name, cp="CP 107", facing="Track 107 Loop 2",
                      protects="Track 107 Loop 1", dir="west", comment="CP 107 | intermediate")
        (r,) = run(rows)
        self.assertEqual((r["switch"], r["protects"]), ("", "Track 107 Loop 1"))

    def test_an_a_and_a_b_mast_on_one_block_pair_get_their_legs(self):
        got = run(home("Mast 120RA", "119", "Track X") + home("Mast 120RB", "119", "Track X"))
        self.assertEqual({r["mast"]: r["leg"] for r in got}, {"Mast 120RA": "normal", "Mast 120RB": "diverging"})

    def test_order_is_level_then_number_then_name(self):
        got = run(home("Mast 230L", "229", "T1", level=3) + home("Mast 120RB", "119", "T2")
                  + home("Mast 110L", "109", "T3") + home("Mast 120RA", "119", "T4"))
        self.assertEqual([r["mast"] for r in got], ["Mast 110L", "Mast 120RA", "Mast 120RB", "Mast 230L"])


class Stops(unittest.TestCase):
    def stops(self, rows, pattern):
        with self.assertRaisesRegex(SystemExit, pattern):
            run(rows)

    def test_a_virtual_mast_at_a_switch_or_with_a_staging_ordinal(self):
        for jmri, switch in (("IF$vsm:basic:one-low($2001)", "101"), ("IF$vsm:basic:one-low($1001)", "")):
            with self.subTest(jmri=jmri):
                self.stops([row("mast", "Mast 102RA", jmri, jmri, facing="T", switch=switch, dir="east")],
                           "virtual mast Mast 102RA")

    def test_a_mast_at_no_switch_that_is_not_an_intermediate(self):
        rows = home("Mast 110L", "", "T", protects="OS Switch 109")
        self.stops(rows, "stands at no switch, so it is an intermediate")

    def test_a_mast_protecting_two_blocks_or_none_at_no_switch(self):
        self.stops(home("Mast 110L", "109", "T", protects="A;B"), "protects .* a home signal is at a switch")
        self.stops(home("Mast 110L", "", "T"), "protects nothing")

    def test_a_system_name_not_over_heads(self):
        rows = home("Mast 110L", "109", "T")
        rows[0] = row("mast", "Mast 110L", "IF$shsm:basic:one-searchlight", "IF$shsm:basic:one-searchlight",
                      switch="109", facing="T", dir="west")
        self.stops(rows, "system name not as expected")

    def test_a_head_with_no_row_or_another_virtual_name(self):
        self.stops(home("Mast 110L", "109", "T")[:1], r"heads \['IH49494876'\] have no head row")
        rows = home("Mast 110L", "109", "T")
        rows[1] = row("head", "Head 110L", "IH:HART:C3:110LX", rows[1].system_name)
        self.stops(rows, "has jmri_name 'IH:HART:C3:110LX', not IH:HART:C3:110L")

    def test_a_jmri_name_that_is_not_the_heads(self):
        rows = home("Mast 110L", "109", "T")
        rows[0] = row("mast", "Mast 110L", "IF$shsm:basic:one-low(IH:HART:C3:110L)", rows[0].system_name,
                      switch="109", facing="T", dir="west")
        self.stops(rows, "jmri_name .* is not IF\\$shsm:basic:one-searchlight")

    def test_a_name_out_of_the_grammar(self):
        self.stops(home("Mast 110", "109", "T"), "not a mast name in the device map's grammar")

    def test_two_masts_on_one_pair_that_are_not_a_and_b(self):
        self.stops(home("Mast 120RA", "119", "X") + home("Mast 120RC", "119", "X"), "only an A and a B")

    def test_a_name_twice(self):
        self.stops(home("Mast 110L", "109", "T1") + home("Mast 110L", "109", "T2"), "a mast is named twice")


if __name__ == "__main__":
    unittest.main()

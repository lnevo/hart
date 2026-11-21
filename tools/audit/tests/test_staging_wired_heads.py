"""build_masts.py: a wired staging head is wiring.csv's, its notes the owner's (devices_field.csv), and it is kept on
every rebuild; a wired head the rule cannot carry stops the build."""
from __future__ import annotations

import csv
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
import build_device_map as bdm  # noqa: E402
import build_masts as bsm  # noqa: E402
import staging_device_map as sdm  # noqa: E402
from hartlib import devices, level_masts  # noqa: E402


def row(layer, user, system, jmri=None, node="", notes=""):
    """A device map row (build_device_map.COLUMNS) of staging."""
    return dict(level="1", cp="Plane", layer=layer, user_name=user, system_name=system,
                jmri_name=system if jmri is None else jmri, node=node, dcc="", comment="", trial_name="", notes=notes,
                **dict.fromkeys(bdm.COLUMNS[11:], ""))


def rows_of(text: str) -> list[dict]:
    return list(csv.DictReader(text.splitlines()))


def staging_rows(master_text: str) -> list[dict]:
    """The staging rows of a generated file's text merged with the repo's field file, in the old device-map form."""
    files = devices.Files.here()
    return devices.device_map_rows(devices.parse(master_text, files.master.name, files), ("1",))


def owned(user="Head 6LB", notes="wired (owner, 2026-11-18)") -> dict:
    """A field row of a staging head: its key and the owner's notes."""
    return dict(dict.fromkeys(devices.COLUMNS, ""), level="1", layer="head", user_name=user, notes=notes)


WIRED = row("head", "Head 6LB", "IH432", node="4", notes="wired (owner, 2026-11-18)")
MAST = row("mast", "Mast 6LB", "IF$shsm:basic:one-searchlight(IH432)", node="4")
INTERNAL = row("head", "Head 2L Top", "IH:HART:C1:2L_Top", notes="internal, not wired")


class CommittedMap(unittest.TestCase):
    """The committed devices.csv wires Head 6LB to IH432 on its mast row and its head row (owner,
    2026-11-18). check_wiring_crosswalk.py would also fail if it went missing, but only through tables.xml against
    the regenerated masts.csv."""

    def test_6lb_is_wired_to_ih432(self):
        rows = sdm.read_device_rows(bsm.DEVICE_MAP)
        mast = [r for r in rows if r["layer"] == "mast" and r["user_name"] == "Mast 6LB"]
        head = [r for r in rows if r["layer"] == "head" and r["user_name"] == "Head 6LB"]
        self.assertEqual([(r["system_name"], r["jmri_name"]) for r in mast],
                         [("IF$shsm:basic:one-searchlight(IH432)",) * 2])
        self.assertEqual([(r["system_name"], r["jmri_name"]) for r in head], [("IH432", "IH432")])


def wiring_file(text: str) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / "wiring.csv"
    p.write_text(text, encoding="utf-8")
    return p


class WiringHeads(unittest.TestCase):
    """wiring_heads: a wired head's address, node and wiring text are wiring.csv's, its notes its field row's; a field
    head row it does not list stops."""
    HEAD = ",".join(bsm.wiring.COLUMNS) + "\n"

    def test_the_committed_head(self):
        got = bsm.wiring_heads([owned()])
        h = got["Mast 6LB"]["Head 6LB"]
        self.assertEqual((h["jmri_name"], h["node"], h["comment"], h["notes"]),
                         ("IH432", "4", "Node: 4 Signal: 0 | OU: 2 Ports: 1,2,3", "wired (owner, 2026-11-18)"))

    def test_a_moved_head_follows_wiring_csv(self):
        p = wiring_file(self.HEAD + '1,head,Head 6LB,,,,,4,1,OU2,"4,5,6",wired,\n')
        h = bsm.wiring_heads([owned()], p)["Mast 6LB"]["Head 6LB"]
        self.assertEqual((h["system_name"], h["comment"]), ("IH433", "Node: 4 Signal: 1 | OU: 2 Ports: 4,5,6"))

    def test_a_wired_heads_notes_are_the_owners_else_wiring_csvs_else_wired(self):
        p = wiring_file(self.HEAD + '1,head,Head 6LB,,,,,4,0,OU2,"1,2,3",wired,\n')
        self.assertEqual(bsm.wiring_heads([owned(notes="one high head (owner)")], p)["Mast 6LB"]["Head 6LB"]["notes"],
                         "one high head (owner)")
        self.assertEqual(bsm.wiring_heads([], p)["Mast 6LB"]["Head 6LB"]["notes"], "wired")
        noted = wiring_file(self.HEAD + '1,head,Head 6LB,,,,,4,0,OU2,"1,2,3",wired,from wiring\n')
        self.assertEqual(bsm.wiring_heads([], noted)["Mast 6LB"]["Head 6LB"]["notes"], "from wiring")

    def test_a_wired_head_wiring_csv_does_not_list_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, r"devices_field.csv: Head 6LB \(level 1, head\) has no head row in "
                                                   r"wiring.csv: add its wiring there, or remove the field row"):
            bsm.wiring_heads([owned()], wiring_file(self.HEAD))
        with self.assertRaisesRegex(bsm.RuleError, "Head 6LB is on node 41, no staging node"):
            bsm.wiring_heads([owned()], wiring_file(self.HEAD + '1,head,Head 6LB,,,,,41,0,OU2,"1,2,3",wired,\n'))
        with self.assertRaisesRegex(bsm.RuleError, "is not a staging head name"):
            bsm.wiring_heads([], wiring_file(self.HEAD + '1,head,Signal 6,,,,,4,0,OU2,"1,2,3",wired,\n'))


class WiredHeads(unittest.TestCase):
    """wired_heads: a head row whose jmri_name is not its internal name is wired; anything else odd stops."""

    def test_wired_and_internal_heads(self):
        wired = bsm.wired_heads([MAST, WIRED, INTERNAL])
        self.assertEqual(list(wired), ["Mast 6LB"])
        self.assertEqual(wired["Mast 6LB"]["Head 6LB"]["jmri_name"], "IH432")

    def test_internal_names(self):
        self.assertEqual(bsm.internal_head("Head 24RA Top"), "IH:HART:C1:24RA_Top")
        self.assertEqual(bsm.internal_head("Head 67"), "IH:HART:C1:67")
        with self.assertRaises(bsm.RuleError):
            bsm.internal_head("Head six")

    def test_a_wired_head_that_is_not_lcos_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, "Head 6LB.*neither"):
            bsm.wired_heads([row("head", "Head 6LB", "IT432")])

    def test_system_and_jmri_names_that_differ_stop_either_way(self):
        for system, jmri in (("IH433", "IH432"), ("IH432", "IH:HART:C1:6LB"), ("IH:HART:C1:6LB", "IH432")):
            with self.subTest(system=system, jmri=jmri), self.assertRaisesRegex(bsm.RuleError, "differ"):
                bsm.wired_heads([row("head", "Head 6LB", system, jmri=jmri)])

    def test_a_head_named_twice_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, "two rows"):
            bsm.wired_heads([WIRED, WIRED])

    def test_a_mast_naming_a_wired_head_with_no_head_row_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, r"Mast 6LB names wired head\(s\) \['IH432'\]"):
            bsm.wired_heads([MAST, INTERNAL])

    def test_a_mast_naming_another_masts_wired_head_stops(self):
        other = row("mast", "Mast 6LA", "IF$shsm:basic:one-searchlight(IH432)")
        with self.assertRaisesRegex(bsm.RuleError, r"Mast 6LA names wired head\(s\) \['IH432'\]"):
            bsm.wired_heads([MAST, other, WIRED])

    def test_head_count_must_match_the_wired_heads(self):
        wired = bsm.wired_heads([MAST, WIRED])
        self.assertEqual(bsm.head_names("Mast 6LB", 1, wired), [("IH432", "Head 6LB")])
        with self.assertRaisesRegex(bsm.RuleError, "Mast 6LB: the rule gives 2 head"):
            bsm.head_names("Mast 6LB", 2, wired)
        top = bsm.wired_heads([row("head", "Head 6LB Top", "IH432")])
        with self.assertRaisesRegex(bsm.RuleError, "the rule gives 2 head"):
            bsm.head_names("Mast 6LB", 2, top)          # one of two heads wired: the other is not named

    def test_mast_node(self):
        heads = {"Head 6LB": WIRED}
        self.assertEqual(bsm.mast_node("Mast 6LB", None, {}), "")
        self.assertEqual(bsm.mast_node("Mast 6LB", dict(MAST, node="7"), heads), "7")
        self.assertEqual(bsm.mast_node("Mast 6LB", dict(MAST, node=""), heads), "4")
        two = {"Head 6LB Top": WIRED, "Head 6LB Bottom": dict(WIRED, node="5")}
        with self.assertRaisesRegex(bsm.RuleError, "set the mast row's node"):
            bsm.mast_node("Mast 6LB", None, two)


class Rebuild(unittest.TestCase):
    """build() on the repo's data (built once), and on a copy of its device map with rows changed."""

    @classmethod
    def setUpClass(cls):
        cls.want, cls.gen, _virtual = bsm.build()

    def build_with(self, field_edit=None, wiring_edit=None):
        """build() on a copy of the repo's two device files whose field rows `field_edit(rows)` changed (the owner's
        hand) and of wiring.csv (`wiring_edit(text)`); returns ({path name: text}, generated masts)."""
        with tempfile.TemporaryDirectory() as d:
            files = devices.pair_copy(Path(d))
            if field_edit:
                rows = field_edit([dict(r) for r in devices.field_rows(files)])
                files.field.write_text(devices.master_text(rows), encoding="utf-8")
            text = bsm.wiring.PATH.read_text(encoding="utf-8")
            wf = Path(d) / "wiring.csv"
            wf.write_text(wiring_edit(text) if wiring_edit else text, encoding="utf-8")
            with unittest.mock.patch.object(bsm, "DEVICE_MAP", files.master), \
                    unittest.mock.patch.object(sdm, "DEVICE_MAP", files.master), \
                    unittest.mock.patch.object(bsm.wiring, "PATH", wf), \
                    unittest.mock.patch.object(bsm, "device_files", lambda: files):
                want, gen, _virtual = bsm.build()
            return {p.name: t for p, t in want.items()}, gen

    @staticmethod
    def wire(user, node, index, notes="wired (test)"):
        """A wiring.csv edit that wires head `user` on `node` as LCOS Signal `index` (IH<node><32 + index>)."""
        return lambda text: text + f'1,head,{user},,,,,{node},{index},OU4,"6,7,8",wired,{notes}\n'

    def test_the_wired_head_is_kept(self):
        rows = staging_rows(self.want[devices.Files.here().master])      # the master the build gives, its staging rows
        head = [r for r in rows if r["layer"] == "head" and r["user_name"] == "Head 6LB"]
        self.assertEqual([(r["system_name"], r["jmri_name"], r["node"]) for r in head], [("IH432", "IH432", "4")])
        mast = next(r for r in rows if r["user_name"] == "Mast 6LB")
        self.assertEqual((mast["system_name"], mast["node"]), ("IF$shsm:basic:one-searchlight(IH432)", "4"))
        self.assertEqual(next(m for m in self.gen if m["mast"] == "Mast 6LB")["signal_kind"], "field")

    def test_a_newly_wired_head_is_kept(self):
        out, _gen = self.build_with(wiring_edit=self.wire("Head 2R", 13, 0))
        rows = staging_rows(out[devices.Files.here().master.name])
        head = next(r for r in rows if r["user_name"] == "Head 2R")
        self.assertEqual((head["jmri_name"], head["node"], head["notes"]), ("IH1332", "13", "wired (test)"))
        mast = next(r for r in rows if r["user_name"] == "Mast 2R")
        self.assertIn("(IH1332)", mast["system_name"])
        self.assertEqual(mast["node"], "13")              # its old row had no node: the head row's
        self.assertIn("IH1332=Head 2R", out[bsm.MASTS.name])

    def test_a_wired_intermediate_is_a_field_signal(self):
        inter = next(m for m in self.gen if "milepost" in m)
        user = "Head " + inter["mast"].removeprefix("Mast ")
        out, gen = self.build_with(wiring_edit=self.wire(user, 13, 1))
        self.assertEqual(next(m for m in gen if m["mast"] == inter["mast"])["signal_kind"], "field")
        sig = next(r for r in rows_of(out[bsm.MASTS.name]) if r["mast"] == inter["mast"])
        self.assertEqual(level_masts.signal_kind(sig), "field")       # the kind follows from the wired head
        self.assertIn("IH1333=" + user, out[bsm.MASTS.name])

    def test_a_wired_head_with_no_mast_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, r"masts the rule does not place: Mast 98L \(Head 98L\)"):
            self.build_with(wiring_edit=self.wire("Head 98L", 13, 2))

    def test_a_wired_head_whose_mast_has_other_heads_stops(self):
        def gone(rows):         # the owner's notes of Head 6LB go with the name wiring.csv no longer has
            return [r for r in rows if r["user_name"] != "Head 6LB"]
        with self.assertRaisesRegex(bsm.RuleError, "Mast 6LB: the rule gives 1 head"):
            self.build_with(gone, lambda text: text.replace("1,head,Head 6LB,", "1,head,Head 6LB Top,"))


if __name__ == "__main__":
    unittest.main()

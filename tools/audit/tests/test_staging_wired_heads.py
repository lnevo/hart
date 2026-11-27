"""device_map_masts.py (build_device_map.py's staging masts): a wired staging head is wiring.csv's, found by its
device ID, its notes the owner's (devices_field.csv, by ID), and it is kept on every rebuild; a wired head the rule
cannot carry stops the build."""
from __future__ import annotations

import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
import build_device_map as bdm  # noqa: E402
import device_map_masts as dmm  # noqa: E402
import staging_device_map as sdm  # noqa: E402
from hartlib import devices  # noqa: E402

SIX_LB = "mast:5:B:west:single"          # Head 6LB's device ID: wiring.csv keys a head by it (naming-layers step 5)


def owned(ident=SIX_LB, notes="wired (owner, 2026-11-18)") -> dict:
    """{id: field row} of a staging head: its key and the owner's notes (field_by_id's form)."""
    return {ident: dict(dict.fromkeys(devices.COLUMNS, ""), level="1", layer="head", id=ident, notes=notes)}


def head_id(user: str) -> str:
    """The device ID of staging head `user` in the repo's name store."""
    return next(i for (lv, i), name in devices.user_names().items() if lv == "1" and name == user)


def wiring_file(text: str) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / "wiring.csv"
    p.write_text(text, encoding="utf-8")
    return p


class CommittedMap(unittest.TestCase):
    """The committed device master wires Head 6LB to IH432 on its mast row and its head row."""

    def test_6lb_is_wired_to_ih432(self):
        rows = sdm.read_device_rows(sdm.DEVICE_MAP)
        mast = [r for r in rows if r["layer"] == "mast" and r["user_name"] == "Mast 6LB"]
        head = [r for r in rows if r["layer"] == "head" and r["user_name"] == "Head 6LB"]
        self.assertEqual([(r["system_name"], r["jmri_name"]) for r in mast],
                         [("IF$shsm:basic:one-searchlight(IH432)",) * 2])
        self.assertEqual([(r["system_name"], r["jmri_name"]) for r in head], [("IH432", "IH432")])


class WiredHeads(unittest.TestCase):
    """wired_heads: a wired head's address, node and wiring text are wiring.csv's, by its ID, its notes its field
    row's; a field head row wiring.csv does not list stops."""
    HEAD = ",".join(dmm.wiring.COLUMNS) + "\n"

    def test_the_committed_head(self):
        h = dmm.wired_heads(owned())[SIX_LB]
        self.assertEqual((h["jmri_name"], h["node"], h["comment"], h["notes"]),
                         ("IH432", "4", "Node: 4 Signal: 0 | OU: 2 Ports: 1,2,3", "wired (owner, 2026-11-18)"))

    def test_a_moved_head_follows_wiring_csv(self):
        p = wiring_file(self.HEAD + f'1,head,{SIX_LB},,,,,,4,1,OU2,"4,5,6",wired,\n')
        h = dmm.wired_heads(owned(), p)[SIX_LB]
        self.assertEqual((h["system_name"], h["comment"]), ("IH433", "Node: 4 Signal: 1 | OU: 2 Ports: 4,5,6"))

    def test_a_wired_heads_notes_are_the_owners_else_wiring_csvs_else_wired(self):
        p = wiring_file(self.HEAD + f'1,head,{SIX_LB},,,,,,4,0,OU2,"1,2,3",wired,\n')
        self.assertEqual(dmm.wired_heads(owned(notes="one high head (owner)"), p)[SIX_LB]["notes"],
                         "one high head (owner)")
        self.assertEqual(dmm.wired_heads({}, p)[SIX_LB]["notes"], "wired")
        noted = wiring_file(self.HEAD + f'1,head,{SIX_LB},,,,,,4,0,OU2,"1,2,3",wired,from wiring\n')
        self.assertEqual(dmm.wired_heads({}, noted)[SIX_LB]["notes"], "from wiring")

    def test_a_wired_head_wiring_csv_does_not_list_stops(self):
        with self.assertRaisesRegex(dmm.RuleError, rf"devices_field.csv: head {SIX_LB} has no head row in "
                                                   r"wiring.csv: add its wiring there, or remove the field row"):
            dmm.wired_heads(owned(), wiring_file(self.HEAD))
        with self.assertRaisesRegex(dmm.RuleError, "Head 6LB is on node 41, no staging node"):
            dmm.wired_heads(owned(), wiring_file(self.HEAD + f'1,head,{SIX_LB},,,,,,41,0,OU2,"1,2,3",wired,\n'))
        with self.assertRaisesRegex(dmm.RuleError, "a head.s id is its mast.s id and its place"):  # the mast's id
            dmm.wired_heads({}, wiring_file(self.HEAD + '1,head,mast:5:B:west,,,,,,4,0,OU2,"1,2,3",wired,\n'))


class Rebuild(unittest.TestCase):
    """staging_masts on the repo's data (built once), and on a copy of its device files and wiring.csv."""

    @classmethod
    def setUpClass(cls):
        cls.solved = bdm.solve()[:3]
        cls.got = cls.build_with()

    @classmethod
    def build_with(cls, wiring_edit=None):
        """staging_masts on a copy of the repo's two device files and of wiring.csv (`wiring_edit(text)`)."""
        with tempfile.TemporaryDirectory() as d:
            files = devices.pair_copy(Path(d))
            text = dmm.wiring.PATH.read_text(encoding="utf-8")
            wf = Path(d) / "wiring.csv"
            wf.write_text(wiring_edit(text) if wiring_edit else text, encoding="utf-8")
            with unittest.mock.patch.object(dmm.wiring, "PATH", wf):
                return dmm.staging_masts(*cls.solved, [r.cells() for r in devices.load(files)], files)

    @staticmethod
    def wire(user, node, index, notes="wired (test)", ident=None):
        """A wiring.csv edit that wires head `user` (by its device ID, `ident` or the name store's) on `node` as LCOS
        Signal `index` (IH<node><32 + index>)."""
        ident = ident or head_id(user)
        return lambda text: text + f'1,head,{ident},,,,,,{node},{index},OU4,"6,7,8",wired,{notes}\n'

    @staticmethod
    def by_name(got):
        return {r["user_name"]: r for r in got["rows"]}

    def test_the_wired_head_is_kept(self):
        rows = self.by_name(self.got)
        head = rows["Head 6LB"]
        self.assertEqual((head["system_name"], head["jmri_name"], head["node"]), ("IH432", "IH432", "4"))
        mast = rows["Mast 6LB"]
        self.assertEqual((mast["system_name"], mast["id"]), ("IF$shsm:basic:one-searchlight(IH432)", "mast:5:B:west"))
        self.assertEqual(mast["node"], "4")
        self.assertEqual(next(m for m in self.got["placed"] if m["mast"] == "Mast 6LB")["signal_kind"], "field")

    def test_a_newly_wired_head_is_kept(self):
        rows = self.by_name(self.build_with(wiring_edit=self.wire("Head 2R", 13, 0)))
        head = rows["Head 2R"]
        self.assertEqual((head["jmri_name"], head["node"], head["notes"]), ("IH1332", "13", "wired (test)"))
        mast = rows["Mast 2R"]
        self.assertIn("(IH1332)", mast["system_name"])
        self.assertEqual(mast["node"], "13")              # no field node: the head row's

    def test_a_wired_intermediate_is_a_field_signal(self):
        inter = next(m for m in self.got["placed"] if "milepost" in m)
        user = "Head " + inter["mast"].removeprefix("Mast ")
        got = self.build_with(wiring_edit=self.wire(user, 13, 1))
        self.assertEqual(next(m for m in got["placed"] if m["mast"] == inter["mast"])["signal_kind"], "field")
        self.assertIn("(IH1333)", self.by_name(got)[inter["mast"]]["system_name"])

    def test_a_wired_head_the_device_master_does_not_have_stops(self):
        # wiring.csv names a head by its device ID, so a head of no mast the rule places has no ID to give
        with self.assertRaisesRegex(dmm.RuleError, "mast:97:A:west:single is no level 1 device of the device master"):
            self.build_with(wiring_edit=self.wire("Head 98L", 13, 2, ident="mast:97:A:west:single"))


if __name__ == "__main__":
    unittest.main()

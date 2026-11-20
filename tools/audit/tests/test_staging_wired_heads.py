"""build_staging_masts.py: a wired staging head is read from the staging rows of devices.csv and kept on every rebuild;
a wired head the rule cannot carry stops the build."""
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
import build_staging_masts as bsm  # noqa: E402
import staging_device_map as sdm  # noqa: E402
from hartlib import devices  # noqa: E402


def row(layer, user, system, jmri=None, node="", notes=""):
    """A device map row (build_device_map.COLUMNS) of staging."""
    return dict(level="1", cp="Plane", layer=layer, user_name=user, system_name=system,
                jmri_name=system if jmri is None else jmri, node=node, dcc="", comment="", trial_name="", notes=notes,
                **dict.fromkeys(bdm.COLUMNS[11:], ""))


def rows_of(text: str) -> list[dict]:
    return list(csv.DictReader(text.splitlines()))


WIRED = row("head", "Head 6LB", "IH432", node="4", notes="wired (owner, 2026-11-18)")
MAST = row("mast", "Mast 6LB", "IF$shsm:basic:one-searchlight(IH432)", node="4")
INTERNAL = row("head", "Head 2L Top", "IH:HART:C1:2L_Top", notes="internal, not wired")


class CommittedMap(unittest.TestCase):
    """The committed devices.csv wires Head 6LB to IH432 on its mast row and its head row (owner,
    2026-11-18). check_wiring_crosswalk.py would also fail if it went missing, but only through tables.xml against
    the regenerated staging_masts.csv."""

    def test_6lb_is_wired_to_ih432(self):
        rows = sdm.read_device_rows(bsm.DEVICE_MAP)
        mast = [r for r in rows if r["layer"] == "mast" and r["user_name"] == "Mast 6LB"]
        head = [r for r in rows if r["layer"] == "head" and r["user_name"] == "Head 6LB"]
        self.assertEqual([(r["system_name"], r["jmri_name"]) for r in mast],
                         [("IF$shsm:basic:one-searchlight(IH432)",) * 2])
        self.assertEqual([(r["system_name"], r["jmri_name"]) for r in head], [("IH432", "IH432")])


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

    def build_with(self, edit):
        """build() on a copy of the repo's devices.csv whose staging device-map rows `edit(rows)` changed (the mast and
        head rows it gives are the ones bsm holds); returns ({path name: text}, generated masts)."""
        with tempfile.TemporaryDirectory() as d:
            real = devices.Files.here()
            files = real.but(master=Path(d) / "devices.csv", staging=Path(d) / real.staging.name,
                             main_upper=Path(d) / real.main_upper.name, name_map=Path(d) / real.name_map.name)
            held = list(devices.load(real))
            rows = edit(devices.device_map_rows(held, ("1",)))
            prior = {(r["level"], r["layer"], r["user_name"]): r for r in held}
            mine = [devices.master_row(r, "build_staging_masts.py", prior.get((r["level"], r["layer"], r["user_name"])))
                    for r in rows if r["layer"] in bsm.WRITES]
            held = devices.replace_rows(held, "build_staging_masts.py", mine)
            for path, text in devices.texts(held, files).items():
                path.write_text(text, encoding="utf-8")
            with unittest.mock.patch.object(bsm, "DEVICE_MAP", files.master), \
                    unittest.mock.patch.object(sdm, "DEVICE_MAP", files.master), \
                    unittest.mock.patch.object(bsm, "device_files", lambda: files):
                want, gen, _virtual = bsm.build()
            return {p.name: t for p, t in want.items()}, gen

    @staticmethod
    def wire(user, ih, node):
        """An edit that wires head `user` to `ih` on `node`."""
        def edit(rows):
            for r in rows:
                if r["layer"] == "head" and r["user_name"] == user:
                    r.update(system_name=ih, jmri_name=ih, node=node, notes="wired (test)")
            return rows
        return edit

    def test_the_wired_head_is_kept(self):
        rows = rows_of(self.want[devices.Files.here().staging])      # the generated staging file: what the master gives
        head = [r for r in rows if r["layer"] == "head" and r["user_name"] == "Head 6LB"]
        self.assertEqual([(r["system_name"], r["jmri_name"], r["node"]) for r in head], [("IH432", "IH432", "4")])
        mast = next(r for r in rows if r["user_name"] == "Mast 6LB")
        self.assertEqual((mast["system_name"], mast["node"]), ("IF$shsm:basic:one-searchlight(IH432)", "4"))
        self.assertEqual(next(m for m in self.gen if m["mast"] == "Mast 6LB")["signal_kind"], "field")

    def test_a_newly_wired_head_is_kept(self):
        out, _gen = self.build_with(self.wire("Head 2R", "IH999", "9"))
        rows = rows_of(out[devices.Files.here().staging.name])
        head = next(r for r in rows if r["user_name"] == "Head 2R")
        self.assertEqual((head["jmri_name"], head["node"], head["notes"]), ("IH999", "9", "wired (test)"))
        mast = next(r for r in rows if r["user_name"] == "Mast 2R")
        self.assertIn("(IH999)", mast["system_name"])
        self.assertEqual(mast["node"], "9")              # its old row had no node: the head row's
        self.assertIn("IH999=Head 2R", out[bsm.MASTS.name])

    def test_a_wired_intermediate_is_a_field_signal(self):
        inter = next(m for m in self.gen if "milepost" in m)
        user = "Head " + inter["mast"].removeprefix("Mast ")
        out, gen = self.build_with(self.wire(user, "IH998", "9"))
        self.assertEqual(next(m for m in gen if m["mast"] == inter["mast"])["signal_kind"], "field")
        sig = next(r for r in rows_of(out[bsm.SIGNALS.name]) if r["mast"] == inter["mast"])
        self.assertEqual(sig["signal_kind"], "field")
        self.assertIn("IH998=" + user, out[bsm.MASTS.name])

    def test_a_wired_head_with_no_mast_stops(self):
        def extra(rows):
            return rows + [row("head", "Head 98L", "IH998", node="9")]
        with self.assertRaisesRegex(bsm.RuleError, r"masts the rule does not place: Mast 98L \(Head 98L\)"):
            self.build_with(extra)

    def test_a_wired_head_whose_mast_has_other_heads_stops(self):
        def split(rows):
            for r in rows:
                if r["user_name"] == "Head 6LB":
                    r["user_name"] = "Head 6LB Top"
            return rows
        with self.assertRaisesRegex(bsm.RuleError, "Mast 6LB: the rule gives 1 head"):
            self.build_with(split)


if __name__ == "__main__":
    unittest.main()

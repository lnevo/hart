"""build_staging_masts.py: a wired staging head is read from device_map_staging.csv and kept on every rebuild; a wired
head the rule cannot carry stops the build."""
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


def row(layer, user, system, jmri=None, node="", notes=""):
    """A device map row (build_device_map.COLUMNS) of staging."""
    return dict(level="1", cp="Plane", layer=layer, user_name=user, system_name=system,
                jmri_name=system if jmri is None else jmri, node=node, dcc="", comment="", trial_name="", notes=notes)


WIRED = row("head", "Head 6LB", "IH432", node="4", notes="wired (owner, 2026-11-18)")
MAST = row("mast", "Mast 6LB", "IF$shsm:basic:one-searchlight(IH432)", node="4")
INTERNAL = row("head", "Head 2L Top", "IH:HART:C1:2L_Top", notes="internal, not wired")


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

    def test_a_wired_head_whose_system_name_differs_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, "system_name"):
            bsm.wired_heads([row("head", "Head 6LB", "IH433", jmri="IH432")])

    def test_a_head_named_twice_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, "two rows"):
            bsm.wired_heads([WIRED, WIRED])

    def test_a_mast_naming_a_wired_head_with_no_head_row_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, r"Mast 6LB names wired head\(s\) \['IH432'\]"):
            bsm.wired_heads([MAST, INTERNAL])

    def test_head_count_must_match_the_wired_heads(self):
        wired = bsm.wired_heads([MAST, WIRED])
        self.assertEqual(bsm.head_names("Mast 6LB", 1, wired), [("IH432", "Head 6LB")])
        with self.assertRaisesRegex(bsm.RuleError, "Mast 6LB: the rule gives 2 head"):
            bsm.head_names("Mast 6LB", 2, wired)
        top = bsm.wired_heads([row("head", "Head 6LB Top", "IH432")])
        with self.assertRaisesRegex(bsm.RuleError, "the rule gives 2 head"):
            bsm.head_names("Mast 6LB", 2, top)          # one of two heads wired: the other is not named


class Rebuild(unittest.TestCase):
    """build() on the repo's data, and on a copy of its device map with one row changed."""

    def build_with(self, edit):
        """build() with DEVICE_MAP a copy of the repo's that `edit(rows)` changed; returns {path name: text}."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / bsm.DEVICE_MAP.name
            shutil.copy(bsm.DEVICE_MAP, path)
            with path.open(newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            rows = edit(rows)
            with path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=bdm.COLUMNS, lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
            with unittest.mock.patch.object(bsm, "DEVICE_MAP", path):
                want, _gen = bsm.build()
            return {p.name: t for p, t in want.items()}

    def test_the_wired_head_is_kept(self):
        want, gen = bsm.build()
        rows = list(csv.DictReader(want[bsm.DEVICE_MAP].splitlines()))
        head = [r for r in rows if r["layer"] == "head" and r["user_name"] == "Head 6LB"]
        self.assertEqual([(r["system_name"], r["jmri_name"], r["node"]) for r in head], [("IH432", "IH432", "4")])
        mast = next(r for r in rows if r["user_name"] == "Mast 6LB")
        self.assertEqual(mast["system_name"], "IF$shsm:basic:one-searchlight(IH432)")
        self.assertEqual(next(m for m in gen if m["mast"] == "Mast 6LB")["signal_kind"], "field")

    def test_a_newly_wired_head_is_kept(self):
        def wire(rows):
            for r in rows:
                if r["user_name"] == "Head 2R":
                    r.update(system_name="IH999", jmri_name="IH999", node="9", notes="wired (test)")
            return rows
        out = self.build_with(wire)
        rows = list(csv.DictReader(out[bsm.DEVICE_MAP.name].splitlines()))
        head = next(r for r in rows if r["user_name"] == "Head 2R")
        self.assertEqual((head["jmri_name"], head["node"], head["notes"]), ("IH999", "9", "wired (test)"))
        self.assertIn("(IH999)", next(r for r in rows if r["user_name"] == "Mast 2R")["system_name"])
        self.assertIn("IH999=Head 2R", out[bsm.MASTS.name])

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

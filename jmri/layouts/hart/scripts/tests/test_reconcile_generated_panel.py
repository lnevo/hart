"""reconcile_dispatcher_stations.py on a generated Layout Editor panel (LE cut-over, Phase 3).

On a generated panel (hidden marker label, hartlib.tables) the station clusters keep where they stand, or go back
where they stood on --reference (the tables before Stage 1); STATION_ICON_POSITIONS are the hand-drawn panel's.
"""
from __future__ import annotations

import contextlib
import copy
import io
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import paths, tables  # noqa: E402

from test_reconcile_dispatcher_stations import reconciler  # noqa: E402


def marked() -> ET.ElementTree:
    tree = ET.ElementTree(tables.read(paths.REPO_TABLES_XML))
    reconciler.main_layout_editor(tree.getroot()).insert(1, tables.generated_marker_label())
    return tree


def clusters(root: ET.Element) -> dict[str, list[tuple]]:
    out: dict[str, list[tuple]] = {}
    for icon in reconciler.main_layout_editor(root).findall("sensoricon"):
        if icon.get("level") == reconciler.CLUSTER_LEVEL:
            out.setdefault(icon.get("sensor"), []).append((icon.get("x"), icon.get("y")))
    return out


def shift_clusters(root: ET.Element, dx: int = 40) -> None:
    for icon in reconciler.main_layout_editor(root).findall("sensoricon"):
        if icon.get("level") == reconciler.CLUSTER_LEVEL:
            icon.set("x", str(int(icon.get("x")) + dx))


class GeneratedStationsTest(unittest.TestCase):
    def test_a_generated_panel_keeps_its_clusters_where_they_stand(self) -> None:
        tree = marked()
        shift_clusters(tree.getroot())       # off the hand-drawn pixels
        before = clusters(tree.getroot())
        # the hand-drawn panel's buttons read "Track K-1": on a generated panel they read "K-1" (owner, 2026-11-16),
        # so the first run rewrites only those buttons' text, in place
        changes = reconciler.reconcile(tree)
        self.assertTrue(changes.details)
        self.assertTrue(all(d.startswith("reconciled icon MoveToTrack_") for d in changes.details), changes.details)
        self.assertEqual(before, clusters(tree.getroot()))
        for icon in reconciler.main_layout_editor(tree.getroot()).findall("sensoricon"):
            if (icon.get("sensor") or "").startswith("MoveTo"):
                self.assertFalse((icon.get("text") or "").startswith("Track "), icon.get("sensor"))
        changes = reconciler.reconcile(tree)
        self.assertEqual(0, changes.total, changes.details)
        self.assertEqual(before, clusters(tree.getroot()))

    def test_the_hand_drawn_panel_still_takes_its_pixels(self) -> None:
        tree = ET.ElementTree(tables.read(paths.REPO_TABLES_XML))
        shift_clusters(tree.getroot())
        self.assertGreater(reconciler.reconcile(tree).total, 0)
        self.assertEqual(clusters(tables.read(paths.REPO_TABLES_XML)), clusters(tree.getroot()))

    def test_reference_puts_stage1_clusters_back(self) -> None:
        reference = marked()
        tree = copy.deepcopy(reference)
        shift_clusters(tree.getroot())
        ref_le = reconciler.main_layout_editor(reference.getroot())
        changes = reconciler.reconcile(tree, ref_le)
        self.assertGreater(changes.total, 0)
        self.assertEqual(clusters(reference.getroot()), clusters(tree.getroot()))

    def test_an_icon_missing_from_the_reference_keeps_the_panels_own_copy(self) -> None:
        reference = marked()
        ref_le = reconciler.main_layout_editor(reference.getroot())
        for icon in list(ref_le.findall("sensoricon")):
            if icon.get("sensor") == "MoveToTrack_K-1_stored":
                ref_le.remove(icon)
        tree = marked()
        shift_clusters(tree.getroot())
        own = clusters(tree.getroot())["MoveToTrack_K-1_stored"]
        reconciler.reconcile(tree, ref_le)
        got = clusters(tree.getroot())
        self.assertEqual(own, got["MoveToTrack_K-1_stored"])
        self.assertEqual(clusters(reference.getroot())["MoveToTrack_K-2_stored"], got["MoveToTrack_K-2_stored"])

    def test_a_moveto_icon_found_nowhere_stops(self) -> None:
        tree = marked()
        le = reconciler.main_layout_editor(tree.getroot())
        for icon in list(le.findall("sensoricon")):
            if icon.get("sensor") == "MoveToTrack_K-1_stored":
                le.remove(icon)
        with self.assertRaisesRegex(ValueError, "Track K-1: no single MoveToTrack_K-1_stored icon"):
            reconciler.reconcile(tree)

    def test_progress_and_lamp_missing_take_the_offset_from_moveto(self) -> None:
        tree = marked()
        le = reconciler.main_layout_editor(tree.getroot())
        move_to = next(i for i in le.findall("sensoricon") if i.get("sensor") == "MoveToTrack_K-2_stored")
        for icon in list(le.findall("sensoricon")):
            if icon.get("sensor") == "MoveInProgressTrack_K-2":
                le.remove(icon)
        reconciler.reconcile(tree)
        progress = clusters(tree.getroot())["MoveInProgressTrack_K-2"]
        self.assertEqual([(str(int(move_to.get("x")) - reconciler.PAIR_DX), move_to.get("y"))], progress)

    def test_a_hand_drawn_reference_is_refused_for_a_generated_panel(self) -> None:
        tree = marked()
        hand = reconciler.main_layout_editor(tables.read(paths.REPO_TABLES_XML))
        with self.assertRaisesRegex(ValueError, "not a generated one"):
            reconciler.reconcile(tree, hand)

    def test_a_reference_on_the_hand_drawn_panel_is_noted(self) -> None:
        tree = ET.ElementTree(tables.read(paths.REPO_TABLES_XML))
        ref = reconciler.main_layout_editor(marked().getroot())
        with contextlib.redirect_stdout(io.StringIO()) as out:
            changes = reconciler.reconcile(tree, ref)
        self.assertEqual(0, changes.total)
        self.assertIn("--reference not used", out.getvalue())


if __name__ == "__main__":
    unittest.main()

"""reconcile_dispatcher_stations.py on the generated Layout Editor panel, once the Dispatcher System is unparked.

The fixture is this checkout's tables with the Dispatcher System put back from the parked file
(hartlib.parked.with_parked). The station clusters keep where they stand, or go back where they stood on --reference
(the tables before Stage 1); a panel that is not generated is refused.
"""
from __future__ import annotations

import copy
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import parked, paths, tables  # noqa: E402

from test_reconcile_dispatcher_stations import reconciler  # noqa: E402

UNPARKED = parked.with_parked({"dispatcher"}, paths.REPO_TABLES_XML)


def marked() -> ET.ElementTree:
    """The generated panel with the Dispatcher System put back (a copy each time)."""
    return ET.ElementTree(copy.deepcopy(UNPARKED))


def unmarked() -> ET.ElementTree:
    tree = marked()
    le = tables.layout_editor(tree.getroot())
    le.remove(le.find(f"positionablelabel[@text='{tables.GENERATED_PANEL_MARKER}']"))
    return tree


def clusters(root: ET.Element) -> dict[str, list[tuple]]:
    out: dict[str, list[tuple]] = {}
    for icon in tables.layout_editor(root).findall("sensoricon"):
        if icon.get("level") == reconciler.CLUSTER_LEVEL:
            out.setdefault(icon.get("sensor"), []).append((icon.get("x"), icon.get("y")))
    return out


def shift_clusters(root: ET.Element, dx: int = 40) -> None:
    for icon in tables.layout_editor(root).findall("sensoricon"):
        if icon.get("level") == reconciler.CLUSTER_LEVEL:
            icon.set("x", str(int(icon.get("x")) + dx))


class GeneratedStationsTest(unittest.TestCase):
    def test_a_jmri_stored_cluster_is_kept_as_it_is(self) -> None:
        """After Stage 1 PanelPro stores the clusters its own way (attribute order, fonts, editable="false"); the
        check keeps them as they are."""
        tree = marked()
        reconciler.reconcile(tree)                           # the build's clusters, as they stand
        editor = tables.layout_editor(tree.getroot())
        for icon in editor.findall("sensoricon"):
            if (icon.get("sensor") or "").startswith(("MoveTo", "MoveInProgress")):
                attrs = dict(reversed(list(icon.attrib.items())), editable="false")
                if (icon.get("sensor") or "").startswith("MoveTo"):
                    attrs.update(fontFamily="Lucida Grande", fontname="LucidaGrande-Bold")
                icon.attrib.clear()
                icon.attrib.update(attrs)
        stored = ET.tostring(tree.getroot())
        changes = reconciler.reconcile(tree)
        self.assertEqual(0, changes.total, changes.details)
        self.assertEqual(ET.tostring(tree.getroot()).count(b'editable="false"'), stored.count(b'editable="false"'))

    def test_a_generated_panel_keeps_its_clusters_where_they_stand(self) -> None:
        tree = marked()
        reconciler.reconcile(tree)              # the parked file's station lamps are not in it: created once
        shift_clusters(tree.getroot())
        before = clusters(tree.getroot())
        # a button that reads "Track K-1" is rewritten in place to "K-1" (owner, 2026-11-16)
        le = tables.layout_editor(tree.getroot())
        button = next(i for i in le.findall("sensoricon") if i.get("sensor") == "MoveToTrack_K-1_stored")
        button.set("text", "Track K-1")
        changes = reconciler.reconcile(tree)
        self.assertEqual(["reconciled icon MoveToTrack_K-1_stored"], changes.details)
        self.assertEqual(before, clusters(tree.getroot()))
        for icon in tables.layout_editor(tree.getroot()).findall("sensoricon"):
            if (icon.get("sensor") or "").startswith("MoveTo"):
                self.assertFalse((icon.get("text") or "").startswith("Track "), icon.get("sensor"))
        changes = reconciler.reconcile(tree)
        self.assertEqual(0, changes.total, changes.details)
        self.assertEqual(before, clusters(tree.getroot()))

    def test_a_panel_that_is_not_generated_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "'HART Railroad' panel is not a generated one"):
            reconciler.reconcile(unmarked())

    def test_reference_puts_stage1_clusters_back(self) -> None:
        reference = marked()
        reconciler.reconcile(reference)
        tree = copy.deepcopy(reference)
        shift_clusters(tree.getroot())
        ref_le = tables.layout_editor(reference.getroot())
        changes = reconciler.reconcile(tree, ref_le)
        self.assertGreater(changes.total, 0)
        self.assertEqual(clusters(reference.getroot()), clusters(tree.getroot()))

    def test_an_icon_missing_from_the_reference_keeps_the_panels_own_copy(self) -> None:
        reference = marked()
        ref_le = tables.layout_editor(reference.getroot())
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
        le = tables.layout_editor(tree.getroot())
        for icon in list(le.findall("sensoricon")):
            if icon.get("sensor") == "MoveToTrack_K-1_stored":
                le.remove(icon)
        with self.assertRaisesRegex(ValueError, "Track K-1: no single MoveToTrack_K-1_stored icon"):
            reconciler.reconcile(tree)

    def test_progress_and_lamp_missing_take_the_offset_from_moveto(self) -> None:
        tree = marked()
        le = tables.layout_editor(tree.getroot())
        move_to = next(i for i in le.findall("sensoricon") if i.get("sensor") == "MoveToTrack_K-2_stored")
        for icon in list(le.findall("sensoricon")):
            if icon.get("sensor") == "MoveInProgressTrack_K-2":
                le.remove(icon)
        reconciler.reconcile(tree)
        progress = clusters(tree.getroot())["MoveInProgressTrack_K-2"]
        self.assertEqual([(str(int(move_to.get("x")) - reconciler.PAIR_DX), move_to.get("y"))], progress)

    def test_a_reference_that_is_not_generated_is_refused(self) -> None:
        tree = marked()
        hand = tables.layout_editor(unmarked().getroot())
        with self.assertRaisesRegex(ValueError, "--reference: the 'HART Railroad' panel is not a generated one"):
            reconciler.reconcile(tree, hand)



if __name__ == "__main__":
    unittest.main()

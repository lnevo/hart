"""audit_sml and audit_generated_dispatcher expect the hand-drawn panel's counts on a hand-drawn panel and the
rehearsed three-level counts on a generated one; a generated panel before discovery may hold the staging logic the
build carries from the live tables (carried_destinations)."""
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_panel_contracts as apc  # noqa: E402


def sml_root(n):
    return pairs_root([(f"Mast {i}", f"Mast {i}x") for i in range(n)])


def pairs_root(pairs):
    root = ET.Element("layout-config")
    logics = ET.SubElement(root, "signalmastlogics")
    for source, target in pairs:
        logic = ET.SubElement(logics, "signalmastlogic", source=source)
        dest = ET.SubElement(logic, "destinationMast", destination=target)
        ET.SubElement(dest, "useLayoutEditor").text = "yes"
    return root


def graph_root(sections, transits):
    root = ET.Element("layout-config")
    s = ET.SubElement(root, "sections")
    for i in range(sections):
        ET.SubElement(s, "section", systemName=f"IY:AUTO:{i}")
    t = ET.SubElement(root, "transits")
    for i in range(transits):
        ET.SubElement(t, "transit", systemName=f"IZ{i}")
    return root


def errors(fn, root, **kw):
    audit = apc.Audit("test", Path("test.xml"))
    fn(root, audit, **kw)
    return [m for m in audit.errors if "SML destinations" in m or "Dispatcher graph" in m]


class ExpectedCounts(unittest.TestCase):
    def test_sml_count_follows_the_panel_kind(self):
        hand, gen = apc.expected_sml(False), apc.expected_sml(True)
        self.assertEqual(errors(apc.audit_sml, sml_root(hand), required=True), [])
        self.assertEqual(errors(apc.audit_sml, sml_root(gen), required=True, generated=True), [])
        self.assertTrue(errors(apc.audit_sml, sml_root(gen), required=True))

    def test_a_generated_panel_before_discovery_holds_the_live_staging_pairs(self):
        """The cut-over candidate as built holds the live tables' destinations between staging masts and none on
        main or upper: a warning; any other set of staging pairs is an error."""
        staging = [("Mast 10RA", "Mast 16L"), ("Mast 38RA", "Mast 36L"), ("Mast 2", "Mast 2035")]
        live = pairs_root(staging + [("Mast 108LA", "Mast 110LA"), ("Mast 40RA", "Mast 136RA")])
        self.assertEqual(apc.carried_destinations(apc.sml_destinations(live)), [s + ("yes",) for s in staging])
        audit = apc.Audit("test", Path("test.xml"))
        apc.audit_sml(pairs_root(staging), audit, required=True, generated=True, live=live)
        self.assertEqual(audit.errors, [])
        self.assertTrue(any("run Stage 1 or stock discovery" in w for w in audit.warnings), audit.warnings)
        for other in (staging[:-1], staging + [("Mast 4", "Mast 6")]):
            self.assertTrue(errors(apc.audit_sml, pairs_root(other), required=True, generated=True, live=live))
        self.assertTrue(errors(apc.audit_sml, pairs_root(staging), required=True, live=live))     # hand-drawn kind

    @mock.patch.object(apc.parked, "PARKED", frozenset())
    def test_dispatcher_graph_follows_the_panel_kind(self):
        for generated in (False, True):
            sections, transits = apc.expected_graph(generated)
            ok = errors(apc.audit_generated_dispatcher, graph_root(sections, transits), generated=generated)
            self.assertEqual(ok, [], generated)
            if not generated:
                other = apc.expected_graph(True)
                self.assertTrue(errors(apc.audit_generated_dispatcher, graph_root(*other)))
        before = apc.expected_graph(False)       # a generated panel before Stage 1: allowed with a warning
        self.assertEqual(errors(apc.audit_generated_dispatcher, graph_root(*before), generated=True), [])
        self.assertTrue(errors(apc.audit_generated_dispatcher, graph_root(before[0] + 1, before[1]), generated=True))

    @mock.patch.object(apc.parked, "PARKED", frozenset({"dispatcher"}))
    def test_a_parked_dispatcher_has_no_graph(self):
        """The Dispatcher System parked (hartlib.parked): tables without sections and transits pass on either panel
        kind, and tables from before the parking that still hold them are held to their counts."""
        empty = ET.Element("layout-config")
        for generated in (False, True):
            self.assertEqual(errors(apc.audit_generated_dispatcher, empty, generated=generated), [])
            self.assertEqual(errors(apc.audit_generated_dispatcher, graph_root(*apc.expected_graph(generated)),
                                    generated=generated), [])
            self.assertTrue(errors(apc.audit_generated_dispatcher, graph_root(1, 1), generated=generated))


if __name__ == "__main__":
    unittest.main()

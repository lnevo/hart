"""audit_sml and audit_generated_dispatcher expect the hand-drawn panel's counts on a hand-drawn panel and the
rehearsed three-level counts on a generated one."""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_panel_contracts as apc  # noqa: E402


def sml_root(n):
    root = ET.Element("layout-config")
    logics = ET.SubElement(root, "signalmastlogics")
    for i in range(n):
        logic = ET.SubElement(logics, "signalmastlogic", source=f"Mast {i}")
        dest = ET.SubElement(logic, "destinationMast", destination=f"Mast {i}x")
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
        hand, gen = apc.EXPECTED_SML[False], apc.EXPECTED_SML[True]
        self.assertEqual(errors(apc.audit_sml, sml_root(hand), required=True), [])
        self.assertEqual(errors(apc.audit_sml, sml_root(gen), required=True, generated=True), [])
        self.assertTrue(errors(apc.audit_sml, sml_root(gen), required=True))
        self.assertTrue(errors(apc.audit_sml, sml_root(hand), required=True, generated=True))

    def test_dispatcher_graph_follows_the_panel_kind(self):
        for generated in (False, True):
            sections, transits = apc.EXPECTED_GRAPH[generated]
            ok = errors(apc.audit_generated_dispatcher, graph_root(sections, transits), generated=generated)
            self.assertEqual(ok, [], generated)
            other = apc.EXPECTED_GRAPH[not generated]
            bad = errors(apc.audit_generated_dispatcher, graph_root(*other), generated=generated)
            self.assertTrue(bad, generated)


if __name__ == "__main__":
    unittest.main()

"""hartlib.startup_logixng: the LogixNG that sets the virtual detectors and turnouts when the tables load, put into
the template's LogixNG sections, and the templates it refuses."""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import level_devices as L, startup_logixng as sl, tables  # noqa: E402
from hartlib.tables_sections import CONDITIONALNGS, DIGITAL_ACTIONS, LOGIXNGS, TablesBuildError  # noqa: E402


def template(*sections: tuple[str, str | None]) -> ET.Element:
    root = ET.Element("layout-config")
    for tag, cls in sections:
        ET.SubElement(root, tag, {"class": cls or ""})
    return root


ALL = (LOGIXNGS, CONDITIONALNGS, DIGITAL_ACTIONS)


class StartLogixNG(unittest.TestCase):
    def test_one_socket_per_action_in_their_order(self) -> None:
        root = template(*ALL)
        actions = [sl.start_action("occupancy", "IQDA:A1", "IS:B:1", "Inactive"),
                   sl.start_action("turnout", "IQDA:A2", "IT:1", "Thrown")]
        sl.start_logixng(root, actions)
        logix, conditional, digital = (root.find(t) for t, _c in ALL)
        self.assertEqual([L.CLEAR_LOGIXNG], [tables.system_name(e) for e in logix])
        self.assertEqual([L.CLEAR_CONDITIONAL], [tables.system_name(e) for e in conditional])
        self.assertEqual([L.CLEAR_MANY, "IQDA:A1", "IQDA:A2"], [tables.system_name(e) for e in digital])
        many = digital[0]
        self.assertEqual([("A1", "IQDA:A1"), ("A2", "IQDA:A2")],
                         [(s.findtext("socketName"), s.findtext("systemName")) for s in many.find("Actions")])
        self.assertEqual("ActionTurnout", digital[2].tag)
        self.assertEqual("Thrown", digital[2].find("state").findtext("enum"))
        self.assertIsNotNone(many.find("MaleSocket/AbstractMaleSocket"))

    def test_a_template_without_a_logixng_section_stops(self) -> None:
        with self.assertRaisesRegex(TablesBuildError, "no LogixNGConditionalNGs section"):
            sl.start_logixng(template(LOGIXNGS, DIGITAL_ACTIONS), [])

    def test_a_template_holding_the_startup_names_stops(self) -> None:
        root = template(*ALL)
        held = ET.SubElement(root.find(LOGIXNGS[0]), "LogixNG")
        ET.SubElement(held, "systemName").text = L.CLEAR_LOGIXNG
        with self.assertRaisesRegex(TablesBuildError, "holds the startup LogixNG's names"):
            sl.start_logixng(root, [])


if __name__ == "__main__":
    unittest.main()

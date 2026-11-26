"""build_lcos_signal_manager_plan.load_live_ids: the detectors and turnouts are devices.csv's by layer and role, never by
name (hand-off row 8); a tables.xml bean with no devices.csv row is left out with a warning naming it."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_lcos_signal_manager_plan",
                                              ROOT / "tools/wiring/build_lcos_signal_manager_plan.py")
PLAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLAN)


class LiveIds(unittest.TestCase):
    def test_an_unlisted_bean_is_named_and_left_out(self) -> None:
        doc = ET.parse(PLAN.TABLES)
        root = doc.getroot()
        sensors = next(s for s in root.iter("sensors") if "Mqtt" in (s.get("class") or ""))
        sensors.append(ET.fromstring("<sensor inverted=\"false\"><systemName>M2S9998</systemName>"
                                     "<userName>BS Ghost</userName><comment>Node: 99 Block: 8</comment></sensor>"))
        turnouts = next(s for s in root.iter("turnouts") if "Mqtt" in (s.get("class") or ""))
        turnouts.append(ET.fromstring("<turnout inverted=\"false\"><systemName>M2T9998</systemName>"
                                      "<userName>Switch 998</userName><comment>Node: 99 Turnout: 8</comment>"
                                      "</turnout>"))
        with tempfile.TemporaryDirectory() as tmp:
            tables = Path(tmp) / "tables.xml"
            doc.write(tables, encoding="utf-8", xml_declaration=True)
            err = io.StringIO()
            with mock.patch.object(PLAN, "TABLES", tables), contextlib.redirect_stderr(err):
                blocks, switches = PLAN.load_live_ids()
        self.assertNotIn("BS Ghost", blocks)
        self.assertNotIn("Switch 998", switches)
        self.assertIn("Switch 1", switches)
        self.assertTrue(blocks)
        self.assertIn("sensor M2S9998 (BS Ghost)", err.getvalue())
        self.assertIn("turnout M2T9998 (Switch 998)", err.getvalue())

    def test_the_committed_tables_warn_of_nothing(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            PLAN.load_live_ids()
        self.assertEqual(err.getvalue(), "")


class PlanErrors(unittest.TestCase):
    def test_a_malformed_port_id_raises_the_plan_error(self) -> None:
        with self.assertRaisesRegex(PLAN.SignalPlanError, "bad port_id nonsense"):
            PLAN.port_index("nonsense")

    def test_main_exits_with_the_plan_error(self) -> None:
        with mock.patch.object(PLAN, "load_live_ids", return_value=({}, {})), \
                mock.patch.object(PLAN, "signal_rows", side_effect=PLAN.SignalPlanError("signals differ: ['X']")), \
                self.assertRaises(SystemExit) as stop:
            PLAN.main()
        self.assertEqual(stop.exception.code, "signals differ: ['X']")


if __name__ == "__main__":
    unittest.main()

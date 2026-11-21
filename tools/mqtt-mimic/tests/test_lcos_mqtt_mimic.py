from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "lcos_mqtt_mimic", SCRIPTS / "lcos_mqtt_mimic.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LcosMimicNamingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.m = load_module()
        cls.layout = cls.m.load_layout()

    def test_turnouts_use_ctc_numbers_and_cps(self) -> None:
        by_label = {t["label"]: t for t in self.layout["turnouts"]}
        self.assertIn("Switch 1", by_label)
        self.assertNotIn("Switch 100", by_label)
        self.assertEqual(by_label["Switch 1"]["plant"], "Brick")
        self.assertEqual(by_label["Switch 7"]["plant"], "Barn")
        self.assertEqual(by_label["Switch 13"]["plant"], "Engine House")
        self.assertEqual(by_label["Switch 9"]["plant"], "Engine House")
        self.assertNotIn("West Yard", {t["plant"] for t in self.layout["turnouts"]})

    def test_level_heads_leave_out_the_hidden_virtual_masts(self) -> None:
        # the main and upper virtual masts (buffer-stop destinations) have no heads and no control point; the
        # layout still loads and every head belongs to a visible mast
        masts = {h["mast"] for h in self.layout["heads"] if h.get("level") in ("main", "upper", 2, 3)}
        self.assertTrue(masts)
        self.assertNotIn("Mast 102RA", masts)
        self.assertIn("Mast 120RA", masts)

    def test_occupancy_uses_os_labels(self) -> None:
        labels = {b["label"] for b in self.layout["blocks"]}
        self.assertIn("OS Switch 1", labels)
        self.assertIn("Track S-R", labels)
        self.assertIn("Track Barn", labels)
        self.assertNotIn("West Yard", {b["plant"] for b in self.layout["blocks"]})

    def test_heads_use_mast_prefix_and_cps(self) -> None:
        # Staging heads come from the wiring plan, which lists wired heads only (ADR-024: Mast 6LB on IH432);
        # staging's internal heads (IH:HART:C1:*) publish nothing, so the mimic shows none of them.
        masts = {h["mast"] for h in self.layout["heads"]}
        self.assertIn("Mast 6LB", masts)
        self.assertNotIn("Mast 2L", masts)
        self.assertNotIn("100L", masts)
        by_mast = {h["mast"]: h["plant"] for h in self.layout["heads"]}
        self.assertEqual(by_mast["Mast 6LB"], "Plane")
        self.assertFalse(any(h["id"].startswith("IH:HART:C1:") for h in self.layout["heads"]))

    def test_head_ids_are_packed_mqtt_leaves(self) -> None:
        ids = {h["id"] for h in self.layout["heads"]}
        self.assertIn("432", ids)
        self.assertNotIn("433", ids)      # dropped with Mast 6LB's second head (ADR-024)
        self.assertNotIn("IH432", ids)
        by_id = {h["id"]: h for h in self.layout["heads"]}
        self.assertEqual(by_id["432"]["systemName"], "IH432")
        self.assertEqual(self.m._head_leaf("IH432"), "432")
        self.assertEqual(self.m._head_leaf("432"), "432")


class LcosMimicNameMapTest(unittest.TestCase):
    """load_cps reads staging's rows of devices.csv (hartlib.devices.load), cp per user name."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = load_module()

    def test_the_committed_master_gives_each_layer_its_plants(self) -> None:
        cps = self.m.load_cps()
        self.assertEqual(cps["turnout"]["Switch 1"], "Brick")
        self.assertIn("OS Switch 1", cps["block"])
        self.assertTrue(cps["occupancy"] and cps["mast"])

    def test_a_missing_master_gives_empty_layers_and_a_broken_one_stops(self) -> None:
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(self.m, "DEVICES", Path(tmp) / "missing.csv"):
                self.assertEqual(self.m.load_cps(), {"turnout": {}, "occupancy": {}, "block": {}, "mast": {}})
            bad = Path(tmp) / "devices.csv"
            bad.write_text("level,layer\n1,mast\n", encoding="utf-8")
            with mock.patch.object(self.m, "DEVICES", bad), \
                    self.assertRaisesRegex(self.m.devices.DevicesError, "the header is not the master's columns"):
                self.m.load_cps()


    def test_a_bad_master_ends_main_with_one_line_naming_devices_csv(self) -> None:
        import sys
        from unittest import mock
        err = self.m.devices.DevicesError("devices.csv: line 7 (2 mast 'Mast 1L'): description is empty")
        with mock.patch.object(self.m, "load_layout", side_effect=err), \
                mock.patch.object(self.m, "pick_mqtt_host", return_value="127.0.0.1"), \
                mock.patch.object(sys, "argv", ["lcos_mqtt_mimic.py"]), \
                self.assertRaises(SystemExit) as stop:
            self.m.main()
        self.assertEqual(stop.exception.code, f"lcos_mqtt_mimic.py: devices.csv cannot be used: {err}")


if __name__ == "__main__":
    unittest.main()

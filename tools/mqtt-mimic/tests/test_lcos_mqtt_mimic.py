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
    """load_cps reads staging's rows of the device master (hartlib.devices.load), cp per user name."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = load_module()

    def test_the_committed_master_gives_each_layer_its_plants(self) -> None:
        cps = self.m.load_cps()
        self.assertEqual(cps["turnout"]["Switch 1"], "Brick")
        self.assertIn("OS Switch 1", cps["block"])
        self.assertTrue(cps["occupancy"] and cps["mast"])

    def test_an_lcc_alias_is_grouped_by_its_name_and_a_line_detector_by_its_cp(self) -> None:
        cps = self.m.load_cps()
        self.assertEqual(cps["turnout"]["DCC Switch 1"], self.m.infer_plant("DCC Switch 1"))     # not its cp, Brick
        self.assertEqual(cps["turnout"]["DCC Switch 9"], "Engine House")                         # by its name
        self.assertEqual(cps["occupancy"]["BS Barn"], "Barn")                  # the first place of its cp list
        self.assertEqual(cps["block"]["Track East Ext"], "Plane")              # Plane;Barn
        self.assertEqual(cps["block"]["Track Main East"], "Barn")              # Barn;East End
        self.assertEqual(self.m.infer_plant("Track X", "CP 107;CP 123"), "CP 107")
        self.assertEqual(self.m.first_place("CP 127;Princess"), "CP 127")      # a main helix row: its own CP

    def test_a_missing_master_gives_empty_layers_and_a_broken_one_stops(self) -> None:
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(self.m, "DEVICES", Path(tmp) / "missing.csv"):
                self.assertEqual(self.m.load_cps(), {"turnout": {}, "occupancy": {}, "block": {}, "mast": {}})
            bad = Path(tmp) / self.m.devices.ONE_FILE
            bad.write_text("level,layer\n1,mast\n", encoding="utf-8")
            with mock.patch.object(self.m, "DEVICES", bad), \
                    self.assertRaisesRegex(self.m.devices.DevicesError, "the header is not the master's columns"):
                self.m.load_cps()


    def test_the_kinds_come_from_devices_csv_and_an_unlisted_bean_is_named(self) -> None:
        """A sensor or turnout's kind is its device master row's (hand-off row 8). A device not on the layout yet (a
        level-less row) is no detector and stops nothing; a tables.xml bean with no row is left out with a warning
        naming it (a Store not split yet can hold one)."""
        import contextlib
        import io
        import tempfile
        import xml.etree.ElementTree as ET
        from unittest import mock
        from hartlib import tables_build as TB
        D = self.m.devices
        added = ET.fromstring("<sensor inverted=\"false\"><systemName>M2S9999</systemName>"
                              "<userName>BS Store Added</userName></sensor>")
        row = {c: "" for c in D.COLUMNS}
        row.update(layer="occupancy", user_name="BS Store Added", assignment="field", system_name="M2S9999",
                   jmri_name="M2S9999", description="Added in PanelPro.")
        row["jmri_bean"] = TB.bean_json([(TB.MQTT_SENSORS, added)], row)
        with tempfile.TemporaryDirectory() as tmp:
            master = Path(tmp) / self.m.devices.ONE_FILE
            master.write_text(D.master_text(list(D.load()) + [row]), encoding="utf-8")
            doc = ET.parse(self.m.TABLES)
            root = doc.getroot()
            sensors = next(s for s in root.iter("sensors") if "Mqtt" in (s.get("class") or ""))
            sensors.append(added)
            sensors.append(ET.fromstring("<sensor inverted=\"false\"><systemName>M2S9998</systemName>"
                                         "<userName>BS Ghost</userName></sensor>"))
            turnouts = next(s for s in root.iter("turnouts") if "Mqtt" in (s.get("class") or ""))
            turnouts.append(ET.fromstring("<turnout inverted=\"false\"><systemName>M2T9998</systemName>"
                                          "<userName>Switch 998</userName></turnout>"))
            tables = Path(tmp) / "tables.xml"
            doc.write(tables, encoding="utf-8", xml_declaration=True)
            err = io.StringIO()
            with mock.patch.object(self.m, "DEVICES", master), mock.patch.object(self.m, "TABLES", tables), \
                    contextlib.redirect_stderr(err):
                got = self.m.load_layout(levels=False)
        names = {b["userName"] for b in got["blocks"]}
        self.assertNotIn("BS Store Added", names)
        self.assertNotIn("BS Ghost", names)
        self.assertIn("BS Switch 1", names)
        self.assertNotIn("Switch 998", {t["label"] for t in got["turnouts"]})
        self.assertIn("sensor M2S9998 (BS Ghost)", err.getvalue())
        self.assertIn("turnout M2T9998 (Switch 998)", err.getvalue())
        self.assertNotIn("M2S9999", err.getvalue())          # it has its row: not on the layout yet, no warning

    def test_a_bad_master_ends_main_with_one_line_naming_devices_csv(self) -> None:
        import sys
        from unittest import mock
        err = self.m.devices.DevicesError("devices.csv: line 7 (2 mast 'Mast 1L'): description is empty")
        with mock.patch.object(self.m, "load_layout", side_effect=err), \
                mock.patch.object(self.m, "pick_mqtt_host", return_value="127.0.0.1"), \
                mock.patch.object(sys, "argv", ["lcos_mqtt_mimic.py"]), \
                self.assertRaises(SystemExit) as stop:
            self.m.main()
        self.assertEqual(stop.exception.code, f"lcos_mqtt_mimic.py: the device master cannot be used: {err}")



class SortAndReconnect(unittest.TestCase):
    """plant_rank orders unknown plants last; the subscriber loop reports a missing client and does not hide bugs.
    Popen is faked: nothing runs and nothing is published."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = load_module()

    def test_unknown_plant_sorts_after_every_listed_one(self) -> None:
        ranks = [self.m.plant_rank(p) for p in (*self.m.PLANT_ORDER, "Nowhere")]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(ranks[-1], len(self.m.PLANT_ORDER))

    def bus(self):
        from unittest import mock
        with mock.patch.object(self.m, "_which", lambda name: f"/bin/{name}"):
            bus = self.m.Bus("broker.invalid")
        events = []
        bus.emit = lambda e: (events.append(e), bus._stop.set())
        return bus, events

    def test_a_client_that_cannot_start_is_a_disconnected_event(self) -> None:
        from unittest import mock
        bus, events = self.bus()
        with mock.patch.object(self.m.subprocess, "Popen", side_effect=FileNotFoundError("mosquitto_sub")):
            bus.loop_sub()
        self.assertEqual(events, [{"type": "mqtt", "connected": False, "error": "mosquitto_sub"}])
        self.assertFalse(bus.connected)

    def test_a_bug_reading_a_line_is_not_hidden(self) -> None:
        from unittest import mock
        bus, events = self.bus()
        bus.emit = events.append
        proc = mock.Mock(stdout=iter(["track/sensor/1 ACTIVE\n"]))
        with mock.patch.object(self.m.subprocess, "Popen", return_value=proc), \
                mock.patch.object(bus, "_on_line", side_effect=KeyError("addr")):
            with self.assertRaises(KeyError):
                bus.loop_sub()

if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

SCRIPTS = Path(__file__).resolve().parents[1]


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "lcos_mqtt_mimic", SCRIPTS / "lcos_mqtt_mimic.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LcosMimicNamingTest(unittest.TestCase):
    m: ClassVar[ModuleType]
    layout: ClassVar[dict[str, Any]]

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


class LcosMimicNameMapTest(unittest.TestCase):
    """load_cps reads staging's rows of the device master (hartlib.devices.load), cp per user name."""

    m: ClassVar[ModuleType]

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



class PlantOrder(unittest.TestCase):
    """plant_rank orders unknown plants last."""

    m: ClassVar[ModuleType]

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = load_module()

    def test_unknown_plant_sorts_after_every_listed_one(self) -> None:
        ranks = [self.m.plant_rank(p) for p in (*self.m.PLANT_ORDER, "Nowhere")]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(ranks[-1], len(self.m.PLANT_ORDER))


class Errors(unittest.TestCase):
    """What stops the mimic is a MimicError, a BusError or a DevicesError; main ends on its message. The broker probe is
    faked: no connection is made."""

    m: ClassVar[ModuleType]

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = load_module()

    def test_the_first_host_that_answers_is_the_broker(self) -> None:
        from unittest import mock
        with mock.patch.object(self.m, "probe", side_effect=lambda h, port: h == "127.0.0.1"), \
                mock.patch.object(self.m, "mqtt_broker", return_value="broker.invalid"):
            self.assertEqual(self.m.pick_mqtt_host("other.invalid", 1883), "127.0.0.1")

    def test_no_broker_is_a_mimic_error_naming_each_host_tried(self) -> None:
        from unittest import mock
        with mock.patch.object(self.m, "probe", return_value=False), \
                mock.patch.object(self.m, "mqtt_broker", return_value="broker.invalid"), \
                mock.patch.object(self.m, "host_default", return_value="broker.invalid"), \
                self.assertRaisesRegex(self.m.MimicError, "No MQTT broker on port 1884. Tried: a.invalid, "
                                       "broker.invalid, 127.0.0.1"):
            self.m.pick_mqtt_host("a.invalid", 1884)

    def test_a_missing_tables_file_is_a_mimic_error(self) -> None:
        from unittest import mock
        with mock.patch.object(self.m, "TABLES", Path("/nonexistent/tables.xml")), \
                self.assertRaisesRegex(self.m.MimicError, "missing /nonexistent/tables.xml"):
            self.m.load_layout()

    def test_main_ends_on_a_mimic_or_bus_error_s_message(self) -> None:
        import sys
        from unittest import mock
        for err in (self.m.MimicError("No MQTT broker on port 1883."), self.m.BusError("mosquitto_pub not found.")):
            with self.subTest(err=type(err).__name__), \
                    mock.patch.object(self.m, "pick_mqtt_host", return_value="127.0.0.1"), \
                    mock.patch.object(self.m, "load_layout", side_effect=err), \
                    mock.patch.object(sys, "argv", ["lcos_mqtt_mimic.py"]), self.assertRaises(SystemExit) as stop:
                self.m.main()
            self.assertEqual(stop.exception.code, str(err))
            self.assertIs(stop.exception.__cause__, err)


class StagingStepsTest(unittest.TestCase):
    """load_layout's staging steps on a small tables root and a fake device index (no files, no broker)."""

    class FakeIndex:
        def __init__(self, rows: dict[str, set[str]]) -> None:
            self.rows = rows

        def has(self, layer: str, name: str) -> bool:
            return name in self.rows.get(layer, set())

        def names(self, layer: str, roles: object = None) -> list[str]:
            return sorted(self.rows.get(layer, set()))

    ROOT_XML = """<layout-config><sensors>
      <sensor><systemName>M2S100</systemName><userName>FB 7 N</userName></sensor>
      <sensor><systemName>M2S101</systemName><userName>FB 7 R</userName></sensor>
      <sensor><systemName>IS9</systemName><userName>Internal</userName></sensor>
    </sensors><turnouts>
      <turnout feedback="twosensor" sensor1="FB 7 R" sensor2="FB 7 N"><systemName>M2T7</systemName>
        <userName>Switch 7</userName></turnout>
      <turnout feedback="direct"><systemName>M2T3</systemName><userName>Switch 3</userName></turnout>
      <turnout><systemName>M2T99</systemName><userName>Switch 99</userName></turnout>
    </turnouts></layout-config>"""

    def setUp(self) -> None:
        import xml.etree.ElementTree as ET

        self.m = load_module()
        self.root = ET.fromstring(self.ROOT_XML)

    def test_sensors_are_the_m2s_ones_by_address(self) -> None:
        sensors = self.m._staging_sensors(self.root)
        self.assertEqual(sorted(sensors), ["100", "101"])
        self.assertEqual((sensors["100"].user_name, sensors["100"].system_name), ("FB 7 N", "M2S100"))

    def test_a_twosensor_turnout_carries_its_feedback_addresses(self) -> None:
        import contextlib
        import io

        index = self.FakeIndex({"turnout": {"Switch 7", "Switch 3"}})
        by_user = {"FB 7 N": "100", "FB 7 R": "101"}
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            got = self.m._staging_turnouts(self.root, index, by_user, {"turnout": {"Switch 7": "Plane"}})
        self.assertEqual([t["num"] for t in got], [7, 3])     # Plane sorts before Other
        seven, three = got
        self.assertEqual((seven["feedback"], seven["n_addr"], seven["r_addr"], seven["plant"]),
                         ("TWOSENSOR", "100", "101", "Plane"))
        self.assertEqual((three["n_addr"], three["r_addr"]), (None, None))
        self.assertIn("M2T99 (Switch 99)", err.getvalue())     # no device-master row: named and left out


if __name__ == "__main__":
    unittest.main()

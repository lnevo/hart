"""hartlib.jmri_bean: a level-less device's beans as its jmri_bean JSON, written and read back, and every shape the
reader refuses."""
from __future__ import annotations

import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import devices as D, jmri_bean as jb, tables  # noqa: E402
from hartlib.tables_sections import BLOCKS, MQTT_SENSORS, TablesBuildError  # noqa: E402


def row(**cells: str) -> dict[str, str]:
    out = {c: "" for c in D.COLUMNS}
    out.update({"layer": "sensor", "user_name": "Test sensor", "jmri_comment": "on the bench", **cells})
    return out


SENSOR = ET.fromstring('<sensor inverted="false"><systemName>M2S999</systemName><userName>Test sensor</userName>'
                       "<comment>on the bench</comment></sensor>")


class RoundTrip(unittest.TestCase):
    def test_the_beans_come_back_with_their_cells(self) -> None:
        r = row()
        r["jmri_bean"] = jb.bean_json([(MQTT_SENSORS, SENSOR)], r)
        self.assertIn('{"tag":"userName","column":"user_name"}', r["jmri_bean"])
        renamed = dict(r, user_name="Bench sensor")                     # a rename is one cell
        (sec, el), = jb.row_beans(renamed)
        self.assertEqual(MQTT_SENSORS, sec)
        self.assertEqual(("M2S999", "Bench sensor"), (tables.system_name(el), tables.user_name(el)))

    def test_kept_beans_put_a_names_only_block_apart(self) -> None:
        names_only = ET.fromstring("<block><systemName>IB9</systemName><userName>Test block</userName></block>")
        r = row(layer="block", user_name="Test block")
        r["jmri_bean"] = jb.bean_json([(BLOCKS, names_only)], r)
        self.assertEqual([("blocks-names",) + BLOCKS], list(jb.kept_beans([r, row()])))


class Refused(unittest.TestCase):
    def test_each_bad_shape_names_the_row(self) -> None:
        good = {"section": list(MQTT_SENSORS), "element": {"tag": "sensor", "attrs": {},
                                                           "children": [{"tag": "systemName", "text": "M2S9"}]}}
        for text, why in (("{", "not JSON"),
                          ('{"beans": []}', "at least one bean"),
                          (json.dumps({"beans": [dict(good, section=["memories", None])]}), "not one a device master"),
                          (json.dumps({"beans": [dict(good, element={"attrs": {}})]}), "has no tag"),
                          (json.dumps({"beans": [dict(good, element={"tag": "sensor", "column": "dcc"})]}),
                           "names column 'dcc'"),
                          (json.dumps({"beans": [dict(good, element={"tag": "sensor", "attrs": {"a": 1}})]}),
                           "attrs in jmri_bean are not text"),
                          (json.dumps({"beans": [dict(good, element={"tag": "sensor"})]}), "has no system name")):
            with self.subTest(why=why), self.assertRaisesRegex(TablesBuildError, f"sensor 'Test sensor': .*{why}"):
                jb.row_beans(row(jmri_bean=text))

    def test_kept_beans_report_every_bad_row_at_once(self) -> None:
        bad = [row(user_name="A", jmri_bean="{"), row(user_name="B", jmri_bean='{"beans": []}')]
        with self.assertRaisesRegex(TablesBuildError, r"^the device master: sensor 'A': .*; sensor 'B': "):
            jb.kept_beans(bad)


if __name__ == "__main__":
    unittest.main()

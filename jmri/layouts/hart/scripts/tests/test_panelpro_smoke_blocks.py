"""The PanelPro smoke test's main and upper block check (panelpro_smoke_test.py, Jython inside JMRI): a block on a
field sensor (a detector swapped in by its device row, ADR-028) passes when it is the one the tables bind
(HART_FIELD_DETECTED, from hartlib.level_devices.field_detected); a block with no sensor, or on any other, fails.

The script cannot load outside JMRI, so its plain functions are taken from the source and run here.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPT = ROOT / "jmri/layouts/hart/scripts/panelpro_smoke_test.py"
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import level_devices  # noqa: E402

PLAIN = ("LEVEL_BLOCK_PREFIX", "LEVEL_SENSOR_PREFIX", "field_detected", "block_sensor_errors", "level_sensors",
         "level_block_errors")


def plain_parts(names: tuple[str, ...] = PLAIN, ns: dict | None = None) -> dict:
    """The script's named constants, plain functions and classes, run in a namespace of their own (`ns`, which may
    hold what they use: Jython's builtins or the script's other globals)."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    keep = [n for n in tree.body
            if (isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names)
            or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in names)]
    ns = {"os": os, **(ns or {})}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(SCRIPT), "exec"), ns)
    missing = [name for name in names if name not in ns]
    if missing:
        raise AssertionError(f"{SCRIPT.name} has no {missing}")
    return ns


class SmokeBlocks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = plain_parts()

    def check(self, blocks, field=None):
        return self.ns["block_sensor_errors"](blocks, field or {})

    def test_the_prefixes_are_hartlibs(self):
        self.assertEqual(self.ns["LEVEL_BLOCK_PREFIX"], level_devices.BLOCK_PREFIX)
        self.assertEqual(self.ns["LEVEL_SENSOR_PREFIX"], level_devices.SENSOR_PREFIX)

    def test_virtual_sensors_pass(self):
        self.assertEqual(self.check([("Track 107 Loop 1", "IB:C3:0041", "IS:HART:C3:B:107_Loop_1")]), [])

    def test_a_swapped_detector_passes_on_its_field_sensor(self):
        field = self.ns["field_detected"]("IB:C3:0041 M2S3305;")
        self.assertEqual(field, {"IB:C3:0041": "M2S3305"})
        self.assertEqual(self.check([("Track 107 Loop 1", "IB:C3:0041", "M2S3305"),
                                     ("Track 107-109", "IB:C3:0042", "IS:HART:C3:B:107-109")], field), [])

    def test_a_block_with_no_sensor_fails(self):
        field = {"IB:C3:0041": "M2S3305"}
        for f in ({}, field):
            self.assertEqual(self.check([("Track 107 Loop 1", "IB:C3:0041", None)], f),
                             ["main and upper blocks with no occupancy sensor: Track 107 Loop 1"])

    def test_a_field_sensor_the_tables_do_not_bind_fails(self):
        self.assertEqual(self.check([("Track 107 Loop 1", "IB:C3:0041", "M2S3305")]),
                         ["main and upper blocks with no virtual occupancy sensor: Track 107 Loop 1"])
        self.assertEqual(self.check([("Track 107 Loop 1", "IB:C3:0041", "IS:HART:C3:B:107_Loop_1")],
                                    {"IB:C3:0041": "M2S3305"}),
                         ["main and upper blocks not on their field sensor: Track 107 Loop 1 "
                          "(IS:HART:C3:B:107_Loop_1, not M2S3305)"])

    def test_the_variable_is_read_strictly(self):
        self.assertEqual(self.ns["field_detected"](""), {})
        self.assertEqual(self.ns["field_detected"]("A B;C D;"), {"A": "B", "C": "D"})
        with self.assertRaisesRegex(ValueError, "is not <block> <sensor>"):
            self.ns["field_detected"]("A;")


class _Bean:
    def __init__(self, system, user=None, sensor=None):
        self.system, self.user, self.sensor = system, user, sensor

    def getSystemName(self):
        return self.system

    def getDisplayName(self):
        return self.user or self.system

    def getSensor(self):
        return self.sensor


class _Manager:
    def __init__(self, beans):
        self.beans = beans

    def getNamedBeanSet(self):
        return self.beans


class LevelBlockErrors(unittest.TestCase):
    """level_block_errors over the managers, HART_FIELD_DETECTED read from the environment."""

    def run_check(self, env):
        ns = plain_parts()
        virtual = _Bean("IS:HART:C3:B:107-109")
        field = _Bean("M2S3305")
        blocks = _Manager([_Bean("IB:C3:0041", "Track 107 Loop 1", field),
                           _Bean("IB:C3:0042", "Track 107-109", virtual)])
        with unittest.mock.patch.dict(os.environ, env, clear=False):
            return ns["level_block_errors"](blocks, _Manager([virtual, field]))

    def test_the_swapped_block_passes(self):
        self.assertEqual(self.run_check({"HART_FIELD_DETECTED": "IB:C3:0041 M2S3305;"}), [])

    def test_a_bad_variable_is_a_failure_line_not_a_traceback(self):
        self.assertEqual(self.run_check({"HART_FIELD_DETECTED": "IB:C3:0041;"}),
                         ["HART_FIELD_DETECTED: 'IB:C3:0041' is not <block> <sensor>"])


class WrapperPassesIt(unittest.TestCase):
    def test_the_wrapper_exports_the_field_detected_blocks_of_the_tables_it_loads(self):
        text = (SCRIPT.parent / "run_panelpro_smoke_test.sh").read_text(encoding="utf-8")
        self.assertIn("python3 -m hartlib.level_devices field-detected", text)
        self.assertIn('"$PP_TABLES_FILE"', text)
        # the file pp_begin has PanelPro load, in place
        session = (ROOT / "tools/hosts/panelpro_session.sh").read_text(encoding="utf-8")
        self.assertIn('TABLES_URI="$PP_TABLES_FILE"', session)
        self.assertIn('TABLES_URI="home:${PP_TABLES_FILE#"$HOME"/}"', session)
        self.assertIn('load-tables --profile "$PROFILE_XML" --tables "$TABLES_URI"', session)
        self.assertIn("export HART_FIELD_DETECTED", text)


if __name__ == "__main__":
    unittest.main()

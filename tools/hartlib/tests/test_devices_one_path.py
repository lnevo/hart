"""The device master is reached through hartlib.devices only (T6a step 0), so splitting it in two changes one module.

The scan of the repo for code outside hartlib that names or opens the devices files is a static check,
tools/audit/check_devices_one_path.py (check.sh job devices-one-path). Here: the one file that check allows to name
them (tools/schematic/panel_stamps.py, which cannot import hartlib in its shell test) holds hartlib's names, and the
path helpers place the files under a folder.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools/hartlib/src"))
from hartlib import devices  # noqa: E402

ALLOWED = "tools/schematic/panel_stamps.py"      # check_devices_one_path.ALLOWED


class OnePathTest(unittest.TestCase):
    def test_the_allowed_copy_is_hartlibs_name(self):
        spec = importlib.util.spec_from_file_location("panel_stamps", REPO / ALLOWED)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["panel_stamps"] = mod         # dataclasses look their module up here
        spec.loader.exec_module(mod)
        self.assertEqual(mod.DEVICES_FILE, devices.MASTER_FILE)
        self.assertEqual(mod.DEVICES_FIELD_FILE, devices.FIELD_FILE)
        self.assertEqual(devices.MASTER_FILE, devices.GENERATED_FILE)

    def test_master_path_under_a_folder(self):
        self.assertEqual(devices.master_path(Path("/x")), Path("/x") / devices.MASTER_FILE)
        self.assertEqual(devices.master_path(), devices.MASTER)
        self.assertEqual(devices.field_path(Path("/x")), Path("/x") / devices.FIELD_FILE)
        self.assertEqual(devices.Files.under(Path("/x")).field, Path("/x") / devices.FIELD_FILE)


if __name__ == "__main__":
    unittest.main()

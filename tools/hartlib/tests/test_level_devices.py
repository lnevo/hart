"""hartlib.level_devices: the main and upper virtual names come from each device's own name alone."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import level_devices as D, tables  # noqa: E402


class NamesTest(unittest.TestCase):
    def test_block_sensors(self):
        self.assertEqual([D.block_sensor(b) for b in ("Track 107-109", "Track 107 Loop 2", "OS Switch 225b",
                                                      "Track 135-H1", "Track 101 Spur 1")],
                         ["IS:HART:C3:B:107-109", "IS:HART:C3:B:107_Loop_2", "IS:HART:C3:B:OS225b",
                          "IS:HART:C3:B:135-H1", "IS:HART:C3:B:101_Spur_1"])
        self.assertEqual([D.occupancy_user(b) for b in ("Track 107 Loop 2", "OS Switch 225b")],
                         ["BS 107 Loop 2", "BS Switch 225b"])
        for bad in ("Track 1/2", "Track ", "Yard"):
            with self.subTest(block=bad), self.assertRaises(ValueError):
                D.block_sensor(bad)
        self.assertTrue(D.is_block_sensor("IS:HART:C3:B:OS101"))
        self.assertFalse(D.is_block_sensor("IS:SML_MODE"))

    def test_heads_and_clear_actions(self):
        self.assertEqual(D.head_name("Head 108R Top"), "IH:HART:C3:108R_Top")
        self.assertEqual(D.clear_action("IS:HART:C3:B:OS101"), "IQDA$HART:C3:B:OS101")
        with self.assertRaises(ValueError):
            D.clear_action("IS:SML_MODE")

    def test_clear_sensors_of_the_released_tables(self):
        root = tables.read()
        got = D.clear_sensors(root)
        self.assertEqual(sorted(got), sorted(tables.system_name(s) for s in tables.sensors(root)
                                             if D.is_block_sensor(tables.system_name(s))))
        self.assertTrue(got)


if __name__ == "__main__":
    unittest.main()

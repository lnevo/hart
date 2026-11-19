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

    def test_the_naming_rule_holds_every_main_and_upper_name_and_no_other(self):
        """is_level_name: every name of a main or upper device in the released tables follows it (system and user
        names; a layout block by its user name, the block's, since JMRI may number one added in PanelPro anywhere; the
        sensors-clear LogixNG by its system names), and no other device's name does, staging's four-digit masts 2035
        and 2036 included."""
        root = tables.read()
        level = {"IT:HART:C3:", "IS:HART:C3:B:", "IH:HART:C3:", "IB:C3:", "IQ$HART:C3:", "IQC$HART:C3:",
                 "IQDA$HART:C3:"}
        beans = [el for sec in tables.elements(root) if sec.tag != "LayoutEditor" for el in tables.elements(sec)
                 if tables.system_name(el)]
        mine = [el for el in beans if tables.system_name(el).startswith(tuple(level)) or
                "(IH:HART:C3:" in tables.system_name(el)]
        users = {tables.user_name(el) for el in mine} - {""}
        lbs = [lb for lb in tables.layout_blocks(root) if tables.user_name(lb) in users]
        self.assertEqual(len(lbs), 125)
        names = {tables.system_name(el) for el in mine} | (users - {D.CLEAR_USER}) | {tables.user_name(lb) for lb in lbs}
        self.assertEqual(sorted(n for n in names if not D.is_level_name(n)), [])
        others = [el for el in beans if el not in mine and el not in lbs]
        self.assertGreater(len(others), 300)
        self.assertEqual([n for el in others for n in (tables.system_name(el), tables.user_name(el))
                          if D.is_level_name(n)], [])
        self.assertFalse(D.is_level_name("Mast 2035") or D.is_level_name("Switch 39") or D.is_level_name(""))
        self.assertTrue(D.is_level_name("Mast 140RA") and D.is_level_name("IB:C3:0999"))   # gone, by rule

    def test_clear_sensors_of_the_released_tables(self):
        root = tables.read()
        got = D.clear_sensors(root)
        self.assertEqual(sorted(got), sorted(tables.system_name(s) for s in tables.sensors(root)
                                             if D.is_block_sensor(tables.system_name(s))))
        self.assertTrue(got)


if __name__ == "__main__":
    unittest.main()

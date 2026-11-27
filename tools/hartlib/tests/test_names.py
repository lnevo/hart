"""hartlib.names: devices.csv's dcc column goes back into the JMRI comment where it was."""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "src"))

from hartlib import devices, names, paths, tables  # noqa: E402


class CommentTest(unittest.TestCase):
    def test_dcc_is_the_second_group(self):
        self.assertEqual(names.jmri_comment("Node: 4 Turnout: 0 | OU: 1 Ports: 1,2", "100"),
                         "Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2")
        self.assertEqual(names.jmri_comment("Node: 4 Turnout: 0", "100"), "Node: 4 Turnout: 0 | DCC: 100")
        self.assertEqual(names.jmri_comment("Node: 4 Turnout: 0 | OU: 1 Ports: 1,2", ""),
                         "Node: 4 Turnout: 0 | OU: 1 Ports: 1,2")

    def test_split_takes_the_group_out(self):
        self.assertEqual(names.split_dcc("Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2"),
                         ("Node: 4 Turnout: 0 | OU: 1 Ports: 1,2", "100"))
        self.assertEqual(names.split_dcc("Node: 4 Turnout: 0 | DCC: 100"), ("Node: 4 Turnout: 0", "100"))
        self.assertEqual(names.split_dcc("Brick | Switch 1"), ("Brick | Switch 1", ""))

    def test_a_dcc_group_it_cannot_put_back_is_refused(self):
        for odd in ("DCC: 100 | Node: 4", "Node: 4 | OU: 1 | DCC: 100", "Node: 4 |DCC: 100| OU: 1",
                    "Node: 4 | DCC 100", "Node: 4 | DCC: 100 | DCC: 101"):
            with self.subTest(comment=odd), self.assertRaises(ValueError):
                names.split_dcc(odd)

    def test_every_field_turnouts_comment_round_trips_exactly(self):
        for row in devices.load():
            if row.role != "turnout" or row.assignment != "field":
                continue
            jmri = devices.comment_of(row)
            with self.subTest(row=row.user_name):
                self.assertEqual(names.split_dcc(jmri), (row.wiring, row.dcc))
                self.assertEqual(names.jmri_comment(*names.split_dcc(jmri)), jmri)

    def test_wiring_carries_no_dcc_and_every_lcc_alias_has_its_address(self):
        """The dcc column is the one place of a DCC address: no wiring text has one, and every LCC alias row (DCC
        Switch N) fills dcc with the number its MTT system name carries."""
        rows = devices.load()
        for row in rows:
            with self.subTest(row=row.user_name):
                self.assertNotRegex(row.wiring, r"DCC:\s*\d")
                self.assertRegex(row.dcc, r"^(\d+)?$")
        aliases = [r for r in rows if r.role == "lcc_alias" and r.level == 1]
        self.assertEqual(len(aliases), 20)
        self.assertTrue(all(r.dcc and r.system_name == f"MTT{r.dcc}" for r in aliases))

    def test_every_mqtt_turnout_comment_in_tables_xml_comes_from_the_master(self):
        want = {row.system_name: devices.comment_of(row) for row in devices.load()
                if row.role == "turnout" and row.assignment == "field" and row.dcc}
        root = tables.read(paths.TABLES_XML)
        have = {tables.system_name(t): tables.text(t, "comment") for t in tables.turnouts(root)
                if re.search(r"DCC:\s*\d", tables.text(t, "comment"))}
        self.assertEqual(have, want)

if __name__ == "__main__":
    unittest.main()

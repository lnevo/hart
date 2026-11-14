"""hartlib.names: the map's dcc column goes back into the JMRI comment where it was."""
import csv
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "src"))

from hartlib import names, paths, tables  # noqa: E402


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

    def test_map_comments_carry_no_dcc(self):
        with paths.PUBLIC_NAME_MAP.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertIn("dcc", rows[0])
        for row in rows:
            with self.subTest(row=row["current"]):
                self.assertNotRegex(row["comment"], r"DCC:\s*\d")
                self.assertRegex(row["dcc"], r"^(\d+)?$")

    def test_every_mqtt_turnout_comment_in_tables_xml_comes_from_the_map(self):
        with paths.PUBLIC_NAME_MAP.open(newline="", encoding="utf-8") as fh:
            want = {row["hardware"]: names.row_comment(row) for row in csv.DictReader(fh)
                    if row["layer"] == "turnout" and row["current"] == row["proposed"] and row["dcc"]}
        root = tables.read(paths.TABLES_XML)
        have = {tables.system_name(t): tables.text(t, "comment") for t in tables.turnouts(root)
                if re.search(r"DCC:\s*\d", tables.text(t, "comment"))}
        self.assertEqual(have, want)


if __name__ == "__main__":
    unittest.main()

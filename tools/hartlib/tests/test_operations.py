"""hartlib.operations: the sections of an Operations Pro roster file."""
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "src"))

from hartlib import operations  # noqa: E402

HEADER = ('<?xml version="1.0" encoding="UTF-8"?>\n'
          '<?xml-stylesheet href="/xml/XSLT/operations-cars.xsl" type="text/xsl"?>\n'
          '<!DOCTYPE operations-config SYSTEM "/xml/DTD/operations-cars.dtd">\n')


class SectionsTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def write(self, body: str) -> Path:
        path = self.dir / "roster.xml"
        path.write_text(HEADER + body, encoding="utf-8")
        return path

    def test_cars_in_file_order_and_only_in_their_section(self):
        path = self.write('<operations-config><cars><car id="B1" roadName="B"/><car id="A2"/></cars>'
                          '<other><car id="stray"/></other></operations-config>')
        self.assertEqual(operations.ids(operations.cars(path)), ["B1", "A2"])
        self.assertEqual(operations.cars(path)[0].get("roadName"), "B")

    def test_engines_and_trains(self):
        path = self.write('<operations-config><engines><engine id="E1"/></engines>'
                          '<trains><train id="T1" name="local"/></trains></operations-config>')
        self.assertEqual(operations.ids(operations.engines(path)), ["E1"])
        self.assertEqual([t.get("name") for t in operations.trains(path)], ["local"])
        self.assertEqual(operations.cars(path), [])

    def test_an_unknown_section_is_refused(self):
        with self.assertRaises(ValueError):
            operations.section(self.write("<operations-config/>"), "wagons")

    def test_a_broken_file_names_itself(self):
        path = self.write("<operations-config><cars>")
        with self.assertRaisesRegex(ET.ParseError, "roster.xml"):
            operations.cars(path)

    def test_a_missing_file_is_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            operations.cars(self.dir / "none.xml")


class RepoFilesTest(unittest.TestCase):
    def test_the_repo_rosters_read(self):
        for name, path in operations.ROSTERS.items():
            if name in ("cars", "engines", "trains"):
                found = operations.section(path, name)
                self.assertEqual(len(found), len(list(operations.root(path).iter(operations.SECTIONS[name]))), path)
                self.assertTrue(found, path)


if __name__ == "__main__":
    unittest.main()

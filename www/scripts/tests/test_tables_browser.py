"""build_tables_browser.py: the browser rows from a small tables file, and a file that cannot be read is a named
error that keeps its cause."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_tables_browser as btb  # noqa: E402

SMALL = b"""<?xml version='1.0' encoding='UTF-8'?>
<layout-config>
  <sensors><sensor><systemName>M2S1</systemName><userName>OS 1</userName><comment>east</comment></sensor></sensors>
  <sensors><sensor><systemName>IS9</systemName></sensor></sensors>
  <blocks><block systemName="IB1"><systemName>IB1</systemName><userName>B1</userName></block></blocks>
  <blocks><block systemName="IB1" length="100"><systemName>IB1</systemName><userName>B1</userName>
    <!-- a comment JMRI may keep --><occupancysensor>M2S1</occupancysensor><path /><path /></block></blocks>
  <signalmastlogics><signalmastlogic><sourceSignalMast>A</sourceSignalMast>
    <destinationMast><destinationSignalMast>B</destinationSignalMast><enabled>yes</enabled></destinationMast>
    <destinationMast><destinationSignalMast>C</destinationSignalMast><enabled>no</enabled></destinationMast>
  </signalmastlogic></signalmastlogics>
</layout-config>"""


def rows(data: dict, tid: str) -> list:
    return next(t["rows"] for t in data["tables"] if t["id"] == tid)


class Build(unittest.TestCase):
    def setUp(self) -> None:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def small(self) -> dict:
        p = self.dir / "tables.xml"
        p.write_bytes(SMALL)
        return btb.build(btb.load(p)[1])

    def test_rows_from_every_manager_and_the_full_block_pass(self) -> None:
        data = self.small()
        self.assertEqual(rows(data, "sensors"), [["M2S1", "OS 1", "MQTT", "east"], ["IS9", "", "Internal", ""]])
        self.assertEqual(rows(data, "blocks"), [["IB1", "B1", "100", "M2S1", 2, ""]])
        self.assertEqual(rows(data, "sml"), [["A", "B", "yes", ""], ["A", "C", "no", ""]])
        self.assertEqual((data["meta"]["smlSources"], data["meta"]["smlDestinations"]), (1, 2))
        self.assertEqual(list(data["meta"])[:3], ["sensors", "turnouts", "memories"])

    def test_a_small_file_fails_the_checks_it_should(self) -> None:
        self.assertIn("table 'turnouts' has no rows", btb.problems(self.small()))

    def test_a_file_that_is_not_xml_is_a_named_error(self) -> None:
        p = self.dir / "tables.xml"
        p.write_bytes(b"<layout-config><sensors>")
        with self.assertRaisesRegex(btb.BrowserDataError, "is not XML") as cm:
            btb.load(p)
        self.assertIsNotNone(cm.exception.__cause__)

    def test_a_missing_file_is_a_named_error(self) -> None:
        with self.assertRaisesRegex(btb.BrowserDataError, "cannot read the tables file") as cm:
            btb.load(self.dir / "none.xml")
        self.assertIsInstance(cm.exception.__cause__, OSError)


if __name__ == "__main__":
    unittest.main()

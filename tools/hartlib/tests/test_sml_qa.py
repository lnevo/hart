"""hartlib.sml_qa: the native SML QA's steps file, read in run order, and the staging devices it drives, by device ID
from the device master; each bad shape stops with a QAError naming the file and line or the device."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src")]
from hartlib import sml_qa  # noqa: E402
from hartlib.device_rows import MasterRow  # noqa: E402
from hartlib.sml_qa import QAError  # noqa: E402

HEADER = ",".join(sml_qa.COLUMNS) + "\n"
GOOD = HEADER + (
    "qa01_second,1,about,,,,,,Second.\n"
    "qa01_second,2,after,det:os:1,INACTIVE,,,,\n"
    "qa01_second,3,expect,,,,Mast 2L,stop,\n"
    "qa00_first,2,before,det:os:1,ACTIVE,,,,\n"
    "qa00_first,1,about,,,,,,First.\n"
    "qa00_first,3,before,switch:1,THROWN,,,,\n"
    "qa00_first,4,expect,,,,Mast 2L,Diverging Clear,a note\n"
    "qa00_first,5,expect,,,,Mast 2R,nonstop,\n"
)


def rows(fb: tuple[str, ...] = ("N", "R")) -> list[MasterRow]:
    out = [MasterRow(1, "turnout", "Switch 1", "turnout", system_name="M2T408", id="switch:1"),
           MasterRow(1, "turnout", "Switch 7", "turnout", system_name="M2T1308", id="switch:7"),
           MasterRow(1, "turnout", "DCC Switch 1", "lcc_alias", id="dcc:1"),
           MasterRow(1, "occupancy", "BS Switch 1", "os", system_name="M2S401", id="det:os:1"),
           MasterRow(1, "occupancy", "BS Spare", "spare", system_name="MTS1", id="det:spare"),
           MasterRow(2, "turnout", "Switch 101", "turnout", system_name="IT:HART:101", id="switch:101")]
    out += [MasterRow(1, "fb", f"FB Switch 1 {end}", "fb", system_name=f"M2S47{i}", id=f"fb:1:{end}")
            for i, end in enumerate(("N", "R")) if end in fb]
    return out


class Read(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "native_sml_qa.csv"

    def tearDown(self) -> None:
        self.dir.cleanup()

    def read(self, text: str) -> tuple[sml_qa.Step, ...]:
        self.path.write_text(text, encoding="utf-8")
        return sml_qa.read(self.path)

    def fails(self, text: str, pattern: str) -> None:
        self.path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(QAError, pattern):
            sml_qa.read(self.path)

    def test_steps_in_tag_order_and_rows_in_n_order(self) -> None:
        first, second = self.read(GOOD)
        self.assertEqual(first, sml_qa.Step(
            "qa00_first", "First.", (("Mast 2L", "Diverging Clear"), ("Mast 2R", "nonstop")),
            (sml_qa.Change("det:os:1", "ACTIVE", 5), sml_qa.Change("switch:1", "THROWN", 7)), ()))
        self.assertEqual(second.tag, "qa01_second")
        self.assertEqual(second.after, (sml_qa.Change("det:os:1", "INACTIVE", 3),))

    def test_the_repo_file_reads(self) -> None:
        steps = sml_qa.read()
        self.assertEqual(steps[0].tag, "qa00_rest")
        self.assertEqual([s.tag for s in steps], sorted(s.tag for s in steps))

    def test_missing_file(self) -> None:
        with self.assertRaisesRegex(QAError, "cannot read it"):
            sml_qa.read(self.path)

    def test_missing_column(self) -> None:
        self.fails("tag,n,part,device,state,mast,want,text\n", "no column feedback")

    def test_bad_cells(self) -> None:
        cases = [
            ("qa0_x,1,about,,,,,,d\n", "tag 'qa0_x' is not qaNN_words"),
            ("qa00_x,0,about,,,,,,d\n", "n '0' is not a whole number from 1"),
            ("qa00_x,1,story,,,,,,d\n", "part 'story' is not one of"),
            ("qa00_x,1,before,switch:1,,,,,\n", "a before row needs state"),
            ("qa00_x,1,expect,,,,Mast 2L,,\n", "an? expect row needs want"),
            ("qa00_x,1,about,switch:1,,,,,d\n", "an? about row has no device"),
            ("qa00_x,1,before,switch:1,OPEN,,,,\n", "state 'OPEN' is not one of"),
            ("qa00_x,1,before,det:os:1,ACTIVE,none,,,\n", "feedback 'none': only none, on a turnout state"),
            ("qa00_x,1,before,switch:1,CLOSED,skip,,,\n", "feedback 'skip'"),
        ]
        for body, pattern in cases:
            with self.subTest(body=body):
                self.fails(HEADER + body, pattern)

    def test_shape_of_the_steps(self) -> None:
        about = "qa00_x,1,about,,,,,,d\n"
        self.fails(HEADER + about + "qa00_x,1,expect,,,,Mast 2L,stop,\n", r"qa00_x n 1 is given twice")
        self.fails(HEADER + about + "qa00_y,1,about,,,,,,d\n", "qa00_y has the number of qa00_x")
        self.fails(HEADER + "qa00_x,1,expect,,,,Mast 2L,stop,\n", "qa00_x has 0 about rows, not one")
        self.fails(HEADER + about + "qa00_x,2,about,,,,,,e\n", "qa00_x has 2 about rows, not one")
        self.fails(HEADER + about + "qa00_x,2,expect,,,,Mast 2L,stop,\nqa00_x,3,expect,,,,Mast 2L,nonstop,\n",
                   r":4: qa00_x expects Mast 2L twice")


class Drives(unittest.TestCase):
    def steps(self, *changes: tuple[str, str, bool]) -> tuple[sml_qa.Step, ...]:
        return (sml_qa.Step("qa00_x", "d", (), tuple(sml_qa.Change(d, s, n, skip) for n, (d, s, skip)
                                                     in enumerate(changes, 2)), ()),)

    def test_turnouts_take_their_feedback_and_occupancy_its_address(self) -> None:
        got = sml_qa.drives(self.steps(("switch:1", "THROWN", False), ("det:os:1", "ACTIVE", False),
                                       ("switch:7", "CLOSED", False), ("switch:1", "CLOSED", False)), rows())
        self.assertEqual(list(got), ["switch:1", "det:os:1", "switch:7"])
        self.assertEqual(got["switch:1"], sml_qa.Drive("switch:1", "Switch 1", "turnout", "408", ("470", "471")))
        self.assertEqual(got["switch:7"].feedback, None)              # no fb rows: driven without feedback
        self.assertEqual(got["det:os:1"], sml_qa.Drive("det:os:1", "BS Switch 1", "occupancy", "401", None))

    def test_unknown_or_other_level_id(self) -> None:
        for ident in ("switch:99", "switch:101"):
            with self.subTest(ident=ident), self.assertRaisesRegex(QAError, f"{ident} is no staging device ID"):
                sml_qa.drives(self.steps((ident, "CLOSED", False)), rows())

    def test_a_state_its_row_does_not_take(self) -> None:
        with self.assertRaisesRegex(QAError, r"ACTIVE drives a occupancy row; Switch 1 \(switch:1\) is a turnout"):
            sml_qa.drives(self.steps(("switch:1", "ACTIVE", False)), rows())
        with self.assertRaisesRegex(QAError, "role lcc_alias"):
            sml_qa.drives(self.steps(("dcc:1", "CLOSED", False)), rows())

    def test_a_system_name_that_is_not_lcos_mqtt(self) -> None:
        with self.assertRaisesRegex(QAError, r"BS Spare \(det:spare\): system name 'MTS1' is not M2S<number>"):
            sml_qa.drives(self.steps(("det:spare", "ACTIVE", False)), rows())

    def test_one_feedback_row_of_two(self) -> None:
        with self.assertRaisesRegex(QAError, "has fb:1:N but not the other feedback sensor"):
            sml_qa.drives(self.steps(("switch:1", "CLOSED", False)), rows(fb=("N",)))

    def test_the_named_exception_drops_the_masters_feedback(self) -> None:
        got = sml_qa.drives(self.steps(("switch:1", "CLOSED", True), ("switch:1", "THROWN", True)), rows())
        self.assertIsNone(got["switch:1"].feedback)

    def test_the_exception_on_some_rows_only(self) -> None:
        with self.assertRaisesRegex(QAError, "feedback none on some of its rows only"):
            sml_qa.drives(self.steps(("switch:1", "CLOSED", True), ("switch:1", "THROWN", False)), rows())

    def test_the_exception_on_a_turnout_with_no_fb_rows(self) -> None:
        with self.assertRaisesRegex(QAError, "gives it no fb rows: drop the exception"):
            sml_qa.drives(self.steps(("switch:7", "CLOSED", True)), rows())


if __name__ == "__main__":
    unittest.main()

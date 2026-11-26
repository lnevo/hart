"""correct.py's error paths and its split steps: the table and roster readers, the profile error, the notes, and the
exit status. The proposal's logic is covered in test_speedmatch.py and test_speedmatch_review.py."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SM = Path(__file__).resolve().parents[1] / "speedmatch"
sys.path.insert(0, str(SM))
import correct  # noqa: E402

HEADER = "loco,direction,step,travel,blocks_per_reading,readings,readings_used,median_mm_s,rel_sd_pct,settled,reason\n"


def profile(rows):
    d = Path(tempfile.mkdtemp())
    p = d / "profile.csv"
    p.write_text(HEADER + "".join(f"{loco},{direction},{step},,1,5,5,{mm},1.0,True,settled\n"
                                  for loco, direction, step, mm in rows))
    return p


def roster(cvs):
    d = Path(tempfile.mkdtemp())
    p = d / "r.xml"
    body = "".join(f'<CVvalue name="{cv}" value="{v}"/>' for cv, v in cvs.items())
    p.write_text(f'<locomotive-config><locomotive id="L"><values>{body}</values></locomotive></locomotive-config>')
    return p


def run_main(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = correct.main(argv)
    return code, out.getvalue()


class Tables(unittest.TestCase):
    def test_parse_table(self):
        self.assertEqual(correct.parse_table("1,2,3"), [1, 2, 3])

    def test_a_table_entry_that_is_no_whole_number_stops(self):
        with self.assertRaisesRegex(correct.SpeedTableError, "give 28 whole numbers"):
            correct.parse_table("1,x,3")

    def test_a_short_table_stops(self):
        with self.assertRaisesRegex(correct.SpeedTableError, "28 entries, got 3"):
            correct.propose([1, 2, 3], {}, {})

    def test_roster_table_reads_cv67_to_cv94(self):
        p = roster({67 + i: i for i in range(28)} | {29: 6})
        self.assertEqual(correct.roster_table(p), list(range(28)))

    def test_a_roster_without_the_table_cvs_stops(self):
        p = roster({67 + i: i for i in range(27)})
        with self.assertRaisesRegex(correct.SpeedTableError, "no CV94 in the roster file"):
            correct.roster_table(p)

    def test_a_roster_without_a_locomotive_stops(self):
        d = Path(tempfile.mkdtemp())
        p = d / "r.xml"
        p.write_text("<locomotive-config/>")
        with self.assertRaisesRegex(correct.SpeedTableError, "no locomotive"):
            correct.roster_table(p)


class Main(unittest.TestCase):
    ARGS = ["--loco", "B", "--direction", "reverse", "--target-loco", "A", "--target-direction", "forward"]

    def test_no_profile_rows_stops_with_the_reason(self):
        p = profile([("A", "forward", 24, 100.0)])
        out = p.parent / "o"
        with self.assertRaises(SystemExit) as cm:
            correct.main(["--table", ",".join(["100"] * 28), "--profile", str(p), "--out", str(out)] + self.ARGS)
        self.assertEqual(str(cm.exception), "no profile rows for B reverse or for the target")
        self.assertFalse(out.exists())

    def test_a_bad_table_stops_with_the_reason(self):
        p = profile([("A", "forward", 24, 100.0), ("B", "reverse", 24, 100.0)])
        for bad, why in (("1,2", "28 entries, got 2"), ("1,,2", "whole numbers")):
            with self.assertRaises(SystemExit) as cm:
                correct.main(["--table", bad, "--profile", str(p), "--out", str(p.parent / "o")] + self.ARGS)
            self.assertIn(why, str(cm.exception))

    def test_no_table_is_a_usage_error(self):
        p = profile([("A", "forward", 24, 100.0)])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            correct.main(["--profile", str(p), "--out", str(p.parent / "o")] + self.ARGS)
        self.assertEqual(cm.exception.code, 2)

    def test_the_roster_table_feeds_the_proposal(self):
        steps = range(4, 127, 6)
        p = profile([("A", "forward", s, 2.0 * s) for s in steps] + [("B", "reverse", s, 1.0 * s) for s in steps])
        r = roster({67 + i: 100 for i in range(28)})
        out = p.parent / "o"
        code, text = run_main(["--roster-xml", str(r), "--profile", str(p), "--out", str(out)] + self.ARGS)
        self.assertEqual(code, correct.EXIT_CODES["continue"])
        prop = json.loads((out / "proposal.json").read_text())
        self.assertEqual(prop["old"], [100] * 28)
        self.assertEqual(prop["status"], "continue")
        self.assertTrue(prop["writes"])
        self.assertIn("status continue", text)

    def test_a_matched_loco_is_done_with_exit_0(self):
        steps = range(4, 127, 6)
        p = profile([("A", "forward", s, 1.0 * s) for s in steps] + [("B", "reverse", s, 1.0 * s) for s in steps])
        code, _ = run_main(["--table", ",".join(["100"] * 28), "--profile", str(p), "--out", str(p.parent / "o")]
                           + self.ARGS)
        self.assertEqual(code, 0)


class Steps(unittest.TestCase):
    def test_add_note_joins_with_a_semicolon(self):
        row, _ = correct._anchor(1, 10, 4.5, None, None, 0.03, 1.0, 1.5)
        correct._add_note(row, "x")
        self.assertEqual(row["note"], "no usable measurement (outside the measured steps or none); x")
        blank, _ = correct._anchor(1, 10, 4.5, 100.0, 100.0, 0.03, 1.0, 1.5)
        correct._add_note(blank, "x")
        self.assertEqual(blank["note"], "x")

    def test_anchor_raise_cut_and_keep(self):
        raised, v = correct._anchor(1, 10, 4.5, 50.0, 100.0, 0.03, 1.0, 1.5)
        self.assertEqual((raised["kind"], v), ("raise", 15))
        cut, v = correct._anchor(1, 10, 4.5, 200.0, 100.0, 0.03, 1.0, 1.5)
        self.assertEqual((cut["kind"], v), ("cut", 7))
        floor, v = correct._anchor(1, 1, 4.5, 200.0, 100.0, 0.03, 1.0, 1.5)
        self.assertEqual((floor["kind"], v, floor["note"]), ("cut", 1, "already at the floor"))
        kept, v = correct._anchor(1, 10, 4.5, 101.0, 100.0, 0.03, 1.0, 1.5)
        self.assertEqual((kept["kind"], v, kept["within"]), ("keep", 10, True))

    def test_start_low_raises_from_the_next_entry(self):
        rows = [correct._anchor(k, 1 if k == 1 else 100, s, 50.0, 100.0, 0.03, 1.0, 1.5)[0]
                for k, s in enumerate(correct.ANCHOR_STEPS, start=1)]
        raw = [2] + [150] * 27
        correct._start_low_raises(raw, rows)
        self.assertEqual(raw[0], 75)
        self.assertIn("started from the next entry's value", rows[0]["note"])

    def test_read_profile_answers_a_profile(self):
        p = profile([("A", "forward", 24, 100.0)])
        got = correct.read_profile(p, "A", "forward")
        self.assertIsInstance(got, correct.Profile)
        self.assertEqual(got.speeds, {24: 100.0})
        self.assertEqual(got.skipped, [])


if __name__ == "__main__":
    unittest.main()

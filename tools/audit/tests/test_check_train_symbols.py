"""check_train_symbols: crew jobs, Operations Pro trains and the CATS train list name trains of the master."""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/audit"))

import check_train_symbols as C  # noqa: E402

TRAINS = [
    {"train_symbol": "D749", "train_name": "D749", "engine": "1993", "font": "East", "opspro_name": ""},
    {"train_symbol": "D749R", "train_name": "D749 Return", "engine": "1993", "font": "West",
     "opspro_name": "D749 Return"},
]


def header(*records: str) -> ET.Element:
    return ET.fromstring("<DOC><TRAINSTORE><TRAINDATA>" + "".join(records) + "</TRAINDATA></TRAINSTORE></DOC>")


def rec(symbol: str, name: str, engine: str, font: str) -> str:
    return f'<DATARECORD TRAIN_NAME="{name}" TRAIN_SYMBOL="{symbol}" ENGINE="{engine}" FONT="{font}" CARS="0" />'


class CheckTrainSymbols(unittest.TestCase):
    def test_the_repo_passes(self) -> None:
        self.assertEqual(C.main(), 0)

    def test_a_crew_job_code_must_be_a_symbol_and_other_jobs_are_left_out(self) -> None:
        crew = {"jobs": [{"id": "d749", "code": "D749", "kind": "crew"},
                         {"id": "x", "code": "X9", "kind": "crew"},
                         {"id": "yardmaster", "code": "YM-01", "kind": "yardmaster"}]}
        problems = C.crew_problems(TRAINS, crew)
        self.assertEqual(len(problems), 1)
        self.assertIn("'X9'", problems[0])

    def test_roster_names_are_symbols_mapped_names_or_open_questions(self) -> None:
        self.assertEqual(C.roster_problems(TRAINS, ["D749", "D749 Return", *C.NOT_TRAINS]), [])
        problems = C.roster_problems(TRAINS, ["D749", "D749 Return", "D749R2", *C.NOT_TRAINS])
        self.assertEqual(len(problems), 1)
        self.assertIn("'D749R2'", problems[0])

    def test_a_stale_mapping_or_open_question_fails(self) -> None:
        problems = C.roster_problems(TRAINS, ["D749"])
        self.assertTrue(any("opspro_name 'D749 Return' is no train" in p for p in problems))
        self.assertEqual(sum("NOT_TRAINS" in p for p in problems), len(C.NOT_TRAINS))

    def test_an_open_question_the_master_now_holds_fails(self) -> None:
        name = next(iter(C.NOT_TRAINS))
        trains = [*TRAINS, {"train_symbol": name, "train_name": name, "engine": "1", "font": "East",
                            "opspro_name": ""}]
        problems = C.roster_problems(trains, ["D749", "D749 Return", *C.NOT_TRAINS])
        self.assertEqual(problems, [f"check_train_symbols.NOT_TRAINS: {name!r} is in "
                                    f"{C.MASTER.relative_to(ROOT)} now; drop it"])

    def test_the_desk_train_list_matches_the_master_in_order(self) -> None:
        same = header(rec("D749", "D749", "1993", "East"), rec("D749R", "D749 Return", "1993", "West"))
        self.assertEqual(C.header_problems(TRAINS, same), [])
        swapped = header(rec("D749R", "D749 Return", "1993", "West"), rec("D749", "D749", "1993", "East"))
        self.assertTrue(C.header_problems(TRAINS, swapped))
        engine = header(rec("D749", "D749", "2121", "East"), rec("D749R", "D749 Return", "1993", "West"))
        self.assertIn("2121", C.header_problems(TRAINS, engine)[-1])
        self.assertEqual(C.header_problems(TRAINS, ET.fromstring("<DOC/>")),
                         [f"{C.HEADER.relative_to(ROOT)}: no TRAINSTORE/TRAINDATA"])


if __name__ == "__main__":
    unittest.main()

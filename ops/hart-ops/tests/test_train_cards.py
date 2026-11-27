"""The six train cards: road and number from the train master, wording from train_cards.py, EXTRA left blank; a card
and the master that disagree stop with a CardPipelineError."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))
import train_cards  # noqa: E402
from card_errors import CardPipelineError  # noqa: E402
from hartlib import operations  # noqa: E402

HEADER = "train_symbol,train_name,road_name,card_number,on_desks\n"
ROWS = ("D749,D749,CSX,D749,yes\nNVL,NVL,POHC,NVL,yes\nCK1,CK1,HART,CK1,yes\nR23A,Route 23 AM,PRC,Route 23,yes\n"
        "R23P,Route 23 PM,PRC,,yes\nOCS1,OCS-1,CSX,OCS-1,yes\n")


def test_six_trains_with_roads():
    roads = {t["RoadNumber"]: t["RoadName"] for t in train_cards.trains()}
    assert roads == {"D749": "CSX", "NVL": "POHC", "CK1": "HART",
                     "Route 23": "PRC", "OCS-1": "CSX", "EXTRA": "HART"}


def test_road_and_number_come_from_the_master():
    master = operations.read_trains()
    for card, fields in zip(train_cards.CARD_TEXT, train_cards.trains()):
        if card.symbol is not None:
            assert (fields["RoadName"], fields["RoadNumber"]) == (master[card.symbol].road,
                                                                  master[card.symbol].card_number)


def test_extra_has_a_description_and_no_orders():
    extra = next(t for t in train_cards.trains() if t["RoadNumber"] == "EXTRA")
    assert extra["Description"] and extra["Orders"] == []


def test_orders_fit_the_card():
    for t in train_cards.trains():
        assert len(t["Orders"]) <= 7
        assert all(len(line) <= 62 for line in t["Orders"])


def test_cards_are_blank_image_cards():
    cards = train_cards.train_cards()
    assert len(cards) == 6 and all(c[1] is None and c[0]["Blank"] for c in cards)


class MasterErrors(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "trains.csv"

    def fails(self, text: str, pattern: str) -> None:
        self.path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(CardPipelineError, pattern):
            train_cards.trains(self.path)

    def test_a_fake_master_gives_its_roads(self) -> None:
        self.path.write_text(HEADER + ROWS.replace("CK1,CK1,HART", "CK1,CK1,BO"), encoding="utf-8")
        self.assertEqual(train_cards.trains(self.path)[2]["RoadName"], "BO")

    def test_missing_file(self) -> None:
        with self.assertRaisesRegex(CardPipelineError, "the train master cannot be used: .*cannot read it"):
            train_cards.trains(self.path)

    def test_missing_column(self) -> None:
        self.fails("train_symbol,train_name,on_desks\n", "no column road_name, card_number")

    def test_a_card_whose_train_is_not_in_the_master(self) -> None:
        self.fails(HEADER + ROWS.replace("NVL,NVL,POHC,NVL,yes\n", ""), "train NVL has a card .* but no row")

    def test_a_card_whose_train_has_no_card_number(self) -> None:
        self.fails(HEADER + ROWS.replace("POHC,NVL", "POHC,"), "train NVL has a card .* but no card_number")

    def test_a_card_number_with_no_card_text(self) -> None:
        self.fails(HEADER + ROWS.replace("R23P,Route 23 PM,PRC,,", "R23P,Route 23 PM,PRC,Route 23 PM,"),
                   "R23P has a card_number but no card text")

    def test_bad_master_rows(self) -> None:
        cases = [(ROWS + "D749,x,CSX,,yes\n", "train D749 is listed twice"),
                 (ROWS + ",x,CSX,,yes\n", "train_symbol is empty"),
                 (ROWS + "X1,x,CSX,,maybe\n", "on_desks 'maybe' is not yes or no"),
                 (ROWS + "X1,x,,,yes\n", "X1 is on the desks and has no road_name"),
                 (ROWS + "X1,x,CSX,NVL,yes\n", "card_number NVL is NVL's too")]
        for rows, pattern in cases:
            with self.subTest(pattern=pattern):
                self.fails(HEADER + rows, pattern)

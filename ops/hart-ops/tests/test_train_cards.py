"""The six train cards: fixed set, fields filled, EXTRA left blank."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))
import train_cards  # noqa: E402


def test_six_trains_with_roads():
    roads = {t["RoadNumber"]: t["RoadName"] for t in train_cards.TRAINS}
    assert roads == {"D749": "CSX", "NVL": "POHC", "CK1": "HART",
                     "Route 23": "PRC", "OCS-1": "CSX", "EXTRA": "HART"}


def test_extra_has_a_description_and_no_orders():
    extra = next(t for t in train_cards.TRAINS if t["RoadNumber"] == "EXTRA")
    assert extra["Description"] and extra["Orders"] == []


def test_orders_fit_the_card():
    for t in train_cards.TRAINS:
        assert len(t["Orders"]) <= 7
        assert all(len(line) <= 62 for line in t["Orders"])


def test_cards_are_blank_image_cards():
    cards = train_cards.train_cards()
    assert len(cards) == 6 and all(c[1] is None and c[0]["Blank"] for c in cards)

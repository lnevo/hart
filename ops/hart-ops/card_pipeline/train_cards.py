"""Train cards for the poker-size sticker sheet.

Six cards fill the empty slots after the equipment cards. They use the equipment card
layout: the title box says TRAIN (or STREETCAR), the three data rows are operator, train
symbol and job, and the photo area holds the work orders: the crew steps from the ops
docs, then ruled lines for handwriting.

Each card's road and number come from the train master ops/hart-ops/data/trains.csv (road_name and card_number,
read through hartlib.operations.read_trains), by train_symbol; its type, description and orders are card wording,
kept here. The EXTRA card is for a train the Dispatcher calls, so it has no train of the master and keeps its road
and number here.

Sources: Neville_Island_Crew_{D749,NVL,CK1}.docx and Neville_Island_Dispatcher_Train_List.docx
in docs/ops; the P&OV EXTRA job from www/docs/Pittsburgh_Ohio_Valley_Railway.md.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import car_paths  # noqa: F401  (puts hartlib on sys.path)
from card_errors import CardPipelineError
from hartlib import operations


class CardText(NamedTuple):
    """A card's wording. `symbol` is its train in the master; None for the EXTRA card, which gives `road` and
    `number` itself."""
    symbol: str | None
    type: str
    description: str
    orders: tuple[str, ...]
    road: str = ""
    number: str = ""


CARD_TEXT = (
    CardText("D749", "TRAIN", "Neville Island Switcher. Demmler / McKeesport turn", (
        "1. Find train tied down in West Yard with the inbound block.",
        "2. Get dispatcher clearance; run inbound to South Yard.",
        "3. Set out the Demmler / McKeesport inbound.",
        "4. Engine light to engine terminal; fuel and sand.",
        "5. When called, interchange with Yardmaster; lift outbound.",
        "6. With clearance, depart toward McKeesport.",
        "7. On return, tie down in West Yard; secure the engine.",
    )),
    CardText("NVL", "TRAIN", "Neville Island Turn. Scully / McKees Rocks", (
        "1. Assign on the train at Scully Yard with the inbound block.",
        "2. Get dispatcher clearance; run to South Yard.",
        "3. Interchange with Yardmaster; lift the local industry cut.",
        "4. Work Aristech, A. Stucki, Calgon Carbon, Ferrellgas,",
        "    Kosmos Cement and Shenango Coke Works.",
        "5. Return to South Yard; lift the Scully outbound block.",
        "6. With clearance, depart for McKees Rocks / Scully; secure.",
    )),
    CardText("CK1", "TRAIN", "Coke Transfer. Power from the Yardmaster", (
        "1. Report to Yardmaster for the assigned engine.",
        "2. Calibrate the track scale with the scale test car.",
        "3. Shenango Coke Works pickup and delivery as directed.",
        "4. Weigh the coke pull on the South Yard west-lead scale",
        "    at a steady stretch; no brakes under weigh.",
        "5. Sort and set out weighed cars in South Yard.",
    )),
    CardText("R23A", "STREETCAR", "Neville Queen. Streetcar 4678, Barn to McKees Rocks", (
        "Employee Timetable No. 23, station time.",
        "Eastbound: Barn 9:00 AM to McKees Rocks 10:00 AM.",
        "Westbound: McKees Rocks 4:00 PM to Barn 5:00 PM.",
        "Stop at all scheduled stations unless directed.",
        "Ahead of schedule only by dispatcher authority.",
        "Compare watches before duty. Freight holds until clear.",
    )),
    CardText("OCS1", "TRAIN", "Office Car Special. Highest priority", (
        "Run when scheduled.",
        "Highest priority: dispatcher clears the route.",
    )),
    CardText(None, "TRAIN", "Extra train. Runs as called by the Dispatcher", (), road="HART", number="EXTRA"),
)


def trains(master: Path = operations.TRAINS_CSV) -> list[dict]:
    """The cards' fields, in CARD_TEXT order: road and number from the master. CardPipelineError on a master that
    cannot be read, a card whose train is not in it or has no card_number, and a master train with a card_number that
    no card here has."""
    try:
        rows = operations.read_trains(master)
    except operations.OpsDataError as exc:
        raise CardPipelineError(f"the train master cannot be used: {exc}") from exc
    out = []
    for card in CARD_TEXT:
        road, number = card.road, card.number
        if card.symbol is not None:
            train = rows.get(card.symbol)
            if train is None or not train.card_number:
                raise CardPipelineError(f"{master}: train {card.symbol} has a card in train_cards.py but "
                                        f"{'no row' if train is None else 'no card_number'}")
            road, number = train.road, train.card_number
        out.append({"Type": card.type, "RoadName": road, "RoadNumber": number, "Description": card.description,
                    "Orders": list(card.orders)})
    worded = {c.symbol for c in CARD_TEXT}
    unworded = [t.symbol for t in rows.values() if t.card_number and t.symbol not in worded]
    if unworded:
        raise CardPipelineError(f"{master}: {', '.join(unworded)} has a card_number but no card text in "
                                "train_cards.py")
    return out


def train_cards(master: Path = operations.TRAINS_CSV) -> list[tuple[dict, None, dict]]:
    """Card tuples in the shape generate_all_cards.generate reads."""
    return [({**t, "Blank": "1"}, None, {}) for t in trains(master)]

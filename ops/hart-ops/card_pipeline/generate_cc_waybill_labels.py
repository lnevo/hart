#!/usr/bin/env python3
"""Print STS CC/WB shipment waybills as slim poker-sticker labels.

Source: same data as Reports → CC/WB Waybills based on Shipments
(``printable_ccwaybill.php``), which pairs an empty-car bill with a freight
bill. Here each half is one car-card-sized label on the Apostrophe sticker
sheet (same template as equipment cards).

Data: ``archive/docs/cc_shipments.json`` (refresh from live STS with
``--refresh`` when Docker is up).
"""

from __future__ import annotations

import argparse
import functools
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, TypedDict

from docx.table import _Cell

import car_paths
import card_template_sheet
import generate_card_template as g
from card_errors import CardPipelineError
from card_template_records import CcLabelRecord

BASE = Path(__file__).resolve().parent.parent
SHIPMENTS_JSON = BASE / "archive" / "docs" / "cc_shipments.json"
OUTPUT = BASE / "archive" / "docs" / "HART_CC_Waybill_Labels.docx"
LOGO_MAP = BASE / "operator_logos" / "party_logo_map.json"
HART_LOGO = BASE / "operator_logos" / "hart.png"
CARDS_PER_PAGE = card_template_sheet.CARDS_PER_PAGE

EXPORT_PHP = Path(__file__).resolve().parent / "sts_cc_shipments.php"
STS_WEB_CONTAINER = "sts-docker-web-1"  # the web service of the sts-docker compose project
CONTAINER_JSON = "/tmp/cc_shipments.json"  # where sts_cc_shipments.php writes inside the container

BillKind = Literal["empty", "freight"]


class Shipment(TypedDict):
    """One STS shipment as sts_cc_shipments.php exports it: its codes and both ends (load_* and unload_*).

    A null field reads as blank.
    """

    code: str
    consignment: str
    car_code: str
    description: str
    special: str
    load_loc: str
    load_sta: str
    load_trk: str
    load_spot: str
    load_rpt: str
    load_color: str
    unload_loc: str
    unload_sta: str
    unload_trk: str
    unload_spot: str
    unload_rpt: str
    unload_color: str


SHIPMENT_FIELDS = tuple(Shipment.__annotations__)

# A blank freight label that fills the last sticker page.
FILLER: CcLabelRecord = {
    "BillKind": "freight",
    "ShipmentCode": "",
    "ToLocation": "",
    "Station": "",
    "Track": "",
    "Spot": "",
    "CarCode": "",
    "Consignment": "",
    "FromLocation": "",
    "FromStation": "",
    "Color": "lightgrey",
}


@functools.cache
def party_logos() -> dict[str, str]:
    """party_logo_map.json's by_party table (party name to a path under ops/hart-ops), read once; empty with no file."""
    if not LOGO_MAP.exists():
        return {}
    data = json.loads(LOGO_MAP.read_text(encoding="utf-8"))
    return dict(data.get("by_party") or {})


def logo_for_party(party: str) -> str:
    """The party's logo file, else the HART logo, else the card logo; blank when none of them exists."""
    rel = party_logos().get(party.strip(), "")
    if rel:
        path = BASE / rel
        if path.exists():
            return str(path)
    if HART_LOGO.exists():
        return str(HART_LOGO)
    if g.LOGO.exists():
        return str(g.LOGO)
    return ""


def normalize_staging(track: str, spot: str, *, bill_kind: str) -> tuple[str, str, str]:
    """Keep STS staging IN/OUT aligned with empty vs freight flow.

    Empty bill → car goes to the *loading* spot (STAGING IN offline).
    Freight bill → car goes to the *unloading* spot (STAGING OUT offline).
    Non-staging tracks (INBOUND/OUTBOUND/island) are left unchanged.
    """
    track = (track or "").strip()
    spot = (spot or "").strip()
    flow = ""
    if track.lower() == "staging":
        track = "STAGING"
        if bill_kind == "empty":
            spot = "IN"
            flow = "IN"
        elif bill_kind == "freight":
            spot = "OUT"
            flow = "OUT"
        else:
            flow = spot.upper() if spot.upper() in {"IN", "OUT"} else ""
    elif spot.upper() in {"IN", "OUT"}:
        flow = spot.upper()
    return track, spot, flow


def export_php(path: Path = EXPORT_PHP) -> str:
    """The shipment export as php -r takes it: the file less its <?php line and the // header under it, from the blank line on."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines or lines[0].strip() != "<?php":
        raise CardPipelineError(f"{path} does not start with <?php")
    body = lines[1:]
    while body and body[0].startswith("//"):
        body.pop(0)
    return "".join(body)


def refresh_shipments_from_sts(dest: Path = SHIPMENTS_JSON) -> int:
    """Pull current shipments from the STS web container into JSON."""
    php = export_php()
    try:
        count = subprocess.check_output(
            ["docker", "exec", STS_WEB_CONTAINER, "php", "-r", php],
            text=True,
        ).strip()
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.check_call(["docker", "cp", f"{STS_WEB_CONTAINER}:{CONTAINER_JSON}", str(dest)])
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CardPipelineError(f"could not export the shipments from the {STS_WEB_CONTAINER} container: {exc}") from exc
    try:
        return int(count)
    except ValueError as exc:
        raise CardPipelineError(f"the shipment export printed {count!r}, not a count") from exc


def read_shipments(path: Path) -> list[Shipment]:
    """The shipments JSON: a list of objects, each with every field a label reads (SHIPMENT_FIELDS)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CardPipelineError(f"cannot read the shipments {path}: {exc}") from exc
    if not isinstance(data, list):
        raise CardPipelineError(f"{path}: expected a list of shipments, found {type(data).__name__}")
    for i, shipment in enumerate(data):
        if not isinstance(shipment, dict):
            raise CardPipelineError(f"{path}: shipment {i} is {type(shipment).__name__}, not an object")
        missing = [f for f in SHIPMENT_FIELDS if f not in shipment]
        if missing:
            raise CardPipelineError(f"{path}: shipment {i} ({shipment.get('code')}) has no {', '.join(missing)}")
    return data


def _text(shipment: Mapping[str, object], field: str) -> str:
    """A shipment field stripped; a null reads as blank."""
    value = shipment[field]
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CardPipelineError(f"shipment {shipment.get('code')}: {field} is {value!r}, not text")
    return value.strip()


def _station(shipment: Mapping[str, object], end: Literal["load", "unload"]) -> str:
    """The party an end of the shipment names: its reporting station, else its routing station."""
    return _text(shipment, f"{end}_rpt") or _text(shipment, f"{end}_sta")


def empty_label(s: Shipment) -> CcLabelRecord:
    """The empty bill (STS mtybill): the empty car goes to the loading location."""
    party = _station(s, "load")
    track, spot, flow = normalize_staging(s["load_trk"], s["load_spot"], bill_kind="empty")
    return {
        "BillKind": "empty",
        "ShipmentCode": _text(s, "code"),
        "ToLocation": _text(s, "load_loc"),
        "Station": party,
        "Track": track,
        "Spot": spot,
        "Flow": flow,
        "CarCode": _text(s, "car_code"),
        "Consignment": _text(s, "consignment"),
        "Color": _text(s, "load_color"),
        "Description": _text(s, "description"),
        "LogoParty": party,
        "LogoPath": logo_for_party(party),
    }


def freight_label(s: Shipment) -> CcLabelRecord:
    """The freight bill (STS waybill): the load goes from the loading to the unloading location."""
    party = _station(s, "unload")
    track, spot, flow = normalize_staging(s["unload_trk"], s["unload_spot"], bill_kind="freight")
    return {
        "BillKind": "freight",
        "ShipmentCode": _text(s, "code"),
        "ToLocation": _text(s, "unload_loc"),
        "Station": party,
        "Track": track,
        "Spot": spot,
        "Flow": flow,
        "CarCode": _text(s, "car_code"),
        "Consignment": _text(s, "consignment"),
        "FromLocation": _text(s, "load_loc"),
        "FromStation": _station(s, "load"),
        "Color": _text(s, "unload_color"),
        "Description": _text(s, "description"),
        "Special": _text(s, "special"),
        "LogoParty": party,
        "LogoPath": logo_for_party(party),
    }


def labels_from_shipments(shipments: Sequence[Shipment]) -> list[CcLabelRecord]:
    """Two labels per shipment: empty (mtybill) then freight (waybill).

    STS is the source of truth for locations/commodities/car codes. Staging
    spots are normalized so empty bills are Staging IN and freight bills are
    Staging OUT (matching CC/WB flow).
    """
    labels: list[CcLabelRecord] = []
    for s in shipments:
        labels.append(empty_label(s))
        labels.append(freight_label(s))
    return labels


def pad_to_page(deck: list[CcLabelRecord]) -> list[CcLabelRecord]:
    """The deck with blank FILLER labels added until the last page is full."""
    need = (CARDS_PER_PAGE - len(deck) % CARDS_PER_PAGE) % CARDS_PER_PAGE
    return deck + [FILLER.copy() for _ in range(need)]


def _fill_slot(cell: _Cell, idx: int, record: CcLabelRecord) -> None:
    g.build_cc_waybill_label(cell, idx=idx, record=record)


def generate(labels: list[CcLabelRecord], output: Path = OUTPUT) -> None:
    """Write the labels to ``output``, nine to a sticker page, the last page filled with blanks."""
    sticker_sheet = car_paths.require_sticker_sheet()
    card_template_sheet.write_sticker_deck(pad_to_page(labels), _fill_slot, sticker_sheet=sticker_sheet,
                                           output=output)


def count_kind(labels: Sequence[CcLabelRecord], kind: BillKind) -> int:
    """How many of the labels are ``kind`` bills."""
    return sum(1 for label in labels if label["BillKind"] == kind)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """The command line: --refresh, --json and --output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-export shipments from the live STS Docker DB before printing",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=SHIPMENTS_JSON,
        help=f"Shipments JSON (default: {SHIPMENTS_JSON})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help=f"Output docx (default: {OUTPUT})",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.refresh or not args.json.exists():
        n = refresh_shipments_from_sts(args.json)
        print(f"Refreshed {n} shipments → {args.json}")

    shipments = read_shipments(args.json)
    labels = labels_from_shipments(shipments)
    generate(labels, args.output)

    pages = card_template_sheet.page_count(len(labels))
    print(f"Wrote {args.output}")
    print(
        f"  {len(shipments)} shipments → {count_kind(labels, 'empty')} empty + {count_kind(labels, 'freight')} freight "
        f"labels · {pages} sticker pages (9/page)"
    )


if __name__ == "__main__":
    try:
        main()
    except CardPipelineError as exc:
        raise SystemExit(str(exc)) from exc

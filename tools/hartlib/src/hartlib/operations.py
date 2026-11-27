"""Operations Pro roster files, read: the cars, engines and trains of an Operations*Roster.xml.

    from hartlib import operations
    for car in operations.cars(operations.ROSTERS["cars"]):    # <car> elements, attributes as JMRI wrote them
        car.get("id"), car.get("roadName"), car.get("outOfService")

The repo's Operations Pro files live in jmri/layouts/hart/operations/ (ADR-015, the copy the hosts load) and, for
the car pipeline, ops/hart-ops/data/; callers name the file. Each reader returns the elements of its section in file
order (./cars/car, ./engines/engine, ./trains/train), so a <car> elsewhere in the file is never counted. A missing
file raises FileNotFoundError and a broken one ET.ParseError, both naming the file (the ParseError keeps its
code and position). Nothing here writes: the tools that change a roster keep JMRI's header and layout themselves.

The roads and models the rosters and the car pipeline name are kept by hand in ops/hart-ops/data/roads.csv and
loco_models.csv; read_roads and read_loco_models are their one reader:

    r = operations.read_roads()   # Roads: codes, display, car_aliases, engine_aliases
    r.display["NW"]               # "N&W": the marks a card shows for a roster road
    r.car_aliases["N&W"]          # "NW": a spelling read off a car photo -> the roster road
    r.engine_aliases["CONRAIL"]   # "CR": a spelling in a loco row -> the roster road
    operations.read_loco_models() # {"GP38": "EMD", ...} in file order (the card pipeline's part match reads it in order)

roads.csv has one row per roster road code (`road`, the key, as the rosters and locos.csv give it: BO, CR, CSX). `marks`
is what a card shows (B&O); empty, a card shows the code. `car_spellings` and `engine_spellings` are the spellings, `;`
between them, that the car photo matcher (process_car_images) and the loco matcher (engine_lookup) turn into the
code; a spelling may be the code itself, which the car matcher needs to accept a road as written. A spelling names
one road only. loco_models.csv maps a model (as Operations Pro names it) to its builder (`mfg`).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .errors import HartlibError

OPERATIONS_DIR = paths.REPO_ROOT / "jmri" / "layouts" / "hart" / "operations"
HART_OPS_DATA = paths.REPO_ROOT / "ops" / "hart-ops" / "data"
ROSTERS = {
    "cars": OPERATIONS_DIR / "OperationsCarRoster.xml",
    "engines": OPERATIONS_DIR / "OperationsEngineRoster.xml",
    "trains": OPERATIONS_DIR / "OperationsTrainRoster.xml",
}
SECTIONS = {"cars": "car", "engines": "engine", "trains": "train"}


def root(path: Path | str) -> ET.Element:
    """The <operations-config> element of an Operations Pro file (its DOCTYPE and stylesheet lines are skipped)."""
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as err:
        named = ET.ParseError(f"{path}: {err}")
        named.code, named.position = err.code, err.position   # where the damage is, as the parser said
        raise named from err


def section(path: Path | str, name: str) -> list[ET.Element]:
    """The elements of one section, e.g. section(path, "cars") is every ./cars/car, in file order."""
    if name not in SECTIONS:
        raise ValueError(f"no Operations Pro section {name!r}: one of {', '.join(SECTIONS)}")
    return root(path).findall(f"./{name}/{SECTIONS[name]}")


def cars(path: Path | str = ROSTERS["cars"]) -> list[ET.Element]:
    return section(path, "cars")


def engines(path: Path | str = ROSTERS["engines"]) -> list[ET.Element]:
    return section(path, "engines")


def trains(path: Path | str = ROSTERS["trains"]) -> list[ET.Element]:
    return section(path, "trains")


def ids(elements: list[ET.Element]) -> list[str]:
    """Each element's id attribute ("" for none), in order."""
    return [e.get("id", "") for e in elements]


ROADS_CSV = HART_OPS_DATA / "roads.csv"
LOCO_MODELS = HART_OPS_DATA / "loco_models.csv"
ROAD_COLUMNS = ["road", "marks", "car_spellings", "engine_spellings"]


class OpsDataError(HartlibError, ValueError):
    """A hand-kept car pipeline file (roads, loco models, the operator sheet's industries, notes and usages) cannot be
    read or is not in its shape; the message names the file, and the line for a bad row."""


@dataclass(frozen=True)
class Roads:
    codes: tuple[str, ...]                                          # every road code, in file order
    display: dict[str, str] = field(default_factory=dict)          # code -> marks, for the codes that have marks
    car_aliases: dict[str, str] = field(default_factory=dict)      # spelling -> code (process_car_images)
    engine_aliases: dict[str, str] = field(default_factory=dict)   # spelling -> code (engine_lookup)


def _rows(path: Path, required: list[str]) -> list[tuple[int, dict[str, str]]]:
    from .railroad_facts import FactsError, read_rows   # here, so reading a roster loads no layout modules
    try:
        return read_rows(path, required, optional=["notes"])
    except FactsError as exc:
        raise OpsDataError(str(exc)) from exc


def _spellings(cell: str) -> list[str]:
    return [s for s in (p.strip() for p in cell.split(";")) if s]


def read_roads(path: Path = ROADS_CSV) -> Roads:
    """The roads of roads.csv. Stops on an empty or repeated road, or a spelling given to two roads."""
    codes: list[str] = []
    display: dict[str, str] = {}
    aliases: dict[str, dict[str, str]] = {"car_spellings": {}, "engine_spellings": {}}
    for line, row in _rows(path, ROAD_COLUMNS):
        code = row["road"]
        if not code:
            raise OpsDataError(f"{path}:{line}: road is empty")
        if code in codes:
            raise OpsDataError(f"{path}:{line}: road {code} is listed twice")
        codes.append(code)
        if row["marks"]:
            display[code] = row["marks"]
        for col, table in aliases.items():
            for s in _spellings(row[col]):
                if s != s.upper():   # the matchers upper-case what they look up, so a lower-case spelling never matches
                    raise OpsDataError(f"{path}:{line}: {col} {s!r} must be in capitals ({s.upper()!r})")
                if table.get(s, code) != code:
                    raise OpsDataError(f"{path}:{line}: {col} {s!r} is already road {table[s]}'s")
                table[s] = code
    return Roads(tuple(codes), display, aliases["car_spellings"], aliases["engine_spellings"])


def read_loco_models(path: Path = LOCO_MODELS) -> dict[str, str]:
    """{model: builder} of loco_models.csv, in file order. Stops on an empty or repeated model or an empty builder."""
    out: dict[str, str] = {}
    for line, row in _rows(path, ["model", "mfg"]):
        if not row["model"] or not row["mfg"]:
            raise OpsDataError(f"{path}:{line}: model and mfg are needed")
        if row["model"] in out:
            raise OpsDataError(f"{path}:{line}: model {row['model']} is listed twice")
        out[row["model"]] = row["mfg"]
    return out


# ---------------------------------------------------------------- the operator sheet's industry tables

INDUSTRY_SHEET = HART_OPS_DATA / "industry_sheet.csv"
INDUSTRY_NOTES = HART_OPS_DATA / "industry_notes.csv"
SPOT_USAGES = HART_OPS_DATA / "spot_usages.csv"


@dataclass(frozen=True)
class IndustrySheet:
    """One industry of the operator sheet and the waybill decks (industry_sheet.csv)."""
    industry_id: str      # industries.csv's key
    sheet_name: str       # the name the sheet and the waybills key it by (spot_assignments.csv's spelling)
    sheet_order: int      # its place among the sheet's island industries
    waybill_order: int | None   # its place in the waybill decks; None: no waybills (Shenango)
    logo: str             # a file in ops/hart-ops/operator_logos/
    logo_width: float     # the logo's width on the page, in inches


def _whole(path: Path, line: int, col: str, cell: str) -> int:
    if not re.fullmatch(r"[0-9]+", cell):
        raise OpsDataError(f"{path}:{line}: {col} {cell!r} is not a whole number")
    return int(cell)


def read_industry_sheet(path: Path = INDUSTRY_SHEET) -> list[IndustrySheet]:
    """The rows of industry_sheet.csv in file order. Stops on a repeated industry_id or sheet_name or a bad number."""
    out: list[IndustrySheet] = []
    cols = ["industry_id", "sheet_name", "sheet_order", "waybill_order", "logo", "logo_width"]
    for line, row in _rows(path, cols):
        if not row["industry_id"] or not row["sheet_name"] or not row["logo"]:
            raise OpsDataError(f"{path}:{line}: industry_id, sheet_name and logo are needed")
        if any(r.industry_id == row["industry_id"] or r.sheet_name == row["sheet_name"] for r in out):
            raise OpsDataError(f"{path}:{line}: {row['industry_id']} ({row['sheet_name']}) is listed twice")
        try:
            width = float(row["logo_width"])
        except ValueError as exc:
            raise OpsDataError(f"{path}:{line}: logo_width {row['logo_width']!r} is not a number") from exc
        waybill = row["waybill_order"]
        for col in ("sheet_order", "waybill_order"):
            if row[col] and any(str(getattr(r, col)) == row[col] for r in out):
                raise OpsDataError(f"{path}:{line}: {col} {row[col]} is another industry's too")
        out.append(IndustrySheet(row["industry_id"], row["sheet_name"],
                                 _whole(path, line, "sheet_order", row["sheet_order"]),
                                 _whole(path, line, "waybill_order", waybill) if waybill else None,
                                 row["logo"], width))
    return out


def read_industry_notes(path: Path = INDUSTRY_NOTES) -> dict[str, list[str]]:
    """{industry_id: its paragraphs, by line} of industry_notes.csv. Stops on an empty text or a repeated line."""
    out: dict[str, dict[int, str]] = {}
    for line, row in _rows(path, ["industry_id", "line", "text"]):
        n = _whole(path, line, "line", row["line"])
        if not row["industry_id"] or not row["text"]:
            raise OpsDataError(f"{path}:{line}: industry_id and text are needed")
        if n in out.setdefault(row["industry_id"], {}):
            raise OpsDataError(f"{path}:{line}: {row['industry_id']} line {n} is listed twice")
        out[row["industry_id"]][n] = row["text"]
    return {k: [v[n] for n in sorted(v)] for k, v in out.items()}


def read_spot_usages(path: Path = SPOT_USAGES) -> dict[str, str]:
    """{usage, lower case: the label the sheet prints} of spot_usages.csv, in file order."""
    out: dict[str, str] = {}
    for line, row in _rows(path, ["usage", "label"]):
        if not row["usage"] or not row["label"]:
            raise OpsDataError(f"{path}:{line}: usage and label are needed")
        if row["usage"] != row["usage"].lower() or row["usage"] in out:
            raise OpsDataError(f"{path}:{line}: usage {row['usage']!r} must be lower case and listed once")
        out[row["usage"]] = row["label"]
    return out


# ---------------------------------------------------------------- the train master

TRAINS_CSV = HART_OPS_DATA / "trains.csv"
TRAIN_COLUMNS = ["train_symbol", "train_name", "road_name", "card_number", "on_desks"]


@dataclass(frozen=True)
class Train:
    """A train of trains.csv (ADR-039), the columns the train cards read."""
    symbol: str           # train_symbol, the key (R23A, D749)
    name: str             # train_name, the CATS desk name; empty on a staging train
    road: str             # road_name, the railroad that runs it (CSX, POHC, PRC, HART)
    card_number: str      # the number its train card shows; empty: it has no card of its own
    on_desks: bool


def read_trains(path: Path = TRAINS_CSV) -> dict[str, Train]:
    """{train_symbol: Train} of trains.csv in file order. Stops on an empty or repeated symbol, an on_desks that is not
    yes or no, a train on the desks with no road_name, and a card_number given to two trains."""
    out: dict[str, Train] = {}
    cards: dict[str, str] = {}
    for line, row in _rows(path, TRAIN_COLUMNS):
        symbol = row["train_symbol"]
        if not symbol:
            raise OpsDataError(f"{path}:{line}: train_symbol is empty")
        if symbol in out:
            raise OpsDataError(f"{path}:{line}: train {symbol} is listed twice")
        if row["on_desks"] not in ("yes", "no"):
            raise OpsDataError(f"{path}:{line}: on_desks {row['on_desks']!r} is not yes or no")
        if row["on_desks"] == "yes" and not row["road_name"]:
            raise OpsDataError(f"{path}:{line}: {symbol} is on the desks and has no road_name")
        card = row["card_number"]
        if card and cards.setdefault(card, symbol) != symbol:
            raise OpsDataError(f"{path}:{line}: card_number {card} is {cards[card]}'s too")
        out[symbol] = Train(symbol, row["train_name"], row["road_name"], card, row["on_desks"] == "yes")
    return out

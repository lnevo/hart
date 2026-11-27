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

import xml.etree.ElementTree as ET
from pathlib import Path

from dataclasses import dataclass, field

from . import paths
from .errors import HartlibError
from .railroad_facts import FactsError, read_rows

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


class RoadsError(HartlibError, ValueError):
    """roads.csv or loco_models.csv cannot be read or is not in its shape; the message names the file and line."""


@dataclass(frozen=True)
class Roads:
    codes: tuple[str, ...]                                          # every road code, in file order
    display: dict[str, str] = field(default_factory=dict)          # code -> marks, for the codes that have marks
    car_aliases: dict[str, str] = field(default_factory=dict)      # spelling -> code (process_car_images)
    engine_aliases: dict[str, str] = field(default_factory=dict)   # spelling -> code (engine_lookup)


def _rows(path: Path, required: list[str]) -> list[tuple[int, dict[str, str]]]:
    try:
        return read_rows(path, required, optional=["notes"])
    except FactsError as exc:
        raise RoadsError(str(exc)) from exc


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
            raise RoadsError(f"{path}:{line}: road is empty")
        if code in codes:
            raise RoadsError(f"{path}:{line}: road {code} is listed twice")
        codes.append(code)
        if row["marks"]:
            display[code] = row["marks"]
        for col, table in aliases.items():
            for s in _spellings(row[col]):
                if table.get(s, code) != code:
                    raise RoadsError(f"{path}:{line}: {col} {s!r} is already road {table[s]}'s")
                table[s] = code
    return Roads(tuple(codes), display, aliases["car_spellings"], aliases["engine_spellings"])


def read_loco_models(path: Path = LOCO_MODELS) -> dict[str, str]:
    """{model: builder} of loco_models.csv, in file order. Stops on an empty or repeated model or an empty builder."""
    out: dict[str, str] = {}
    for line, row in _rows(path, ["model", "mfg"]):
        if not row["model"] or not row["mfg"]:
            raise RoadsError(f"{path}:{line}: model and mfg are needed")
        if row["model"] in out:
            raise RoadsError(f"{path}:{line}: model {row['model']} is listed twice")
        out[row["model"]] = row["mfg"]
    return out

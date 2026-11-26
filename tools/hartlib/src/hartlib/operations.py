"""Operations Pro roster files, read: the cars, engines and trains of an Operations*Roster.xml.

    from hartlib import operations
    for car in operations.cars(operations.ROSTERS["cars"]):    # <car> elements, attributes as JMRI wrote them
        car.get("id"), car.get("roadName"), car.get("outOfService")

The repo's Operations Pro files live in jmri/layouts/hart/operations/ (ADR-015, the copy the hosts load) and, for
the car pipeline, ops/hart-ops/data/; callers name the file. Each reader returns the elements of its section in file
order (./cars/car, ./engines/engine, ./trains/train), so a <car> elsewhere in the file is never counted. A missing
file raises FileNotFoundError and a broken one ET.ParseError, both naming the file (the ParseError keeps its
code and position). Nothing here writes: the tools that change a roster keep JMRI's header and layout themselves.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from . import paths

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

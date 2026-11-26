"""The XML readers of tools/audit/check_layout_facts.py: desks, GUIObjects.xml and tables.xml, each parsed once per
file version, and the elements and attributes the checks need, with a named error when one is missing."""
from __future__ import annotations

import functools
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar, cast

from hartlib import tables as hart_tables

T = TypeVar("T")


class LayoutFactsError(ValueError):
    """A desk or tables file lacks an element or attribute the checks read."""


def _cached(load: Callable[[str], T], path: Path) -> T:
    """``load(path)`` once per file version: a desk or tables.xml is read by several checks."""
    st = Path(path).stat()
    return cast(T, _load_cached(load, str(Path(path).resolve()), (st.st_mtime_ns, st.st_size)))


@functools.lru_cache(maxsize=None)
def _load_cached(load: Callable[[str], object], path: str, _stamp: tuple[int, int]) -> object:
    return load(path)


def need(el: ET.Element, attr: str) -> str:
    """`el`'s attribute `attr`; LayoutFactsError naming the element when it has none."""
    value = el.get(attr)
    if value is None:
        raise LayoutFactsError(f"<{el.tag} ident={el.get('ident')!r} NAME={el.get('NAME')!r}> has no {attr}")
    return value


def desk_root(path: Path) -> ET.Element:
    """The root element of a desk or GUIObjects.xml (parse)."""
    root = parse(path).getroot()
    if root is None:
        raise LayoutFactsError(f"{path}: no root element")
    return root


def trackplan(path: Path) -> ET.Element:
    """A CATS desk's TRACKPLAN element."""
    plan = desk_root(path).find("TRACKPLAN")
    if plan is None:
        raise LayoutFactsError(f"{path}: no TRACKPLAN")
    return plan


def parse(path: Path) -> ET.ElementTree[ET.Element]:
    """ET.parse, once per file version (a desk or GUIObjects.xml)."""
    return _cached(ET.parse, path)


def parse_tables(path: Path) -> ET.Element:
    """Root of tables.xml via hartlib, once per file version."""
    return _cached(hart_tables.read, path)

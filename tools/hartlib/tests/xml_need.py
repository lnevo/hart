"""Test helper: the one element a path names, or the test fails at once (ElementTree's find returns None)."""
from __future__ import annotations

import xml.etree.ElementTree as ET


def need(parent: ET.Element, path: str) -> ET.Element:
    """parent.find(path), failing the test (AssertionError) when nothing matches."""
    el = parent.find(path)
    if el is None:
        raise AssertionError(f"no {path} under <{parent.tag}>")
    return el

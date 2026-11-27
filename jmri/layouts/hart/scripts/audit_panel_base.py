"""The parts every audit_panel_contracts check shares: the Audit record the checks fill, and the XML text helpers.

audit_panel_contracts.py imports this from its own folder (paths.LAYOUT_SCRIPTS), with audit_panel_tables.py (the
tables' own settings, sensors and turnouts) and audit_panel_graph.py (what Discover and Stage 1 store).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Where a check sends a problem: Audit.error, or Audit.warn for a check that only warns (Audit.reporter).
Problem = Callable[[str], None]

# How many items of a long list a message names before " ..."
SHOWN = 8


def first_items(items: list[str], sep: str = "; ") -> str:
    """The first SHOWN items joined by sep, with " ..." when there are more."""
    return sep.join(items[:SHOWN]) + (" ..." if len(items) > SHOWN else "")


def text(element: ET.Element | None, child: str) -> str:
    if element is None:
        return ""
    value = element.findtext(child)
    return value.strip() if value else ""


def attr_or_child(element: ET.Element, name: str) -> str:
    return (element.get(name) or text(element, name)).strip()


@dataclass
class Audit:
    label: str
    path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    facts: dict[str, object] = field(default_factory=dict)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def reporter(self, required: bool) -> Problem:
        """Where a check's problems go: errors when the check is `required`, else warnings."""
        return self.error if required else self.warn

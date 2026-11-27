"""The sources tools/audit/check_layout_facts.py reads and the report its checks write to, shared by its parts
(layout_facts_tables, layout_facts_desks, layout_facts_uss, layout_facts_levels).

hartlib must be importable (check_layout_facts.py puts tools/hartlib/src on sys.path); this module puts the layout
scripts (layout_facts.py) and the CATS scripts (digicon_trace.py) on it.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import Counter

from hartlib import level_masts, paths, railroad

if str(paths.LAYOUT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(paths.LAYOUT_SCRIPTS))
if str(paths.CATS_DIR / "scripts") not in sys.path:
    sys.path.append(str(paths.CATS_DIR / "scripts"))

import digicon_trace as trace  # noqa: E402
import layout_facts as facts  # noqa: E402

__all__ = ["ADDED_LEVELS", "CLOSED", "DESKS", "DEVICE_MAP", "GUI", "HART", "MASTS", "PLAIN_TURNOUTS", "ROOT",
           "STAGING_LEVELS", "TABLES", "THROWN", "Cells", "Report", "facts", "trace"]

ROOT = paths.REPO_ROOT
HART = paths.LAYOUT_DIR
TABLES = paths.TABLES_XML
GUI = HART / "ctc/GUIObjects.xml"
DESKS = (ROOT / "cats/panels/HART_CTC.xml", ROOT / "cats/panels/HART_ABS.xml")
MASTS = railroad.Sources.under().masts     # masts.csv: each mast's level, facing and protected blocks
# the staging level (its field masts and turnouts), and the main and upper levels (on virtual heads and turnouts)
STAGING_LEVELS = (int(railroad.STAGING_LEVEL),)
ADDED_LEVELS = tuple(lv for lv in level_masts.LEVELS if lv not in STAGING_LEVELS)
DEVICE_MAP = railroad.Sources.under().devices     # the device master: the main and upper block names

CLOSED, THROWN = "2", "4"
PLAIN_TURNOUTS = frozenset({"RH_TURNOUT", "LH_TURNOUT", "WYE_TURNOUT"})

Cells = dict[tuple[int, int], ET.Element]     # a CATS desk's SECTION elements by (x, y) (digicon_trace.track_cells)


class Report:
    """The checks' messages, each under a key naming the switch, track or mast it is about."""

    def __init__(self) -> None:
        self.found: dict[str, list[str]] = {}
        self.switch_count = 0           # set by check_layout_facts.run
        self.paths_stored = False       # the checked tables store block paths (a PanelPro Store)

    def add(self, key: str, message: str) -> None:
        self.found.setdefault(key, []).append(message)

    def messages(self) -> list[str]:
        return [m for msgs in self.found.values() for m in msgs]

    def failures(self, known: dict[str, str]) -> list[str]:
        """Every message not in ``known`` (matched exactly), and every ``known`` message that did not happen."""
        seen = self.messages()
        out = [m for m in seen if m not in known]
        out += [f"KNOWN entry no longer happens; remove it from KNOWN: {m}" for m in known if m not in seen]
        return out

    def known(self, known: dict[str, str]) -> list[str]:
        """One line per KNOWN reason that happened, with its count."""
        hits = Counter(known[m] for m in self.messages() if m in known)
        return [f"{reason} ({count} difference(s))" for reason, count in hits.items()]

"""The cells of one LCOS inventory sheet as the wiring viewer reads them (build_wiring_json.py): header tables, notes
without their rename history, port ids, and what a DNOU8 or DNIN8 pin drives or reads.

No file is read here: the rows come from write_inventory.workbook() through build_wiring_json.read_sheets, already
cleaned to one line of text per cell.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Literal, NamedTuple

Row = dict[str, str]                   # one sheet row, keyed by its header

PORT_RE = re.compile(r"^(?P<node>[A-Z]+\d+)-(?P<board>(?:OU|IN|B)\d+)-(?P<pin>\d+)$")
HEAD_RE = re.compile(r"^Head (?P<head>.+?) (?P<color>[RYG])$")

OutKindName = Literal["lamp", "motor", "cal", "relay", "reserved", "spare", "other"]
InKindName = Literal["feedback", "button", "spare", "other"]


def table(rows: list[list[str]], header_idx: int, stop: Callable[[list[str]], bool] | None = None) -> list[Row]:
    """Rows under header_idx as dicts keyed by header, trailing empty columns dropped."""
    header = rows[header_idx]
    width = max((i + 1 for i, h in enumerate(header) if h), default=0)
    header = header[:width]
    out = []
    for r in rows[header_idx + 1 :]:
        if stop and stop(r):
            break
        d = {header[i]: (r[i] if i < len(r) else "") for i in range(width) if header[i]}
        if any(d.values()):
            out.append(d)
    return out


def strip_history(note: str) -> str:
    """Drop rename history ("was S3-6 G", "renamed for linear6") that only confuses a reader.

    The inventory's "was" notes disagree with each other (DNOU8 and DigiconSignals give
    different old IDs for the same pin), so none of them are published.
    """
    note = re.sub(r"\s*\([^)]*\bwas\b[^)]*\)", "", note)
    parts = re.split(r"\s*[;|]\s*", note)
    keep = [p for p in parts if p and not re.match(r"(?i)was\b", p) and "renamed for" not in p.lower()]
    return "; ".join(keep).strip()


def version_of(path: Path) -> str:
    """The workbook's version from its file name (LCOS_Layout_Inventory_v86.xlsx: "v86"); the stem when it has none."""
    m = re.search(r"_v(\d+)", path.stem)
    return f"v{m.group(1)}" if m else path.stem


def split_list(s: str) -> list[str]:
    """A comma-separated cell as its items, blanks dropped."""
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def parse_port(pid: str) -> tuple[str, str, int] | None:
    """(node, board, pin) of a port id such as "C13-OU2-5"; None when pid is not one."""
    m = PORT_RE.match(pid)
    if not m:
        return None
    return m.group("node"), m.group("board"), int(m.group("pin"))


def board_sort(b: str) -> tuple[str, int]:
    """A board's sort key: its letters, then its number (OU2 before OU10)."""
    m = re.match(r"([A-Z]+)(\d+)", b)
    return (m.group(1), int(m.group(2))) if m else (b, 0)


def node_sort(n: str) -> tuple[int, int]:
    """A node's sort key: M nodes, then C, then D, each by number; any other id last."""
    m = re.match(r"([A-Z]+)(\d+)", n)
    return ({"M": 0, "C": 1, "D": 2}.get(m.group(1), 3), int(m.group(2))) if m else (9, 0)


class OutKind(NamedTuple):
    """What a DNOU8 pin drives; color and head are set for a lamp only ("Head 12 R": head "12", color "R")."""
    kind: OutKindName
    color: str = ""
    head: str = ""


def out_kind(device: str, dtype: str) -> OutKind:
    """What a DNOU8 pin drives, from its device name and device type."""
    m = HEAD_RE.match(device)
    if m:
        return OutKind("lamp", m.group("color"), m.group("head"))
    t = dtype.lower()
    if "turnout" in t:
        return OutKind("motor")
    if "cal" in t:
        return OutKind("cal")
    if "relay" in t:
        return OutKind("relay")
    if "reserved" in t or device.lower() == "reserved":
        return OutKind("reserved")
    if not device:
        return OutKind("spare")
    return OutKind("other")


def in_kind(device: str, dtype: str) -> InKindName:
    """What a DNIN8 pin reads, from its device name and device type."""
    t = dtype.lower()
    if "feedback" in t:
        return "feedback"
    if "button" in t:
        return "button"
    if not device:
        return "spare"
    return "other"


def pick_location(locs: list[str]) -> str:
    """The board's place: the most common specific location among its used pins."""
    locs = [l for l in locs if l]
    if not locs:
        return ""
    specific = [l for l in locs if "(" in l]
    return Counter(specific or locs).most_common(1)[0][0]

"""refresh_wiring_docs: cell rewrites and sheet lookups shared by every workbook the refresh writes.

The walk_* / fix_* / apply_* / drop_* functions walk a sheet (or every sheet of a workbook), rewrite string cells by
one rule from refresh_wiring_rules and return how many cells changed; the rest work on one value or one header row.
"""
from __future__ import annotations

import re

from openpyxl.worksheet.worksheet import Worksheet

from refresh_wiring_rules import (
    _SW_TOKEN_CTC,
    _UPPER_NAME_TOKENS,
    DCC_SWITCH_TO_CTC,
    LEGACY_NODE_IDS,
    MANGLED_SWITCH_FIXES,
    NODE_ID_TOKEN,
)


def header_index(ws: Worksheet) -> dict[str, int]:
    return {str(c.value): i for i, c in enumerate(next(ws.iter_rows(min_row=1, max_row=1)), start=1) if c.value}


def _unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def replace_in_cell(value, replacements: list[tuple[str, str]]):
    if not isinstance(value, str) or not value:
        return value
    out = value
    for old, new in replacements:
        if old in out:
            out = out.replace(old, new)
    return out


def walk_replace(ws: Worksheet, replacements: list[tuple[str, str]]) -> int:
    n = 0
    for row in ws.iter_rows():
        for cell in row:
            new = replace_in_cell(cell.value, replacements)
            if new != cell.value:
                cell.value = new
                n += 1
    return n


def rewrite_legacy_node_ids(value):
    """Rewrite C12/C3/… tokens; longest match is the full number (C12 ≠ C1)."""
    if not isinstance(value, str) or not value:
        return value

    def repl(match: re.Match[str]) -> str:
        tok = match.group(1)
        return LEGACY_NODE_IDS.get(tok, tok)

    return NODE_ID_TOKEN.sub(repl, value)


def fix_mangled_switch_names(wb) -> int:
    """Undo v84 10038/1127 concatenations on every sheet."""
    n = 0
    for ws in wb.worksheets:
        n += walk_replace(ws, MANGLED_SWITCH_FIXES)
    return n


def apply_ctc_switch_names(wb) -> int:
    """Switch 113 → Switch 35 (and the rest of DCC 100–119)."""
    n = 0
    for ws in wb.worksheets:
        n += walk_replace(ws, DCC_SWITCH_TO_CTC)
    return n


def apply_legacy_sw_tokens(wb) -> int:
    """SCXB / SW17 / … on Nodes summaries (digit-bounded)."""
    n = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if not isinstance(cell.value, str) or not cell.value:
                    continue
                out = cell.value
                for pat, repl in _SW_TOKEN_CTC:
                    out = pat.sub(repl, out)
                if out != cell.value:
                    cell.value = out
                    n += 1
    return n


def apply_upper_deck_names(wb) -> int:
    """SW127/NIX/S4-1 → Switch 63 / Switch 61 / 64R (upper CTC 61+)."""
    n = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if not isinstance(cell.value, str) or not cell.value:
                    continue
                out = cell.value
                for pat, repl in _UPPER_NAME_TOKENS:
                    out = pat.sub(repl, out)
                if out != cell.value:
                    cell.value = out
                    n += 1
    return n


_HEAD_TOKEN = re.compile(r"(\s*,?\s*)\b(IH\d+)=[\w-]+")


def strip_dead_head_tokens(value: object, live: set[str]) -> object:
    """Drop `IHn=Aspect` tokens for heads not in `live`, with their separator."""
    if not isinstance(value, str):
        return value

    def repl(m: re.Match[str]) -> str:
        return m.group(0) if m.group(2) in live else ""

    out = _HEAD_TOKEN.sub(repl, value)
    return out.lstrip(" ,") if out != value else value


def drop_dead_heads(ws: Worksheet, live: set[str]) -> int:
    """Remove heads tables.xml no longer defines from one as-built sheet.

    Aspect cells lose the dead head's token. In mqtt_topics the dead head's row goes,
    and when that leaves its mast one head, the survivor loses its Top/Bottom tag."""
    n = 0
    for row in ws.iter_rows():
        for cell in row:
            new = strip_dead_head_tokens(cell.value, live)
            if new != cell.value:
                cell.value = new
                n += 1
    if ws.title != "mqtt_topics":
        return n
    idx = header_index(ws)
    jmri_col, name_col, role_col = idx.get("JMRI"), idx.get("Name"), idx.get("Digicon_Block_or_Role")
    if not (jmri_col and name_col and role_col):
        return n
    emptied: set[str] = set()
    for row in range(ws.max_row, 1, -1):
        head = ws.cell(row, jmri_col).value
        if isinstance(head, str) and re.fullmatch(r"IH\d+", head) and head not in live:
            emptied.add(ws.cell(row, role_col).value)
            ws.delete_rows(row)
            n += 1
    for mast in emptied:
        rows = [r for r in range(2, ws.max_row + 1) if ws.cell(r, role_col).value == mast]
        if len(rows) == 1:
            name = ws.cell(rows[0], name_col).value
            for tag in (" Top", " Bottom"):
                if isinstance(name, str) and name.endswith(tag):
                    ws.cell(rows[0], name_col).value = name[: -len(tag)]
                    n += 1
    return n

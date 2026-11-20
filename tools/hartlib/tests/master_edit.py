"""Test helper: change a copy of devices.csv through hartlib.devices (its loader and writer), never by text.

    from master_edit import add, change, drop, find
    change(path, ("2", "turnout", "Switch 101"), jmri_name="IT:HART:C3:999")   # one row's columns
    add(path, level="2", layer="turnout", user_name="Switch 998", ...)         # a row of blanks plus these columns
    drop(path, ("2", "turnout", "Switch 103"))

A row is named by (level, layer, user_name). Every helper loads the file (so it must be a valid master), changes the
rows and writes it back as devices.master_text does, so the result is the master's own format. A name no row has
fails the test at once (AssertionError), rather than changing nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import devices  # noqa: E402


def _rows(path: Path) -> list[dict]:
    return [dict(r) for r in devices.load(path)]


def find(rows: list[dict], key: tuple[str, str, str]) -> dict:
    hit = [r for r in rows if (r["level"], r["layer"], r["user_name"]) == key]
    assert len(hit) == 1, f"{key}: {len(hit)} rows in the master, expected one"
    return hit[0]


def _write(path: Path, rows: list[dict]) -> None:
    rows.sort(key=devices._rank)      # the master's own order, which check_rows holds it to
    path.write_text(devices.master_text(rows), encoding="utf-8")


def change(path: Path, key: tuple[str, str, str], **columns: str) -> None:
    rows = _rows(path)
    row = find(rows, key)
    unknown = set(columns) - set(devices.COLUMNS)
    assert not unknown, f"not master columns: {sorted(unknown)}"
    row.update(columns)
    _write(path, rows)


def add(path: Path, **columns: str) -> None:
    rows = _rows(path)
    row = {c: "" for c in devices.COLUMNS}
    row.update({"assignment": "virtual", "description": "A row the test added."})
    unknown = set(columns) - set(devices.COLUMNS)
    assert not unknown, f"not master columns: {sorted(unknown)}"
    row.update(columns)
    rows.append(row)
    _write(path, rows)


def drop(path: Path, key: tuple[str, str, str]) -> None:
    rows = _rows(path)
    rows.remove(find(rows, key))
    _write(path, rows)

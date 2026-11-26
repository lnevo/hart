"""Test helper: change a one-file copy of the master (devices.one_file_copy) through hartlib.devices, never by text.

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
    devices._read.cache_clear()       # (the cache is keyed on the bytes, so this is belt and braces)


def change(path: Path, key: tuple[str, str, str], **columns: str) -> None:
    """Change one row's columns. On a pair (a devices_generated.csv with its devices_field.csv) a column the key's
    field row gives is changed there, as the owner would; any other in the generated file."""
    if Path(path).name == devices.GENERATED_FILE:
        files = devices.Files.of(path)
        field = [dict(r) for r in devices.field_rows(files)]
        gen = [dict(r) for r in devices.generated_rows(files)]
        f = next((r for r in field if devices.name_key(r) == key), None)
        g = find(gen, key)
        for c, v in columns.items():
            (f if f is not None and c in devices.FIELD_COLUMNS and f[c] else g)[c] = v
        files.field.write_text(devices.master_text(field), encoding="utf-8")
        files.master.write_text(devices.master_text(gen), encoding="utf-8")
        devices.load(files)               # the edited pair must still merge
        return
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
    if row["level"] and "id" not in columns:        # check_rows wants one on every row with a level
        row["id"] = f"test:{row['layer']}:{row['user_name']}"
    rows.append(row)
    _write(path, rows)


def drop(path: Path, key: tuple[str, str, str]) -> None:
    rows = _rows(path)
    rows.remove(find(rows, key))
    _write(path, rows)


def name_store(path: Path, names: dict[str, str]) -> Path:
    """Write a one-file master at `path` (devices.ONE_FILE beside a fixture's switches.csv) holding a level 1 block
    for each {id: user name} of `names`: the name store a fixture's staging rows are read against."""
    blank = {c: "" for c in devices.COLUMNS}
    rows = [blank | dict(level="1", layer="block", role="os" if i.startswith("os:") else "track", id=i, user_name=n,
                         assignment="none", description=f"Block {n}.") for i, n in names.items()]
    _write(Path(path), rows)
    return Path(path)

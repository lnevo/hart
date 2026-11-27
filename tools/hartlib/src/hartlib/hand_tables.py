"""The railroad's names, as the data masters hold them, and the list of tables in code that hold railroad data
(tools/audit/hand_tables.csv): the two inputs of tools/audit/check_hand_tables.py.

    from hartlib import hand_tables
    hand_tables.railroad_names()        # {name or id: "kind (master file)"} from every CSV master in entities.csv
    hand_tables.read_listed(path)       # {(file, table): Listed} from hand_tables.csv, each row checked
    hand_tables.write_listed(path, rows)

The owner's rule (2026-11-26): anything kept by hand goes in a CSV read through hartlib. A table in code whose
entries are the railroad's own names (blocks, switches, stations, industries, trains, locos, roads) is a copy of a
master or a fact with no master, so it is listed in hand_tables.csv until it moves to a CSV.

railroad_names reads docs/data/entities.csv and, for every kind whose master is a CSV, the master's key column and
its NAME_COLUMNS. A new master in entities.csv adds its names with no change here.
"""
from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from . import files, paths
from .errors import HartlibError

ENTITIES = paths.REPO_ROOT / "docs/data/entities.csv"
LISTED = paths.REPO_ROOT / "tools/audit/hand_tables.csv"

# the columns of a master that hold a name a person types (beside the kind's key column)
NAME_COLUMNS = ("name", "public_name", "station", "interlocking", "user_name", "train_name", "opspro_name",
                "road_name", "reporting_marks", "mast", "switch", "Industry")
# a value too short or too plain to say "railroad" on its own: one or two characters, or a number under 100
PLAIN = re.compile(r".{0,2}|\d{1,2}")

LISTED_COLUMNS = ["file", "table", "entries", "status", "reason"]
# move: railroad data, moves to a CSV (wave 4); unreviewed: the check's rule cannot tell, the owner decides once;
# keep: reviewed and stays in code, the reason says why
STATUSES = ("move", "unreviewed", "keep")


class HandTablesError(HartlibError, ValueError):
    """entities.csv, a master or hand_tables.csv cannot be read or is not in its shape; the message names the file
    and line."""


@dataclass(frozen=True)
class Listed:
    file: str
    table: str
    entries: int
    status: str
    reason: str


def _rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise HandTablesError(f"{path}: cannot be read ({exc})") from None


def masters(entities: Path = ENTITIES, root: Path = paths.REPO_ROOT) -> list[tuple[str, str, Path]]:
    """(kind, key column, master path) of every kind in entities.csv whose master is a CSV file in the repo. The
    key cell may name several columns ("industry_id + spot number"); each word that is a column counts."""
    cols, rows = _rows(entities)
    if not {"kind", "key", "master"} <= set(cols):
        raise HandTablesError(f"{entities}: no kind, key and master columns")
    out = []
    for row in rows:
        master = (row["master"] or "").split(" ")[0]
        path = root / master
        if master.endswith(".csv") and path.is_file():
            out.append((row["kind"], row["key"] or "", path))
    return out


def railroad_names(entities: Path = ENTITIES, root: Path = paths.REPO_ROOT) -> dict[str, str]:
    """{name or id: "kind (master)"} of every value in a CSV master's key column and NAME_COLUMNS, PLAIN values
    left out. A cell holding several items (`;` between them) gives each."""
    out: dict[str, str] = {}
    for kind, key, path in masters(entities, root):
        cols, rows = _rows(path)
        keys = [c for c in cols if c in NAME_COLUMNS or re.search(rf"(?<!\w){re.escape(c)}(?!\w)", key)]
        rel = path.relative_to(root).as_posix()
        for row in rows:
            for col in keys:
                for value in (row.get(col) or "").split(";"):
                    value = value.strip()
                    if value and not PLAIN.fullmatch(value):
                        out.setdefault(value, f"{kind} ({rel})")
    return out


def master_files(entities: Path = ENTITIES) -> list[str]:
    """The repo paths railroad_names reads: entities.csv and the CSV masters."""
    return [ENTITIES.relative_to(paths.REPO_ROOT).as_posix()] + sorted(
        p.relative_to(paths.REPO_ROOT).as_posix() for _, _, p in masters(entities))


def read_listed(path: Path = LISTED) -> dict[tuple[str, str], Listed]:
    """The rows of hand_tables.csv by (file, table). Each row has every LISTED_COLUMNS cell, a whole `entries`, a
    STATUSES status and a reason; a (file, table) pair appears once."""
    cols, rows = _rows(path)
    if cols != LISTED_COLUMNS:
        raise HandTablesError(f"{path}: columns are {','.join(cols)}, not {','.join(LISTED_COLUMNS)}")
    out: dict[tuple[str, str], Listed] = {}
    for n, row in enumerate(rows, 2):
        where = f"{path}:{n}"
        cells = {c: (row.get(c) or "").strip() for c in LISTED_COLUMNS}
        if not cells["file"] or not cells["table"]:
            raise HandTablesError(f"{where}: file and table are needed")
        if not cells["entries"].isdigit():
            raise HandTablesError(f"{where}: entries {cells['entries']!r} is not a whole number")
        if cells["status"] not in STATUSES:
            raise HandTablesError(f"{where}: status {cells['status']!r} is not one of {', '.join(STATUSES)}")
        if not cells["reason"]:
            raise HandTablesError(f"{where}: a reason is needed")
        key = (cells["file"], cells["table"])
        if key in out:
            raise HandTablesError(f"{where}: {key[0]} {key[1]} is listed twice")
        out[key] = Listed(cells["file"], cells["table"], int(cells["entries"]), cells["status"], cells["reason"])
    return out


def write_listed(path: Path, rows: Iterable[Listed]) -> None:
    """Write hand_tables.csv sorted by file and table (an atomic write)."""
    lines = [",".join(LISTED_COLUMNS)]
    for r in sorted(rows, key=lambda r: (r.file, r.table)):
        cells = [r.file, r.table, str(r.entries), r.status, r.reason]
        lines.append(",".join(f'"{c}"' if any(ch in c for ch in ',"\n') else c for c in
                              (c.replace('"', '""') for c in cells)))
    files.write_atomic(path, "\n".join(lines) + "\n")

"""devices.csv: the one device master for all three levels, and the three older files generated from it.

jmri/layouts/hart/data/devices.csv holds one row per railroad device (ADR-029). Staging, main and upper are one
structure; a level differs only in column values. devices.columns.csv describes every column (column, description),
and a test holds the two files to each other both ways. Until their readers move over (R9b-2), three files are
generated from the master and must match it byte for byte:

    schematic/device_map_staging.csv      the rows of level 1
    schematic/device_map_main_upper.csv   the rows of levels 2 and 3
    public_name_map.csv                   the rows that carry pnm_order, in that order (the alias rows and the
                                          retired identity rows of the old file are gone)

The master's values.
- level 1 staging, 2 main, 3 upper. layer: turnout, fb, block, occupancy, mast, head, sensor.
- assignment: field (the physical device is in JMRI: jmri_name is system_name), virtual (an internal stand-in; the
  system_name, if any, is the planned device), none (no JMRI name from this row), spare (a detector with no block).
- role: what the device is (ROLES). Readers test it, never a name prefix.
- written_by: the script that writes the row, one of WRITERS (the one place a later merge of builders changes);
  empty is hand-kept. A writer replaces only the rows that carry its name (replace_rows), and stops on a key
  another writer or the owner holds.

Row order is level, layer (LAYERS), then who holds the row (hand-kept first, then WRITERS order), then the order the
holder gave, so a rebuild changes only its own rows and `check` can hold the file to it. Block and mast numbers
that le_tables.block_sort and block_numbering.csv set are not touched here.

    python3 -m hartlib.devices check         # the master and its dictionary are valid and the three files match
    python3 -m hartlib.devices regenerate    # write the three files from the master

Every failure is a DevicesError (a FactsError) naming the file and row.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

from . import names, paths
from .railroad_facts import DEVICE_COLUMNS, FactsError

LEVELS = ("1", "2", "3")
LAYERS = ("turnout", "fb", "block", "occupancy", "mast", "head", "sensor")   # also the order within a level
ASSIGNMENTS = ("field", "virtual", "none", "spare")
ROLES = ("turnout", "lcc_alias", "fb", "os", "xover_corner", "track", "spur", "loop_half", "helix",
         "home", "intermediate", "hidden", "head", "spare", "panel_status")
# The scripts that write rows (the one list: a merge of builders changes only this). Order is the order of rows
# within a (level, layer) after the hand-kept ones.
WRITERS = ("build_staging_masts.py", "build_device_map.py", "build_main_upper_masts.py", "panel_items.json")
OUT_OF_MAPS = ("spare", "panel_status")        # roles the two device maps leave out
SOURCE_PREFIXES = ("IT:HART:", "IS:HART:", "IH:HART:", "IB:HART:")

COLUMNS = ("level", "cp", "layer", "role", "user_name", "assignment", "system_name", "jmri_name", "node", "dcc",
           "wiring", "jmri_comment", "trial_name", "notes", "blocks", "detector", "stop", "switch", "facing",
           "protects", "dir", "written_by", "description",
           "pnm_order", "pnm_cp", "pnm_hardware", "pnm_dcc", "pnm_comment", "pnm_notes")
PNM_COLUMNS = ("layer", "current", "proposed", "cp", "hardware", "dcc", "comment", "notes")
# the columns a device map shares with the master, and the three that are built (comment) or dropped (the rest)
_SHARED = tuple(c for c in DEVICE_COLUMNS if c not in ("comment",))

_NODE_TEXT = re.compile(r"Node: \d+")
_WIRED_HEAD = re.compile(r"\(IH\d+\)")


class DevicesError(FactsError):
    """The master or its dictionary cannot stand as it is, or a write would break it."""


@dataclass(frozen=True)
class Files:
    """The files the master and the three generated files live in; tests point them at a copy."""
    master: Path
    dictionary: Path
    staging: Path
    main_upper: Path
    name_map: Path

    @staticmethod
    def under(data: Path) -> "Files":
        """The files as they sit under a data folder (jmri/layouts/hart/data): one root, so a test or a script that
        points it elsewhere moves every file together and cannot write the repo's."""
        return Files(data / "devices.csv", data / "devices.columns.csv", data / "schematic" / "device_map_staging.csv",
                     data / "schematic" / "device_map_main_upper.csv", data / "public_name_map.csv")

    @staticmethod
    def here() -> "Files":
        return Files.under(paths.LAYOUT_DATA)

    def but(self, **changes) -> "Files":
        return replace(self, **changes)

    def generated(self) -> tuple[Path, ...]:
        return self.staging, self.main_upper, self.name_map


# ---------------------------------------------------------------- reading

@lru_cache(maxsize=8)
def _read(path: Path, mtime_ns: int, size: int) -> tuple[Mapping[str, str], ...]:
    try:
        fh = path.open(newline="", encoding="utf-8")
    except OSError as exc:
        raise DevicesError(f"{path}: cannot read it ({exc.strerror})") from None
    with fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header is None or tuple(header) != COLUMNS:
            raise DevicesError(f"{path.name}: the header is not the master's columns "
                               f"({', '.join(COLUMNS)}); got {header}")
        rows = []
        for line, fields in enumerate(reader, 2):
            if len(fields) != len(COLUMNS):
                raise DevicesError(f"{path.name} line {line}: {len(fields)} fields, expected {len(COLUMNS)}")
            rows.append(MappingProxyType(dict(zip(COLUMNS, fields))))
    return tuple(rows)


def load(files: Files | None = None) -> tuple[Mapping[str, str], ...]:
    """The master's rows (read-only mappings), checked (check_rows). Read once per file state: the parse is cached on
    the file's mtime and size, so every reader of one run shares it. DevicesError on any problem."""
    path = (files or Files.here()).master
    try:
        st = path.stat()
    except OSError as exc:
        raise DevicesError(f"{path}: cannot read it ({exc.strerror})") from None
    rows = _read(path, st.st_mtime_ns, st.st_size)
    check_rows(rows, path.name)
    return rows


def read_dictionary(path: Path) -> dict[str, str]:
    """{column: description} of devices.columns.csv; DevicesError unless it is exactly the columns `column,description`
    with every master column once, and each described."""
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
    except OSError as exc:
        raise DevicesError(f"{path}: cannot read it ({exc.strerror})") from None
    if not rows or rows[0] != ["column", "description"]:
        raise DevicesError(f"{path.name}: the header is column,description")
    out, bad = {}, []
    for line, r in enumerate(rows[1:], 2):
        if len(r) != 2:
            bad.append(f"line {line}: {len(r)} fields, expected 2")
        elif r[0] in out:
            bad.append(f"line {line}: {r[0]} is described twice")
        elif not r[1].strip():
            bad.append(f"line {line}: {r[0]} has no description")
        else:
            out[r[0]] = r[1]
    bad += [f"{c} is a master column with no description" for c in COLUMNS if c not in out]
    bad += [f"{c} is described but is no master column" for c in out if c not in COLUMNS]
    if bad:
        raise DevicesError(f"{path.name}: " + "; ".join(bad))
    return out


# ---------------------------------------------------------------- the checks

def _rank(row: Mapping[str, str]) -> tuple[int, int, int]:
    writer = row["written_by"]
    return (LEVELS.index(row["level"]), LAYERS.index(row["layer"]), 0 if not writer else 1 + WRITERS.index(writer))


def check_rows(rows: Iterable[Mapping[str, str]], where: str = "devices.csv") -> None:
    """The master's invariants; DevicesError listing every problem (a row is named by its line, level, layer and
    name). Run on every load and after every write."""
    bad, keys, jmri, field_systems = [], {}, {}, {}
    ranks, pnm = [], {}
    for n, r in enumerate(rows, 2):
        at = f"line {n} ({r['level']} {r['layer']} {r['user_name']!r})"
        if r["level"] not in LEVELS:
            bad.append(f"{at}: level is one of {', '.join(LEVELS)}")
            continue
        if r["layer"] not in LAYERS:
            bad.append(f"{at}: layer is one of {', '.join(LAYERS)}")
            continue
        unknown = False
        for col, allowed in (("role", ROLES), ("assignment", ASSIGNMENTS), ("written_by", ("",) + WRITERS)):
            if r[col] not in allowed:
                bad.append(f"{at}: {col} {r[col]!r} is not one of {', '.join(a or 'empty' for a in allowed)}")
                unknown = unknown or col == "written_by"
        for col in ("user_name", "description"):
            if not r[col].strip():
                bad.append(f"{at}: {col} is empty")
        key = (r["level"], r["layer"], r["user_name"])
        if key in keys:
            bad.append(f"{at}: the same level, layer and user_name as line {keys[key]}")
        keys[key] = n
        jn = r["jmri_name"]
        if jn:
            # a virtual turnout and its LCC alias both stand on one internal turnout, so the role is part of the key
            jk = (r["layer"], r["role"] == "lcc_alias", jn)
            if jk in jmri:
                bad.append(f"{at}: jmri_name {jn!r} is line {jmri[jk]}'s as well")
            jmri[jk] = n
        a = r["assignment"]
        if a == "field":
            if not r["system_name"] or not jn:
                bad.append(f"{at}: a field device needs a system_name and a jmri_name")
            elif r["system_name"] != jn and not (r["role"] == "turnout" and jn == r["user_name"]):
                # a staging turnout the tables and panels bind by its user name (staging_device_map.py): the one exception
                bad.append(f"{at}: field, but system_name {r['system_name']!r} is not jmri_name {jn!r}")
            if r["system_name"]:
                if r["system_name"] in field_systems.get(r["layer"], {}):
                    bad.append(f"{at}: field system_name {r['system_name']!r} is line "
                               f"{field_systems[r['layer']][r['system_name']]}'s as well")
                field_systems.setdefault(r["layer"], {})[r["system_name"]] = n
        elif a == "virtual" and not jn:
            bad.append(f"{at}: a virtual device needs a jmri_name")
        elif a == "none" and jn:
            bad.append(f"{at}: assignment none, but jmri_name is {jn!r}")
        if (a == "spare") != (r["role"] == "spare"):
            bad.append(f"{at}: assignment spare and role spare go together")
        if a == "spare" and not (r["system_name"] and r["system_name"] == jn):
            bad.append(f"{at}: a spare detector has its M2S name as system_name and jmri_name")
        if (r["role"] == "panel_status") != (r["written_by"] == "panel_items.json"):
            bad.append(f"{at}: role panel_status and written_by panel_items.json go together")
        if r["wiring"] and r["jmri_comment"]:
            bad.append(f"{at}: wiring and jmri_comment are both set; a row has one comment")
        pnms = [r[c] for c in COLUMNS if c.startswith("pnm_")]
        if r["pnm_order"]:
            order = int(r["pnm_order"]) if r["pnm_order"].isdigit() else None
            if order is None or order in pnm:
                bad.append(f"{at}: pnm_order {r['pnm_order']!r} is not a number of its own")
            pnm[order] = n
        elif any(pnms):
            bad.append(f"{at}: pnm_ columns are set but pnm_order is empty")
        if not unknown:
            ranks.append((_rank(r), n))
    for (a, na), (b, nb) in zip(ranks, ranks[1:]):
        if b < a:
            bad.append(f"line {nb}: out of order (level, layer, then hand-kept rows before each writer's, "
                       f"in WRITERS order); it follows line {na}")
            break
    if bad:
        raise DevicesError(f"{where}: " + "; ".join(bad))


# ---------------------------------------------------------------- roles, assignments, descriptions

def block_role(name: str) -> str:
    """The role of a block or its occupancy row from its name ("OS Switch 7", "BS Switch 225b", "Track 101 Spur 1",
    "Track Helix Inner", "BS 107 Loop 2")."""
    if re.fullmatch(r"(?:OS|BS) Switch \d+[a-d]", name):
        return "xover_corner"
    if re.fullmatch(r"(?:OS|BS) Switch \d+", name):
        return "os"
    if "Helix" in name:
        return "helix"
    if re.search(r" Spur(?: \d+)?$", name):
        return "spur"
    if re.search(r" Loop(?: \d+)?$", name):
        return "loop_half"
    return "track"


def role_of(layer: str, user_name: str, system_name: str, jmri_name: str) -> str:
    """The role a device-map row gets: DevicesError on a layer a device map does not hold."""
    if layer == "turnout":
        return "lcc_alias" if user_name.startswith("DCC Switch ") else "turnout"
    if layer == "fb":
        return "fb"
    if layer in ("block", "occupancy"):
        return block_role(user_name)
    if layer == "head":
        return "head"
    if layer == "mast":
        if (jmri_name or system_name).startswith("IF$vsm"):
            return "hidden"
        return "intermediate" if re.fullmatch(r"Mast [AB]?\d+", user_name) else "home"
    raise DevicesError(f"layer {layer!r}: a device map has no {layer} rows")


def assignment_of(jmri_name: str) -> str:
    """How a device-map row is in JMRI: none without a jmri_name, virtual for an internal name (IT/IS/IH/IB:HART:, a
    hidden mast, a mast over internal heads), else field."""
    if not jmri_name:
        return "none"
    if jmri_name.startswith(SOURCE_PREFIXES) or jmri_name.startswith("IF$vsm"):
        return "virtual"
    if jmri_name.startswith("IF$shsm") and not _WIRED_HEAD.search(jmri_name):
        return "virtual"
    return "field"


def describe(r: Mapping[str, str]) -> str:
    """One plain sentence for a row from its columns; DevicesError on a role it has no sentence for. Writers call this
    for the rows they write; a hand-kept row's sentence is kept as given."""
    u, role, node = r["user_name"], r["role"], r["node"]
    on = f" on LCOS node {node}" if node else ""
    at = f" at {r['cp']}" if r["cp"] else ""
    live = "wired in JMRI" if r["assignment"] == "field" else "a virtual stand-in until the plant is wired"
    if role == "turnout":
        return f"Turnout {u}{at}, {live}{on}."
    if role == "lcc_alias":
        return f"LCC alias {u} of the turnout with the same number, DCC address {r['dcc'] or 'not set'}."
    if role == "fb":
        return f"Feedback sensor {u}: reports one position of its turnout{on}."
    if role == "os":
        return f"Block {u}: the track through the points of its switch."
    if role == "xover_corner":
        return f"Block {u}: one corner of a double crossover."
    if role == "track":
        return f"Track block {u}."
    if role == "spur":
        return f"Block {u}: a spur that ends at a buffer stop."
    if role == "loop_half":
        return f"Block {u}: one half of a balloon loop."
    if role == "helix":
        return f"Block {u}: a helix track, one block for its whole length."
    if role == "home":
        return f"Signal mast {u} at a switch, facing {r['facing'] or 'its track'}."
    if role == "intermediate":
        return f"Intermediate signal mast {u} between two blocks, facing {r['facing'] or 'its track'}."
    if role == "hidden":
        return f"Hidden routing mast {u}, facing {r['facing'] or 'its track'}; it shows no signal on the panel."
    if role == "head":
        return f"Signal head {u} of {'Mast ' + u.removeprefix('Head ').split(' ')[0]}, {live}."
    if role == "spare":
        return f"Spare detector {u}: a field detector with no block assigned."
    raise DevicesError(f"no description rule for role {role!r} ({u})")


# ---------------------------------------------------------------- device-map rows and master rows

def _carries_dcc(r: Mapping[str, str]) -> bool:
    return r["role"] == "turnout" and r["assignment"] == "field"


def device_map_row(r: Mapping[str, str]) -> dict[str, str]:
    """The old-form device-map row of a master row: comment is jmri_comment, else wiring, with the DCC group put in
    as the JMRI comment has it for a field turnout (hartlib.names.jmri_comment)."""
    comment = r["jmri_comment"] or (names.jmri_comment(r["wiring"], r["dcc"]) if _carries_dcc(r) else r["wiring"])
    return {c: (comment if c == "comment" else r[c]) for c in DEVICE_COLUMNS}


def master_row(old: Mapping[str, str], writer: str, prior: Mapping[str, str] | None = None,
               description: str | None = None) -> dict[str, str]:
    """The master row of an old-form device-map row. `prior` is the row it replaces, whose pnm_ columns (and, for a
    hand-kept row, description) it keeps. DevicesError when the comment cannot be split back by device_map_row."""
    if not set(DEVICE_COLUMNS) <= set(old):
        raise DevicesError(f"device-map row {old.get('user_name')!r} misses columns "
                           f"{sorted(set(DEVICE_COLUMNS) - set(old))}")
    r = {c: "" for c in COLUMNS}
    r.update({c: str(old[c]) for c in _SHARED})
    r["role"] = role_of(old["layer"], old["user_name"], old["system_name"], old["jmri_name"])
    r["assignment"] = assignment_of(old["jmri_name"])
    r["written_by"] = writer
    comment = old["comment"]
    if _NODE_TEXT.match(comment):
        r["wiring"] = names.split_dcc(comment)[0] if _carries_dcc(r) else comment
    else:
        r["jmri_comment"] = comment
    if prior:
        r.update({c: prior[c] for c in COLUMNS if c.startswith("pnm_")})
    r["description"] = description or (prior["description"] if prior and not writer else "") or describe(r)
    if device_map_row(r) != {c: str(old[c]) for c in DEVICE_COLUMNS}:
        raise DevicesError(f"{r['level']} {r['layer']} {r['user_name']}: the comment {comment!r} does not survive "
                           f"the split into wiring, dcc and jmri_comment")
    return r


# ---------------------------------------------------------------- writing

def replace_rows(rows: Iterable[Mapping[str, str]], writer: str, new: Iterable[Mapping[str, str]]
                 ) -> list[dict[str, str]]:
    """`rows` with the rows `writer` holds replaced by `new` (master rows with written_by == writer), sorted into the
    master's order (stable). DevicesError when the writer is not in WRITERS, a new row names another writer or
    would take a key (level, layer, user_name) a row held by someone else has, or the result breaks check_rows."""
    if writer not in WRITERS:
        raise DevicesError(f"writer {writer!r} is not one of {', '.join(WRITERS)}")
    rows, new = [dict(r) for r in rows], [dict(r) for r in new]
    foreign = [r for r in new if r["written_by"] != writer]
    if foreign:
        raise DevicesError(f"{writer} would write {len(foreign)} row(s) held by someone else, first "
                           f"{foreign[0]['level']} {foreign[0]['layer']} {foreign[0]['user_name']!r} "
                           f"(written_by {foreign[0]['written_by']!r})")
    others = {(r["level"], r["layer"], r["user_name"]): r["written_by"] for r in rows if r["written_by"] != writer}
    clash = [k for k in ((r["level"], r["layer"], r["user_name"]) for r in new) if k in others]
    if clash:
        raise DevicesError(f"{writer} would rewrite row(s) it does not hold: "
                           + ", ".join(f"{k[2]!r} ({k[1]}, level {k[0]}; held by {others[k] or 'hand'})" for k in clash[:5]))
    out = [r for r in rows if r["written_by"] != writer] + new
    out.sort(key=_rank)
    check_rows(out, "devices.csv after the write")
    return out


def _text(columns: Iterable[str], rows: Iterable[Mapping[str, str]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def master_text(rows: Iterable[Mapping[str, str]]) -> str:
    return _text(COLUMNS, rows)


def device_map_rows(rows: Iterable[Mapping[str, str]], levels: tuple[str, ...]) -> list[dict[str, str]]:
    """The old-form rows of a device map: those of `levels` outside OUT_OF_MAPS, in master order."""
    return [device_map_row(r) for r in rows if r["level"] in levels and r["role"] not in OUT_OF_MAPS]


def device_map_text(rows: Iterable[Mapping[str, str]], levels: tuple[str, ...]) -> str:
    """The text of a device map (device_map_rows)."""
    return _text(DEVICE_COLUMNS, device_map_rows(rows, levels))


def name_map_text(rows: Iterable[Mapping[str, str]]) -> str:
    """The text of public_name_map.csv: one identity row per master row that has a pnm_order, in that order."""
    kept = sorted((r for r in rows if r["pnm_order"]), key=lambda r: int(r["pnm_order"]))
    return _text(PNM_COLUMNS, ({"layer": r["layer"], "current": r["user_name"], "proposed": r["user_name"],
                                "cp": r["pnm_cp"], "hardware": r["pnm_hardware"], "dcc": r["pnm_dcc"],
                                "comment": r["pnm_comment"], "notes": r["pnm_notes"]} for r in kept))


def texts(rows: list[Mapping[str, str]], files: Files | None = None) -> dict[Path, str]:
    """{path: text} of the master and the three files generated from `rows`."""
    f = files or Files.here()
    return {f.master: master_text(rows), f.staging: device_map_text(rows, ("1",)),
            f.main_upper: device_map_text(rows, ("2", "3")), f.name_map: name_map_text(rows)}


def outputs_after_rows(writer: str, new: Iterable[Mapping[str, str]], files: Files | None = None
                       ) -> dict[Path, str]:
    """{path: text} of the master and the three generated files once `writer` has written `new`, master rows with
    written_by set to it, in place of the rows it holds. Each row keeps the pnm_ columns of the row it replaces.
    The caller writes the texts (or compares them for --check); nothing is written here. DevicesError when the
    writer would touch a row it does not hold."""
    f = files or Files.here()
    held = load(f)
    prior = {(r["level"], r["layer"], r["user_name"]): r for r in held}
    rows = []
    for n in new:
        row = dict(n)
        old = prior.get((row["level"], row["layer"], row["user_name"]))
        if old is not None and old["written_by"] == writer:
            row.update({c: old[c] for c in COLUMNS if c.startswith("pnm_")})
        rows.append(row)
    return texts(replace_rows(held, writer, rows), f)


def outputs_after(writer: str, old_rows: Iterable[Mapping[str, str]], files: Files | None = None
                  ) -> dict[Path, str]:
    """outputs_after_rows for `old_rows`, old-form device-map rows (master_row gives each its master form). What a
    reader of the generated file sees for these rows is what the writer gave; DevicesError when it is not."""
    f = files or Files.here()
    old_rows = list(old_rows)
    prior = {(r["level"], r["layer"], r["user_name"]): r for r in load(f)}
    new = [master_row(o, writer, prior.get((str(o["level"]), o["layer"], o["user_name"]))) for o in old_rows]
    out = outputs_after_rows(writer, new, f)
    want = {(str(o["level"]), o["layer"], o["user_name"]): {c: str(o[c]) for c in DEVICE_COLUMNS} for o in old_rows}
    held = {(r["level"], r["layer"], r["user_name"]): device_map_row(r)
            for r in csv.DictReader(io.StringIO(out[f.master])) if r["written_by"] == writer}
    if held != want:
        raise DevicesError(f"{writer}: the rows written do not read back as given")
    return out


@dataclass(frozen=True)
class PnmUpdate:
    texts: dict
    changed: int


def set_pnm_comments(layer: str, comments: Mapping[str, str], files: Files | None = None) -> PnmUpdate:
    """The master and generated files' texts once the `pnm_comment` of each `layer` row in the name map whose user
    name is in `comments` is the one given, and how many rows changed. Only hand-kept rows may change: a row a script
    writes raises DevicesError naming that writer, since it would rewrite the column on its next run."""
    f = files or Files.here()
    rows, changed = [dict(r) for r in load(f)], 0
    for r in rows:
        want = comments.get(r["user_name"])
        if r["layer"] != layer or not r["pnm_order"] or not want or r["pnm_comment"] == want:
            continue
        if r["written_by"]:
            raise DevicesError(f"{layer} {r['user_name']!r}: pnm_comment is held by {r['written_by']}; change it there")
        r["pnm_comment"] = want
        changed += 1
    check_rows(rows, "devices.csv after the comment update")
    return PnmUpdate(texts(rows, f) if changed else {}, changed)


def stale_message(path: Path, files: Files, script: str) -> str:
    """What a --check says of a stale `path`: the writer to run, and for a generated file the command that rewrites it
    from the master when the master itself is right."""
    if path in files.generated():
        return (f"{path.name} is stale: run python3 {script}, or, when only this generated file differs, "
                f"python3 -m hartlib.devices regenerate")
    return f"{path.name} is stale: run python3 {script}"


def write_all(files: Files, content: Mapping[Path, str]) -> list[Path]:
    """Write the changed ones of `content`; the paths written."""
    done = []
    for p, text in content.items():
        if not p.exists() or p.read_text(encoding="utf-8") != text:
            p.write_text(text, encoding="utf-8")
            done.append(p)
    return done


# ---------------------------------------------------------------- the check

def stale(files: Files | None = None) -> list[str]:
    """What is wrong with the generated files: [] when the master and its dictionary check and the three files are
    what the master generates."""
    f = files or Files.here()
    rows = load(f)
    read_dictionary(f.dictionary)
    out = []
    for path, text in texts(list(rows), f).items():
        if path == f.master:
            continue
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            out.append(f"{path.name} is not what devices.csv generates: run python3 -m hartlib.devices regenerate")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m hartlib.devices", description=__doc__.split("\n")[0])
    ap.add_argument("action", choices=("check", "regenerate"))
    args = ap.parse_args(argv)
    f = Files.here()
    try:
        if args.action == "check":
            problems = stale(f)
            for p in problems:
                print(p, file=sys.stderr)
            if not problems:
                print(f"devices.csv: {len(load(f))} rows; its dictionary and the three generated files agree")
            return 1 if problems else 0
        rows = list(load(f))
        read_dictionary(f.dictionary)
        for p in write_all(f, {k: v for k, v in texts(rows, f).items() if k != f.master}):
            print(f"wrote {p.name}")
        return 0
    except DevicesError as exc:
        print(f"devices.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

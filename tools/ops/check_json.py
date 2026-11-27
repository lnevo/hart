#!/usr/bin/env python3
"""Check the hand-kept JSON files that builds read against a schema each (ADR-039, decision 3; docs/data/sidecars.md).

A column sidecar describes a CSV; these files are nested JSON, so each has a schema here instead (SCHEMAS). A schema
states only what the readers depend on: the keys they need, the types they take and the values they allow. Each
reader still makes its own deeper checks (an XML snippet that parses, a track ID the name store has).

    jmri/layouts/hart/data/schematic/plan_overrides.json   hartlib.layer_files, plan_bands.band_places, track_names,
                                                           build_layout_docs.py (staging scale_ratio)
    jmri/layouts/hart/data/schematic/preferences.json      hartlib.layer_files, map_revision (revision, date),
                                                           host_screen.py, track_names.pref_section, build_staging_sets
    jmri/layouts/hart/data/schematic/panel_items.json      hartlib.hand_lists.read_panel_items, panel_items.load
    www/scripts/published-files.json                       portal_common, make_share_cards, serve_portal,
                                                           prepare_github_pages, tools/audit/portal_inputs

A schema node is a dict with a `type`:
  object  keys {name: node}; required (names); other (the node of every key not in keys, or None: none allowed);
          closed (no key outside keys, notes included); key (a node every key must pass); unique (for an array of
          objects: the field no two share). A key starting with _ is a note and goes unchecked unless keys names it
          or the object is closed.
  array   items (the node of each item); prefix (nodes of the first items, in order); min and max (its length).
  str     values (the allowed ones); pattern (a regex the whole value matches); file (yes: a file under the repo root).
  int, number (int or float, never bool), bool, any, const (`value`).
Every node may have `check`: fn(value) -> a problem or None, for a rule between fields.

Each problem names the file and the key path (main_upper.host_screen.size[1]).

    python3 tools/ops/check_json.py              check every file in SCHEMAS (exit 1 on a problem)
    python3 tools/ops/check_json.py PATH ...     check only these files (each must be in SCHEMAS)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import hand_lists, layer_files  # noqa: E402  the layout files' paths are theirs (check_data_readers)
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# A schema node: a dict whose "type" says which other keys it holds (the module docstring lists them).
Schema = dict[str, Any]
# A cross-field rule: the value (already shape-checked against its node, so of the node's type) -> a problem or None.
Rule = Callable[[Any], "str | None"]


# ---------------------------------------------------------------- schema nodes

def obj(keys: dict[str, Schema] | None = None, required: Iterable[str] = (), other: Schema | None = None,
        closed: bool = False, key: Schema | None = None, check: Rule | None = None) -> Schema:
    return {"type": "object", "keys": keys or {}, "required": tuple(required), "other": other, "closed": closed,
            "key": key, "check": check}


def arr(items: Schema | None = None, prefix: Iterable[Schema] = (), min: int = 0, max: int | None = None,  # noqa: A002
        unique: str | None = None, check: Rule | None = None) -> Schema:
    return {"type": "array", "items": items or ANY, "prefix": list(prefix), "min": min, "max": max,
            "unique": unique, "check": check}


def text(values: Iterable[str] | None = None, pattern: str | None = None, file: bool = False, nonempty: bool = False,
         check: Rule | None = None) -> Schema:
    return {"type": "str", "values": tuple(values) if values else None, "pattern": pattern, "file": file,
            "nonempty": nonempty, "check": check}


def whole(lo: int | None = None, hi: int | None = None) -> Schema:
    return {"type": "int", "min": lo, "max": hi}


def number(above: float | None = None, lo: float | None = None) -> Schema:
    return {"type": "number", "above": above, "min": lo}


BOOL: Schema = {"type": "bool"}
ANY: Schema = {"type": "any"}


def const(value: object) -> Schema:
    return {"type": "const", "value": value}


# ---------------------------------------------------------------- the checker

def _step(path: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    k = str(key)
    part = k if IDENT.fullmatch(k) else json.dumps(k)
    return f"{path}.{part}" if path and IDENT.fullmatch(k) else (f"{path}[{part}]" if path else part)


def _kind(v: object) -> str:
    return {dict: "an object", list: "an array", str: "text", bool: "true or false", type(None): "null"}.get(
        type(v), "a number" if isinstance(v, (int, float)) else type(v).__name__)


def _const(value: object, node: dict, path: str, at: str, root: Path) -> list[str]:
    if value != node["value"] or type(value) is not type(node["value"]):
        return [f"{at}: must be {json.dumps(node['value'])}, not {json.dumps(value)}"]
    return []


def _bool(value: object, node: dict, path: str, at: str, root: Path) -> list[str]:
    return [] if isinstance(value, bool) else [f"{at}: must be true or false, not {_kind(value)}"]


def _int(value: object, node: dict, path: str, at: str, root: Path) -> list[str]:
    if isinstance(value, bool) or not isinstance(value, int):
        return [f"{at}: must be a whole number, not {_kind(value)}"]
    lo, hi = node["min"], node["max"]
    if lo is not None and value < lo or hi is not None and value > hi:
        return [f"{at}: {value} is not from {lo} to {hi}" if lo is not None and hi is not None
                else f"{at}: {value} is above {hi}" if hi is not None else f"{at}: {value} is below {lo}"]
    return []


def _number(value: object, node: dict, path: str, at: str, root: Path) -> list[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return [f"{at}: must be a number, not {_kind(value)}"]
    out = []
    if node["above"] is not None and not value > node["above"]:
        out.append(f"{at}: {value} is not above {node['above']}")
    if node["min"] is not None and value < node["min"]:
        out.append(f"{at}: {value} is below {node['min']}")
    return out


def _str(value: object, node: dict, path: str, at: str, root: Path) -> list[str]:
    if not isinstance(value, str):
        return [f"{at}: must be text, not {_kind(value)}"]
    out = []
    if node["nonempty"] and not value.strip():
        out.append(f"{at}: is empty")
    if node["values"] and value not in node["values"]:
        out.append(f"{at}: {value!r} is not one of {', '.join(node['values'])}")
    if node["pattern"] and not re.fullmatch(node["pattern"], value):
        out.append(f"{at}: {value!r} does not match {node['pattern']}")
    if node["file"] and not (root / value).is_file():
        out.append(f"{at}: {value} is not a file in the repo")
    return out


def _array(value: object, node: dict, path: str, at: str, root: Path) -> list[str]:
    if not isinstance(value, list):
        return [f"{at}: must be an array, not {_kind(value)}"]
    out = []
    if len(value) < node["min"] or node["max"] is not None and len(value) > node["max"]:
        want = (f"{node['min']}" if node["max"] == node["min"] else
                f"{node['min']} to {node['max']}" if node["max"] is not None else f"at least {node['min']}")
        out.append(f"{at}: has {len(value)} items, needs {want}")
    for i, item in enumerate(value):
        sub = node["prefix"][i] if i < len(node["prefix"]) else node["items"]
        out += problems(item, sub, _step(path, i), root)
    if node["unique"]:
        seen: set[str] = set()
        for i, item in enumerate(value):
            if isinstance(item, dict) and node["unique"] in item:
                v = json.dumps(item[node["unique"]])
                if v in seen:
                    out.append(f"{_step(path, i)}.{node['unique']}: {v} is given twice")
                seen.add(v)
    return out


def _object(value: object, node: dict, path: str, at: str, root: Path) -> list[str]:
    if not isinstance(value, dict):
        return [f"{at}: must be an object, not {_kind(value)}"]
    out = [f"{_step(path, name)}: is required" for name in node["required"] if name not in value]
    for k, v in value.items():
        if node["key"] is not None:
            out += [f"{_step(path, k)} (the key): {p.split(': ', 1)[1]}"
                    for p in problems(k, node["key"], "x", root)]
        if k in node["keys"]:
            out += problems(v, node["keys"][k], _step(path, k), root)
        elif k.startswith("_") and not node["closed"]:
            continue
        elif node["other"] is not None and not node["closed"]:
            out += problems(v, node["other"], _step(path, k), root)
        else:
            allowed = ", ".join(node["keys"]) or "none"
            out.append(f"{_step(path, k)}: is not a key here (keys: {allowed})")
    return out


# each schema node type -> its shape check: (value, node, path, "at" text, repo root) -> problems
SHAPE_CHECKS: dict[str, Callable[[object, dict, str, str, Path], list[str]]] = {
    "any": lambda value, node, path, at, root: [],
    "const": _const, "bool": _bool, "int": _int, "number": _number, "str": _str, "array": _array, "object": _object,
}


def problems(value: object, node: dict, path: str = "", root: Path = ROOT) -> list[str]:
    """Every problem of `value` against `node`, each "path: what is wrong" ("top level" for the root)."""
    at = path or "top level"
    check = SHAPE_CHECKS.get(node["type"])
    if check is None:
        raise ValueError(f"schema node type {node['type']!r}")
    out = check(value, node, path, at, root)
    # a cross-field rule runs only on a value whose own shape passed (it indexes its keys): fix shape errors first
    if not out and node.get("check"):
        msg = node["check"](value)
        if msg:
            out.append(f"{at}: {msg}")
    return out


# ---------------------------------------------------------------- plan_overrides.json

def _relabel_map(edit: dict) -> str | None:
    if edit.get("op") == "relabel" and not isinstance(edit.get("map"), dict):
        return "a relabel edit needs a map, an object of plan label to switch label"
    return None


PLAN_EDIT = obj({"op": text(nonempty=True), "map": obj(other=text())}, required=("op",), other=ANY,
                check=_relabel_map)
BAND = obj({"name": text(nonempty=True), "level": whole(1, 3), "below": number(above=0)}, required=("name", "level"),
           other=ANY)
PLAN_SECTION_KEYS = {
    "_layer": whole(),
    "edits": arr(PLAN_EDIT),                     # track_names, store_split, build_signals: each edit's op
    "level": whole(1, 3),                         # plan_bands.band_places: a one-band input's level
    "level_title": text(nonempty=True),           # and its band title
    "levels": obj({"bands": arr(BAND, min=1, unique="name"), "assign": obj(other=number())}, other=ANY),
    "helix": obj(other=text(pattern=r"block:.+")),  # {helix junction: its helix track's block ID} (device_map_inputs)
    "mast_prefix": text(),                        # cats_panel, render_le_layout
    "scale_ratio": number(above=0),               # build_layout_docs.car_inches
    "left_end": text(pattern=r"block:.+"),        # track_names: staging's left end, by block ID
}
PLAN_OVERRIDES = obj({
    "_sections": const(True),
    "_note": text(),
    "staging": obj(PLAN_SECTION_KEYS, required=("level", "level_title", "scale_ratio"), other=ANY),
    "main_upper": obj(PLAN_SECTION_KEYS, required=("levels",), other=ANY),
}, required=("_sections", "staging", "main_upper"), other=obj(other=ANY))   # a further sheet is an object


# ---------------------------------------------------------------- preferences.json

def _taskbar_below_height(v: dict) -> str | None:
    return None if v["taskbar"] < v["size"][1] else f"taskbar {v['taskbar']} is not less than the height {v['size'][1]}"


def _no_window_keys(section: dict) -> str | None:
    own = sorted(k for k in ("le_window", "cats_window") if k in section)
    return f"{', '.join(own)} is set from host_screen (host_screen.apply), not by hand" if own else None


MIN_CELLS = arr(prefix=(text(nonempty=True), text(nonempty=True), whole(1)), items=text(pattern=r"block:.+"), min=3)
PREF_SECTION_KEYS = {
    "_layer": whole(),
    "title": arr(text()),
    "min_cells": arr(MIN_CELLS),                  # [from, to, cells, track ID ...] (track_names._map_pref_tracks)
    "turnbacks": arr(text(pattern=r"block:.+")),
    "track_labels": obj(other=text(), key=text(pattern=r"block:.+")),
    "le_labels": obj(other=ANY),
    "le_band_labels": obj(other=obj(other=ANY)),
}
HOST_SCREEN = obj({"size": arr(whole(1), min=2, max=2), "taskbar": whole(0)}, required=("size", "taskbar"),
                  closed=True, check=_taskbar_below_height)
PREFERENCES = obj({
    "_sections": const(True),
    "_note": text(),
    # build_staging_sets.py writes staging's detail_sheets to preferences_generated.json: a hand one would win
    "staging": obj({**PREF_SECTION_KEYS, "detail_sheets": {"type": "any", "check": lambda v: (
        "staging's detail_sheets is generated (preferences_generated.json); a hand value would hide it")}},
        other=ANY, check=_no_window_keys),
    "main_upper": obj({
        **PREF_SECTION_KEYS,
        "revision": whole(0),                      # map_revision.fields: the title block
        "date": text(pattern=r"\d{4}-\d{2}-\d{2}"),
        "host_screen": HOST_SCREEN,                # host_screen.window
        "detail_sheets": obj(other=arr(text(nonempty=True))),
    }, required=("revision", "date", "host_screen"), other=ANY, check=_no_window_keys),
}, required=("_sections", "staging", "main_upper"), other=obj(other=ANY, check=_no_window_keys))


# ---------------------------------------------------------------- panel_items.json

POINTS = ("top-left", "top", "top-right", "left", "centre", "right", "bottom-left", "bottom", "bottom-right")
SIZE = arr(number(lo=0), min=2, max=2)
SET_BY_BUILD = ("class", "name", "x", "y", "panelwidth", "panelheight", "windowwidth", "windowheight")


def _anchor_rule(a: dict) -> str | None:
    if a["to"] != "origin" and "at" not in a:
        return f"a {a['to']} anchor needs at, one of {', '.join(POINTS)}"
    if (a["to"] == "block") != ("block" in a):
        return "a block anchor names its block, no other does"
    return None


def _member_rule(m: dict) -> str | None:
    if "right" in m:
        return "right places a label by its right edge and measures its size: give no dx or size" \
            if "dx" in m or "size" in m else None
    return None if "size" in m else "needs size [w, h] (or right in place of dx and size)"


def _item_rule(it: dict) -> str | None:
    if ("members" in it) == ("xml" in it):
        return "give xml and size, or members"
    if "xml" in it and "size" not in it:
        return "an item with xml needs size [w, h]"
    return None


def _no_build_attributes(attrs: dict) -> str | None:
    own = sorted(set(attrs) & set(SET_BY_BUILD))
    return f"{', '.join(own)} are the build's to set" if own else None


ANCHOR = obj({"to": text(("origin", "drawing", "block")), "at": text(POINTS), "block": text(nonempty=True),
              "dx": number(), "dy": number()}, required=("to",), closed=True, check=_anchor_rule)
MEMBER = obj({"dx": number(), "dy": number(), "xml": text(nonempty=True), "size": SIZE, "right": number()},
             required=("xml",), closed=True, check=_member_rule)
ITEM = obj({"id": text(nonempty=True), "anchor": ANCHOR, "xml": text(nonempty=True), "size": SIZE,
            "members": arr(MEMBER, min=1), "note": text()}, required=("id", "anchor"), closed=True, check=_item_rule)
PANEL_ITEMS = obj({"_note": text(), "attributes": obj(other=text(), check=_no_build_attributes),
                   "drawing_options": text(pattern=r"(?s)\s*<layoutTrackDrawingOptions\b.*"),
                   "items": arr(ITEM, min=1, unique="id")}, required=("items", "attributes"), closed=True)


# ---------------------------------------------------------------- published-files.json

def _site_path(rel: str) -> str | None:
    parts = rel.split("/")
    if rel.startswith("/") or rel.startswith("www/") or any(p in ("", ".", "..") for p in parts):
        return f"{rel!r} is not a path inside the site (relative to www/, no empty, . or .. part)"
    return None


def _repo_path(rel: str) -> str | None:
    parts = rel.split("/")
    if rel.startswith("/") or any(p in ("", ".", "..") for p in parts):
        return f"{rel!r} is not a path from the repo root"
    return None


# {site path: the one repo file the build copies there}; prepare_github_pages stops on a missing source
PUBLISHED_FILES = obj(other=text(file=True, check=_repo_path), key=text(nonempty=True, check=_site_path))


def _rel(path: Path) -> str:
    return Path(path).resolve().relative_to(ROOT).as_posix()


PLAN_OVERRIDES_FILE = _rel(layer_files.path("plan_overrides"))
PREFERENCES_FILE = _rel(layer_files.path("preferences"))
PANEL_ITEMS_FILE = _rel(hand_lists.PANEL_ITEMS)
SCHEMAS = {
    PLAN_OVERRIDES_FILE: PLAN_OVERRIDES,
    PREFERENCES_FILE: PREFERENCES,
    PANEL_ITEMS_FILE: PANEL_ITEMS,
    "www/scripts/published-files.json": PUBLISHED_FILES,
}


def check_file(rel: str, root: Path = ROOT, schema: dict | None = None, path: Path | None = None) -> list[str]:
    """The problems of one file, each starting with `rel`: the file `path` (default root/rel) against `schema`
    (default SCHEMAS[rel]); a `file` rule looks under `root`."""
    schema = SCHEMAS[rel] if schema is None else schema
    try:
        value = json.loads((root / rel if path is None else path).read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"{rel}: cannot read it ({exc.strerror or exc})"]
    except ValueError as exc:
        return [f"{rel}: not JSON ({exc})"]
    return [f"{rel}: {p}" for p in problems(value, schema, root=root)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", help="files to check, from the repo root (default: every one in SCHEMAS)")
    args = ap.parse_args(argv)
    def repo_rel(f: str) -> str:            # a path from the cwd (or absolute) as the repo-relative SCHEMAS key
        try:
            return Path(f).resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:                  # outside this repo: no schema
            return f
    files = [repo_rel(f) for f in args.files] or list(SCHEMAS)
    unknown = [f for f in files if f not in SCHEMAS]
    if unknown:
        print(f"check_json: no schema for {', '.join(unknown)} (schemas: {', '.join(SCHEMAS)})", file=sys.stderr)
        return 2
    failed = 0
    for rel in files:
        found = check_file(rel)
        failed += bool(found)
        for p in found:
            print(f"check_json: {p}", file=sys.stderr)
    print(f"check_json: {len(files) - failed} of {len(files)} files pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

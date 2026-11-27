"""Staging's switch rows of the device master (build_device_map.py, through device_map_staging): its turnout, LCC
alias and feedback rows (staging_wired_rows), generated for each switch of the plan (staging_switches) by the row
makers every level uses (device_map_rows.switch_device_rows), wired as wiring.csv has them and with the owner's
cells of devices_field.csv over them (staging_field, device_map_rows.owner_over). The constants and readers every
staging row needs (staging_field, staging_cps, check_unique) are here too; device_map_staging re-exports them.

The builder's paths are read from build_device_map when a function runs (device_map_schematic.builder): that module
imports this one through device_map_staging, so this one does not import it at load.
"""
from __future__ import annotations

import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from map_error import MapError  # noqa: E402
from device_map_inputs import CPS, NODES, STAGING_NAMES, WIRING, staging_nodes, wiring_rows  # noqa: E402  the readers
from device_map_rows import Wired, owner_over, switch_device_rows  # noqa: E402  every level's row makers
from device_map_schematic import builder  # noqa: E402
from hartlib import device_ids, devices, layer_files, railroad, track_names, wiring  # noqa: E402

natural = railroad.natural


STAGING_SHEET = "staging"           # staging's section of plan_overrides.json
STAGING = int(railroad.STAGING_LEVEL)   # staging's level, as wiring.csv and interlockings.csv number it
STAGING_LEVEL = railroad.STAGING_LEVEL  # and as the device master does
WRITER = "build_device_map.py"
FIELD_LAYERS = ("block", "occupancy")
# One row of the device master, keyed by hartlib.devices.COLUMNS. A plain dict, not a TypedDict: hartlib's row
# functions (devices.master_row, describe, merge) take Mapping[str, str], which a TypedDict does not satisfy.
MasterRow = dict[str, str]
FieldKey = tuple[str, str]          # (layer, device ID): how the owner's field rows are found (hartlib.devices.KEY)


WIRED_LAYERS = {"turnout": "turnout", "fb": "fb"}      # master layer -> wiring.csv kind of staging's wired rows


def field_row(f: Mapping[str, str]) -> MasterRow:
    """A full master row of a staging device from its field row (devices_field.csv): its key and the owner's cells,
    every other cell empty for this script to fill."""
    return {c: f[c] for c in devices.COLUMNS}


def staging_field(files: devices.Files | None = None, layers: Sequence[str] = FIELD_LAYERS
                  ) -> dict[FieldKey, MasterRow]:
    """{(layer, device ID): full row} of the field file's staging rows of `layers` (field_row): the devices the owner
    says staging has, this script's input for them, keyed as the field file is (hartlib.devices.KEY), so a row keeps
    its owner's user name when the generated name changes. Read from devices_field.csv alone, never from this
    script's last output."""
    bdm = builder()
    return {(f["layer"], f["id"]): field_row(f) for f in devices.field_index(files or bdm.device_files()).values()
            if f["level"] == STAGING_LEVEL and f["layer"] in layers}


def alias_note(turnout: str, address: str) -> str:
    """The note of an LCC alias row: the turnout it stands for and that turnout's LCOS address. MapError when the
    turnout has no address (no wiring.csv row)."""
    if not address:
        raise MapError(f"LCC alias DCC {turnout}: {turnout} has no turnout row in {WIRING.name}")
    return f"LCC alias of {turnout} ({address})"


def staging_switches(data: Path | None = None) -> dict[str, list[str]]:
    """{switch number: its plan labels} of staging's switches, from the plan (hartlib.track_names.plan_switches over
    the staging plan graph in `data`, default the builder's schematic folder), not from the owner's rows: the
    switches staging_wired_rows makes rows for."""
    folder = data or builder().OVERRIDES.parent
    try:
        return track_names.plan_switches(STAGING_SHEET, layer_files.read("plan_overrides", STAGING_SHEET, folder),
                                         folder)
    except track_names.TrackNameError as exc:
        raise MapError(str(exc)) from exc


def staging_cps() -> dict[str, str]:
    """{switch number: its control point} of staging's interlockings (interlockings.csv level 1): a staging device's
    generated cp; the owner's cp (its field row) goes over it."""
    try:
        return {str(s): r.name for r in railroad.read_interlockings(CPS, (STAGING,)) for s in r.switches}
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from exc


def staging_wired_rows(files: devices.Files | None = None, path: Path | None = None,
                       nodes: set[int] | None = None, switches: dict[str, list[str]] | None = None) -> list[MasterRow]:
    """Staging's turnout, LCC alias and feedback rows of the master, generated as main and upper's are
    (device_map_rows.switch_device_rows) for each switch of the plan (`switches`: {number: plan labels}, default
    staging_switches()), wired as wiring.csv has them (`path`, default the committed file: node, wiring text and
    address; staging's devices are bound to their address, an alias to MTT<dcc>), with the owner's values over them
    (device_map_rows.owner_over: the field row of the device's id in devices_field.csv, if it has one: its user name,
    role, assignment, cp, dcc and the rest). The alias takes the owner's DCC address (the turnout's or its own field
    row's); a switch with none has no alias row. An alias's note names its turnout as readers see it and its address
    (alias_note). `nodes`: staging's (default staging_nodes()). MapError on a switch with no turnout or feedback row
    in wiring.csv (staging's nodes are as built: the builder proposes none), a wiring or field row whose id names no
    switch of the plan, a node that is not staging's, or a turnout the panels bind by its old user name (Q13)."""
    field = builder().device_files() if files is None else files
    switches = staging_switches() if switches is None else switches
    w = _wired_inputs(path, field, staging_nodes() if nodes is None else nodes)
    out: list[MasterRow] = []
    for s, labels in switches.items():
        out += _switch_rows(w, s, labels) or []
    w.bad.extend(f"{WIRING.name} line {wire.line}: staging {kind} {did} names no switch of the plan"
                 for (kind, did), wire in sorted(w.by.items()) if did.split(":")[1] not in switches)
    w.bad.extend(f"{devices.FIELD_FILE}: staging {layer} {r['user_name'] or '(no name)'} (id {did}): the plan has no "
                 "such device (move the row's cells to the device's id, or remove the row)"
                 for (layer, did), r in sorted(w.owner.items()))
    if w.bad:
        raise MapError("; ".join(w.bad))
    check_unique(out, "staging's turnout and feedback rows")
    return sorted(out, key=lambda r: (devices.LAYERS.index(r["layer"]), natural(r["user_name"])))


class _WiredInputs(NamedTuple):
    """What staging_wired_rows reads once and fills per switch. `owner` (the field rows not yet used) and `bad` (the
    problems found) are changed in place, in switch order, so the error text keeps one order."""
    by: dict[FieldKey, wiring.Wire]     # {(kind, device ID): its wiring.csv row} of staging's turnouts and feedback
    owner: dict[FieldKey, MasterRow]    # staging_field of the wired layers
    cp_of: dict[str, str]               # staging_cps
    bad: list[str]


def _wired_inputs(path: Path | None, field: devices.Files, nodes: set[int]) -> _WiredInputs:
    """staging_wired_rows' inputs: wiring.csv's level 1 turnout and feedback rows (a row on a node that is not
    staging's is a problem, put in bad), the owner's field rows of those layers and staging's control points."""
    by = {(w.kind, w.id): w for w in wiring_rows(path, STAGING_NAMES, field)
          if w.level == STAGING and w.kind in WIRED_LAYERS.values()}
    bad = [f"{WIRING.name} line {w.line}: {w.kind} {w.device} is on node {w.node}, no staging node of {NODES.name} "
           f"({', '.join(map(str, sorted(nodes)))})" for w in by.values() if w.node not in nodes]
    return _WiredInputs(by, staging_field(field, tuple(WIRED_LAYERS)), staging_cps(), bad)


def _switch_rows(w: _WiredInputs, s: str, labels: list[str]) -> list[MasterRow] | None:
    """The turnout, alias (when it has a DCC address) and feedback rows of staging switch `s`, the owner's cells over
    them; None, with the problems in w.bad, when wiring.csv lacks one of its devices, an alias row has no DCC address
    or a row is bound by an old user name. The switch's field rows are taken out of w.owner either way."""
    tid, aid = device_ids.switch_id(s), device_ids.dcc_id(s)
    fb_ids = {nr: device_ids.fb_id(s, nr) for nr in "NR"}
    f_turnout, f_alias = w.owner.pop(("turnout", tid), None), w.owner.pop(("turnout", aid), None)
    f_fb = {nr: w.owner.pop(("fb", fb_ids[nr]), None) for nr in "NR"}
    wires = _switch_wires(w, s, tid, fb_ids, f_turnout, f_fb)
    if wires is None:
        return None
    turnout_wire = wires[("turnout", tid)]
    dcc = (f_turnout or {}).get("dcc") or (f_alias or {}).get("dcc") or ""
    if f_alias is not None and not dcc:
        w.bad.append(f"{devices.FIELD_FILE}: staging turnout {f_alias['user_name'] or 'DCC Switch ' + s} (id {aid}): "
                     f"an LCC alias needs a DCC address, and neither its row nor {tid}'s gives one: give dcc, or "
                     "remove the alias row")
        return None
    made = switch_device_rows(
        STAGING_LEVEL, w.cp_of.get(s, ""), s, labels, _wired(turnout_wire),
        {nr: _wired(wires[("fb", fb_ids[nr])]) for nr in "NR"},
        dcc, jmri=turnout_wire.address, alias_notes="", alias=bool(dcc) or f_alias is not None)
    # the master's form (devices.master_row); the DCC address is put back after, as a field turnout's wiring
    # text holds none (a JMRI comment's "DCC: n" group is the dcc column's)
    rows = {r["id"]: dict(devices.master_row(dict(r, dcc=""), WRITER), dcc=str(r["dcc"])) for r in made}
    turnout = owner_over(rows[tid], f_turnout)
    fbs = [owner_over(rows[fb_ids[nr]], f_fb[nr]) for nr in "NR"]
    if _bound_by_old_name(w.bad, [turnout] + fbs, wires):
        return None
    got = [turnout]
    if aid in rows:
        alias = dict(rows[aid], notes=alias_note(turnout["user_name"], turnout_wire.address))
        got.append(owner_over(alias, f_alias))
    got += fbs
    for r in got:
        r["description"] = devices.describe(r)
    return got


def _switch_wires(w: _WiredInputs, s: str, tid: str, fb_ids: Mapping[str, str], f_turnout: MasterRow | None,
                  f_fb: Mapping[str, MasterRow | None]) -> dict[FieldKey, wiring.Wire] | None:
    """{(kind, device ID): wiring.csv row} of switch `s`'s turnout and two feedback inputs; None, with a problem in
    w.bad for each device wiring.csv has no row for (named by the owner's user name, else the generated one)."""
    keys = [("turnout", tid)] + [("fb", fb_ids[nr]) for nr in "NR"]
    lost = [k for k in keys if k not in w.by]
    for kind, did in lost:
        f = f_turnout if kind == "turnout" else f_fb[did[-1]]
        name = (f or {}).get("user_name") or (f"Switch {s}" if kind == "turnout" else f"FB Switch {s} {did[-1]}")
        w.bad.append(f"staging {kind} {name}: no {kind} row for {did} in {WIRING.name}")
    return None if lost else {k: w.by[k] for k in keys}


def _wired(wire: wiring.Wire) -> Wired:
    """Where a wiring.csv row says its device is wired, as the row makers take it."""
    return Wired(wire.address, wire.node, wire.wiring_text)


def _bound_by_old_name(bad: list[str], rows: Sequence[MasterRow], wires: Mapping[FieldKey, wiring.Wire]) -> bool:
    """Whether a row of `rows` binds its device by a name that is neither its address nor its user name, with a
    problem in `bad` for each: a device the panels bind by its user name (Q13) moves its binding on a rename, so the
    owner changes both cells together; the build does not rewrite the binding."""
    unbound = [(r, wires[(r["layer"], r["id"])].address) for r in rows
               if r["jmri_name"] not in (wires[(r["layer"], r["id"])].address, r["user_name"])]
    for r, address in unbound:
        bad.append(f"{devices.FIELD_FILE}: staging {r['layer']} {r['user_name']} (id {r['id']}): its jmri_name "
                   f"{r['jmri_name']!r} binds it by its old user name; change jmri_name and user_name "
                   f"together, or clear jmri_name to bind it by its address {address}")
    return bool(unbound)


def check_unique(rows: Iterable[Mapping[str, str]], what: str) -> None:
    """The invariant every built set of staging rows keeps: one row per (layer, device ID), each with an ID. MapError
    naming `what` and the keys that break it."""
    count = Counter((r["layer"], r["id"]) for r in rows)
    bad = sorted(k for k, n in count.items() if n > 1 or not k[1])
    if bad:
        raise MapError(f"{what}: " + ", ".join(f"{layer} {did or '(no id)'}" for layer, did in bad)
                       + " given by no row or by more than one")

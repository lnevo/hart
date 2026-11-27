"""The device map's row makers, one for every level: the generator makes each device's row
from the plan, then the owner's values in devices_field.csv go over it (owner_over), the same way on every level.

- device_row: one device-map row (the old form, its comment split later by hartlib.devices.master_row) with the
  role and device ID its caller gives; no role is read off a name.
- switch_device_rows: a switch's turnout, its LCC alias and its two feedback rows, given where each is wired (main
  and upper: the rule's proposal or wiring.csv's frozen row, build_device_map.build; staging: wiring.csv as built,
  device_map_staging.staging_wired_rows).
- owner_over: a generated master row with its field row's cells over it (hartlib.devices.FIELD_COLUMNS), its
  description written again; a row with no field row is returned as it is.
- bean_cells: a main or upper row's start and bean_comment, what hartlib.tables_build.master_beans puts on the
  row's bean, in staging's form.

What stays per level is where the wiring comes from and which JMRI name a device has: staging's devices are bound
to their LCOS addresses, main and upper's to the virtual names (hartlib.level_devices) until their plant is wired.
"""
from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from map_error import MapError  # noqa: E402
import publish_draft  # noqa: E402,F401  puts tools/hartlib/src on the path, so this module imports on its own
from hartlib import device_ids, devices, level_devices, railroad  # noqa: E402
from hartlib.level_masts import SHSM, mast_heads  # noqa: E402  a mast's name over its heads; its heads, in order
from hartlib.tables_build import with_direction  # noqa: E402  a mast's comment names the way it faces

if TYPE_CHECKING:       # the records module imports the plan modules; the row makers need only its type names
    from device_map_records import DeviceMapRow, Layer, MasterCells

Key = tuple[str, str]       # (level, id) of a master row, as its text cells give them


def device_row(level: int, cp: str, layer: Layer, user: str, system: str = "", node: int | str = "",
               comment: str = "", trial: str = "", notes: str = "", dcc: int | str = "", jmri: str = "", *,
               role: str, ident: str, **facts: str) -> DeviceMapRow:
    """A device-map row with the role (hartlib.devices.ROLES) its caller says it has and its device ID (`ident`,
    hartlib.device_ids), from the plan facts its caller holds; `facts` the fact columns (railroad.DEVICE_FACTS),
    each empty when not given. MapError on a fact column that is not one."""
    unknown = sorted(set(facts) - set(railroad.DEVICE_FACTS))
    if unknown:
        raise MapError(f"{layer} {user}: unknown fact columns {unknown}")
    row: DeviceMapRow = {
        "level": level, "cp": cp, "layer": layer, "id": ident, "user_name": user, "system_name": system,
        "jmri_name": jmri, "node": node, "dcc": dcc, "comment": comment, "trial_name": trial, "notes": notes,
        "role": role, "blocks": facts.get("blocks", ""), "detector": facts.get("detector", ""),
        "stop": facts.get("stop", ""), "switch": facts.get("switch", ""), "facing": facts.get("facing", ""),
        "protects": facts.get("protects", ""), "dir": facts.get("dir", "")}
    return row


class Wired(NamedTuple):
    """Where a device is wired: its LCOS system name, node and wiring text ("Node: 4 Turnout: 0 ...")."""
    system: str
    node: int | str
    where: str


def switch_shape(jmri: str, dcc: int | str) -> tuple[str, bool]:
    """(the LCC alias's jmri_name, whether the feedback rows are JMRI sensors) of a switch whose turnout has JMRI name
    `jmri`, by that name's assignment (hartlib.devices.assignment_of), not by its level: a
    field turnout's alias is a JMRI turnout of its own (MTT<dcc>, none without a DCC address) and its feedback rows
    are sensors of their own system names (TWOSENSOR feedback), as staging's are; a virtual turnout's alias names the
    turnout's bean (it gives none) and its feedback rows have no JMRI name (DIRECT feedback), as main and upper's are
    until their plant is wired."""
    if devices.assignment_of(jmri) == "field":
        return (f"MTT{dcc}" if dcc else ""), True
    return jmri, False


def switch_device_rows(level: int, cp: str, s: str, labels: Iterable[str], turnout: Wired, fbs: Mapping[str, Wired],
                       dcc: int | str, *, jmri: str, alias_notes: str, notes: str = "", alias: bool = True
                       ) -> list[DeviceMapRow]:
    """The rows of switch `s` (device_row form): its turnout "Switch <s>" (its trial name from its plan labels,
    `labels`; `notes`), its LCC alias "DCC Switch <s>" (MTT<dcc>, on the turnout's node and wiring, `alias_notes`; none
    when `alias` is false) and its feedback "FB Switch <s> N" and "R" (`fbs`: {"N": Wired, "R": Wired}). `jmri`: the
    JMRI name the turnout is bound by; the alias's and the feedback rows' follow it (switch_shape). The turnout and
    alias rows get no cp (devices.place gives a turnout's place from the switch lists); the feedback rows get `cp`."""
    alias_jmri, fb_bound = switch_shape(jmri, dcc)
    trial = ", ".join(f"Switch {lb}" for lb in sorted(set(labels), key=railroad.natural))
    rows = [device_row(level, "", "turnout", f"Switch {s}", turnout.system, turnout.node, turnout.where, trial, notes,
                       dcc, jmri=jmri, role="turnout", ident=device_ids.switch_id(s))]
    if alias:
        rows.append(device_row(level, "", "turnout", f"DCC Switch {s}", f"MTT{dcc}", turnout.node, turnout.where,
                               notes=alias_notes, dcc=dcc, jmri=alias_jmri, role="lcc_alias",
                               ident=device_ids.dcc_id(s)))
    for nr in "NR":
        w = fbs[nr]
        rows.append(device_row(level, cp, "fb", f"FB Switch {s} {nr}", w.system, w.node, w.where,
                               jmri=w.system if fb_bound else "", role="fb", ident=device_ids.fb_id(s, nr)))
    return rows


def owner_over(row: Mapping[str, str], field: Mapping[str, str] | None) -> MasterCells:
    """Generated master row `row` with the owner's values over it: each non-empty cell of its field row
    (devices_field.csv, hartlib.devices.FIELD_COLUMNS) replaces the generated one, as hartlib.devices.merge does, so
    the builder gives what readers will see (a user name included: the owner's name is the device's on every level).
    A jmri_comment with hartlib.devices.OCCUPANCY_MARK is the builder's to fill: the generated cell stands when it
    is already the field text with the mark filled (as devices.merge takes it), else the field text is taken as it is
    for the caller to fill (staging_rows' wire_block). A field jmri_name with no field assignment sets the
    assignment its name gives (devices.assignment_of: a swap is that one cell, ADR-028). The description is written again from the result
    (devices.describe). `row` as it is (a copy) when `field` is None."""
    out = dict(row)
    if field is None:
        return out
    for c in devices.FIELD_COLUMNS:
        v = field[c]
        if not v:
            continue
        if c == "jmri_comment" and devices.OCCUPANCY_MARK in v and devices.is_templated(v, out[c]):
            continue
        out[c] = v
    if field["jmri_name"] and not field["assignment"]:
        # a swap is one cell (ADR-028): the owner's JMRI name says how the device is in JMRI
        out["assignment"] = devices.assignment_of(field["jmri_name"])
    out["description"] = devices.describe(out)
    return out


def follow_swaps(rows: Sequence[Mapping[str, str]], field: Mapping[Key, Mapping[str, str]]) -> list[MasterCells]:
    """`rows` (master rows with the owner's values over them, owner_over) with the LCC alias and feedback rows of
    each turnout swapped to a field device by its own row alone (ADR-028: its jmri_name and assignment field) given
    the shape switch_shape gives a field turnout: the alias a JMRI turnout of its own, the feedback rows sensors of
    their system names (the planned pins, wired with the turnout); their descriptions written again. A detector
    swapped in the same way (an occupancy row whose assignment is field) is wired, not planned. A row whose own
    field row (`field`, {(level, id): row}) gives a jmri_name or an assignment (a detector: its detector) keeps the
    owner's. A mast over a head swapped in the same way (a head row whose assignment is field) stands on its heads'
    JMRI names (mast_on_heads). So a swap is one row edit; every other row as it is."""
    turnouts = {(r["level"], r["id"].removeprefix("switch:")): r for r in rows
                if r["layer"] == "turnout" and r["role"] == "turnout" and r["assignment"] == "field"}
    heads = {(r["level"], r["id"]): r for r in rows if r["layer"] == "head"}
    return [dict(swapped(r, field.get((r["level"], r["id"])) or {}, turnouts, heads)) for r in rows]


def swapped(r: Mapping[str, str], own: Mapping[str, str], turnouts: Mapping[Key, Mapping[str, str]],
            heads: Mapping[Key, Mapping[str, str]]) -> Mapping[str, str]:
    """Master row `r` as follow_swaps gives it, `own` its field row ({} with none), `turnouts` the field turnout rows
    by (level, switch number) and `heads` the head rows by (level, id)."""
    if r["layer"] == "mast":
        return r if own.get("jmri_name") or own.get("assignment") else mast_on_heads(r, heads)
    if r["layer"] == "occupancy" and r["assignment"] == "field" and r["detector"] == "planned" and \
            not own.get("detector"):
        out = dict(r, detector="wired")       # a detector swapped in is the wired one (railroad.read_device_map)
        out["description"] = devices.describe(out)
        return out
    kind, _, rest = r["id"].partition(":")
    t = turnouts.get((r["level"], rest.split(":")[0])) if kind in ("dcc", "fb") else None
    if t is None or r["assignment"] == "field" or own.get("jmri_name") or own.get("assignment"):
        return r
    alias_jmri, _bound = switch_shape(t["jmri_name"] or t["system_name"], r["dcc"] or t["dcc"])
    jmri = alias_jmri if kind == "dcc" else r["system_name"]
    out = dict(r, jmri_name=jmri, assignment=devices.assignment_of(jmri))
    out["description"] = devices.describe(out)
    return out


def mast_on_heads(mast: Mapping[str, str], heads: Mapping[Key, Mapping[str, str]]) -> Mapping[str, str]:
    """Master row `mast` standing on its heads' JMRI names when one of them is a field head (a head swapped in by its
    own row, its assignment field): each head of its SignalHeadSignalMast name is found by ID, its mast's ID and its
    place (hartlib.device_ids.head_place, top first), in `heads` ({(level, id): row}), and takes that row's
    jmri_name; the assignment is the new name's and the description written again. A mast with no field head, a
    hidden (IF$vsm) mast, or one whose heads are not all rows of `heads`, as it is."""
    m = SHSM.fullmatch(mast["jmri_name"])
    names = mast_heads(mast["jmri_name"])
    if not m or not names or len(names) > 2 or not mast["id"].startswith("mast:"):
        return mast
    keys = [(mast["level"], device_ids.head_id(mast["id"], device_ids.head_place(i, len(names))))
            for i in range(len(names))]
    if any(k not in heads for k in keys):
        return mast
    rows = [heads[k] for k in keys]
    if not any(h["assignment"] == "field" for h in rows):
        return mast
    # one pass over the head list, so a head's new name is never taken for another head's old one
    jmri = f"IF$shsm:{m.group(1)}:{m.group(2)}" + "".join(f"({h['jmri_name']})" for h in rows)
    if jmri == mast["jmri_name"]:
        return mast
    r = dict(mast, jmri_name=jmri, assignment=devices.assignment_of(jmri))
    r["description"] = devices.describe(r)
    return r


# ---------------------------------------------------------------- what a main or upper bean takes from its row

BEAN_LEVELS = level_devices.LEVELS      # the levels whose rows carry start and bean_comment (main and upper)


def makes_bean(r: Mapping[str, str]) -> bool:
    """Whether master row `r` is a main or upper row whose bean takes its comment and startup state from the row
    (start and bean_comment): a row with a JMRI name that is a turnout (not its LCC alias, which names the turnout's
    bean), a block (not a helix block, whose beans are staging's, whatever jmri_name its row is given), a detector
    (not a spare one: the device maps leave it out), a mast or a head. A feedback row gives none (DIRECT feedback), nor
    a row with assignment none."""
    if r["level"] not in BEAN_LEVELS or r["assignment"] == "none" or r["role"] in ("lcc_alias", "spare"):
        return False
    if r["layer"] == "block":
        return r["role"] != "helix"
    return r["layer"] in ("turnout", "occupancy", "mast", "head")


def bean_cells(rows: Sequence[Mapping[str, str]], thrown: frozenset[str] = frozenset()) -> list[MasterCells]:
    """`rows` (master rows, the owner's values over them) with each main and upper row whose bean takes its comment
    from the row (makes_bean) given its start and bean_comment; every other row as it is, its two cells emptied.
    hartlib.tables_build.master_beans makes the bean from them. The comments are in staging's form: the parts joined
    by " | ", the place first (the row's jmri_comment, as on staging's masts and blocks), a block's detector first,
    and a bean no field device drives says so (level_devices.VIRTUAL_NOTE, as a staging head on an internal name
    does), then the planned physical device, a draft (level_devices.planned_note):

    - a turnout (not its LCC alias): start (a virtual one's only: a field device reports its own state) closed, or
      thrown when its switch number is in `thrown` (build_device_map.startup_thrown: the main route runs through
      leg C); comment its place (devices.place), "Switch <n>", the note and its planned turnout:
      "CP 107 | Switch 107 | internal, not wired | planned M2T3308 (draft)";
    - a block (not a helix block, whose beans are staging's): its detector (a part: its block's) and the
      detector's sensor, then its jmri_comment, or for a part with none the block it is part of: "BS 107-109 /
      IS:HART:C3:B:107-109; CP 107";
    - a detector: start inactive (a virtual one's, as a turnout's); comment the note, then its planned detector or why
      there is none (its notes): "internal, not wired | planned M2S3305 (draft)";
    - a mast: its jmri_comment (else its cp and switch, or "intermediate") and direction
      (tables_build.with_direction), then its planned mast (its system name, when not its own name), or
      level_devices.UNPLACED_NOTE when the draft plant has no board room for it (ADR-024): "CP 107 | Switch 107 |
      West | planned IF$shsm:...(IH3332)(IH3333) (draft)"; a hidden mast at a buffer stop has neither: "Peninsula |
      buffer stop | East";
    - a head: its jmri_comment or its mast's place, the note and its planned head (by its place in the mast's planned
      system name) or UNPLACED_NOTE: "CP 107 | Switch 107 | internal, not wired | planned IH3332 (draft)".
    A row that is not virtual (a device swapped in, ADR-028) has no note and no planned device: its wiring follows
    its place, as on staging. Only the rows makes_bean names get cells. MapError on a head with no mast row of its
    id, a block no detector row names, or a switch in `thrown` that is no main or upper turnout row's (the rule and
    the rows disagree: nothing would start it Thrown)."""
    masts = {r["id"]: r for r in rows if r["level"] in BEAN_LEVELS and r["layer"] == "mast"}
    turnouts = {r["id"].removeprefix("switch:") for r in rows if makes_bean(r) and r["layer"] == "turnout"}
    stray = sorted(set(thrown) - turnouts)
    if stray:
        raise MapError(f"switches {', '.join(stray)} start Thrown (the main route through leg C), but no main or "
                       "upper turnout row is theirs")
    detector = {(r["level"], b.strip()): r for r in rows if makes_bean(r) and r["layer"] == "occupancy"
                for b in r["blocks"].split(";") if b.strip()}
    out = []
    for r in rows:
        cells = dict(r, start="", bean_comment="")
        if makes_bean(cells):
            start, comment = bean_of(cells, thrown, detector, masts)
            cells.update(start=start, bean_comment=comment)
        out.append(cells)
    return out


def bean_of(r: Mapping[str, str], thrown: frozenset[str], detector: Mapping[Key, Mapping[str, str]],
            masts: Mapping[str, Mapping[str, str]]) -> tuple[str, str]:
    """(start, bean_comment) of row `r`, one bean_cells names (makes_bean), by its layer: `detector` the detector rows
    by (level, block), `masts` the main and upper mast rows by ID. MapError as bean_cells says."""
    layer = r["layer"]
    if layer == "turnout":
        number = r["id"].removeprefix("switch:")
        return (virtual_start(r, "thrown" if number in thrown else "closed"),
                joined(devices.place(r), f"Switch {number}", *drafted(r, r["system_name"])))
    if layer == "block":
        d = detector.get((r["level"], r["part_of"] or r["user_name"]))
        if d is None:
            raise MapError(f"block {r['user_name']} (level {r['level']}): no detector row names "
                           + (f"its block {r['part_of']}" if r["part_of"] else "it"))
        what = r["jmri_comment"] or (f"part of {r['part_of']}" if r["part_of"] else "")
        return "", "; ".join(x for x in (f"{d['user_name']} / {d['jmri_name']}", what) if x)
    if layer == "occupancy":
        return virtual_start(r, "inactive"), (
            joined(level_devices.VIRTUAL_NOTE, r["notes"]) if r["assignment"] == "virtual" and not r["system_name"]
            else joined(*drafted(r, r["system_name"])))
    if layer == "mast":
        # a mast's planned device follows its place; a virtual mast says nothing of being unwired (its heads
        # do), and a hidden one at a buffer stop has no device to plan
        planned = "" if r["role"] == "hidden" or r["assignment"] != "virtual" else \
            drafted(r, r["system_name"], placed=True)[1]
        return "", joined(with_direction(mast_place(r), r["dir"]), planned)
    if layer == "head":
        m = masts.get(r["id"].rsplit(":", 1)[0])
        if m is None:
            raise MapError(f"head {r['user_name']} ({r['id']}): no mast row of its id")
        heads = dict(zip(mast_heads(m["jmri_name"]), mast_heads(m["system_name"])))
        return "", joined(r["jmri_comment"] or mast_place(m), *drafted(r, heads.get(r["jmri_name"], ""), placed=True))
    raise MapError(f"{r['user_name']} ({r['id']}): layer {layer!r} makes no bean")


def joined(*parts: str) -> str:
    """The non-empty parts of a bean comment, joined by " | "."""
    return " | ".join(p for p in parts if p)


def drafted(r: Mapping[str, str], planned: str, placed: bool = False) -> tuple[str, ...]:
    """The parts of row `r`'s bean comment after the place: a virtual row's VIRTUAL_NOTE and its planned device
    (`planned`, a draft; for a head or a mast that is not hidden, `placed`, UNPLACED_NOTE when it has none; nothing
    when the planned name is the bean's own); a swapped row's (ADR-028) wiring, the device that is wired, as
    staging's."""
    if r["assignment"] != "virtual":
        return (r["wiring"],)
    if planned and planned == r["jmri_name"]:
        return (level_devices.VIRTUAL_NOTE, "")
    return (level_devices.VIRTUAL_NOTE, level_devices.planned_note(planned) if planned or placed else "")


def virtual_start(r: Mapping[str, str], state: str) -> str:
    """`state` as a virtual row's start; none on a field device, which reports its own state."""
    return state if r["assignment"] == "virtual" else ""


def mast_place(m: Mapping[str, str]) -> str:
    """A mast's place: its jmri_comment, else its cp and switch (or "intermediate")."""
    return m["jmri_comment"] or joined(m["cp"], f"Switch {m['switch']}" if m["switch"] else "intermediate")

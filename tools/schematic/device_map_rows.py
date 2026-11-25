"""The device map's row makers, one for every level (naming-layers step 7): the generator makes each device's row
from the plan, then the owner's values in devices_field.csv go over it (owner_over), the same way on every level.

- device_row: one device-map row (the old form, its comment split later by hartlib.devices.master_row) with the
  role and device ID its caller gives; no role is read off a name.
- switch_device_rows: a switch's turnout, its LCC alias and its two feedback rows, given where each is wired (main
  and upper: the rule's proposal or wiring.csv's frozen row, build_device_map.build; staging: wiring.csv as built,
  device_map_staging.staging_wired_rows).
- owner_over: a generated master row with its field row's cells over it (hartlib.devices.FIELD_COLUMNS), its
  description written again; a row with no field row is returned as it is.
- bean_cells: a main or upper row's start and bean_comment, what the Layout Editor build reads off the row for the
  bean it makes (naming-layers step 9), so step 11 can make every bean from the row alone.

What stays per level is where the wiring comes from and which JMRI name a device has: staging's devices are bound
to their LCOS addresses, main and upper's to the virtual names (hartlib.level_devices) until their plant is wired.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Mapping, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mast_rule import MapError  # noqa: E402
from hartlib import device_ids, devices, level_devices, railroad  # noqa: E402
from hartlib.level_masts import mast_heads  # noqa: E402  a mast's heads, in order
from hartlib.tables_build import with_direction  # noqa: E402  a mast's comment names the way it faces


def device_row(level, cp, layer, user, system="", node="", comment="", trial="", notes="", dcc="", jmri="", *, role,
               ident, **facts) -> dict:
    """A device-map row with the role (hartlib.devices.ROLES) its caller says it has and its device ID (`ident`,
    hartlib.device_ids), from the plan facts its caller holds; `facts` the fact columns (railroad.DEVICE_FACTS).
    MapError on a fact column that is not one."""
    row = dict(level=level, cp=cp, layer=layer, id=ident, user_name=user, system_name=system, jmri_name=jmri,
               node=node, dcc=dcc, comment=comment, trial_name=trial, notes=notes, role=role,
               **{c: facts.pop(c, "") for c in railroad.DEVICE_FACTS})
    if facts:
        raise MapError(f"{layer} {user}: unknown fact columns {sorted(facts)}")
    return row


class Wired(NamedTuple):
    """Where a device is wired: its LCOS system name, node and wiring text ("Node: 4 Turnout: 0 ...")."""
    system: str
    node: object
    where: str


def switch_device_rows(level, cp, s: str, labels, turnout: Wired, fbs: Mapping[str, Wired], dcc, *, jmri: str,
                       alias_jmri: str, alias_notes: str, notes: str = "", alias: bool = True,
                       fb_bound: bool = False) -> list[dict]:
    """The rows of switch `s` (device_row form): its turnout "Switch <s>" (its trial name from its plan labels,
    `labels`; `notes`), its LCC alias "DCC Switch <s>" (MTT<dcc>, on the turnout's node and wiring, `alias_notes`; none
    when `alias` is false) and its feedback "FB Switch <s> N" and "R" (`fbs`: {"N": Wired, "R": Wired}). `jmri`,
    `alias_jmri`: the JMRI names the level binds the turnout and alias by; a feedback row is a JMRI sensor of its own
    system name when `fb_bound` (staging's), else it has none (main and upper's: DIRECT feedback)."""
    trial = ", ".join(f"Switch {lb}" for lb in sorted(set(labels), key=railroad.natural))
    rows = [device_row(level, cp, "turnout", f"Switch {s}", turnout.system, turnout.node, turnout.where, trial, notes,
                       dcc, jmri=jmri, role="turnout", ident=device_ids.switch_id(s))]
    if alias:
        rows.append(device_row(level, cp, "turnout", f"DCC Switch {s}", f"MTT{dcc}", turnout.node, turnout.where,
                               notes=alias_notes, dcc=dcc, jmri=alias_jmri, role="lcc_alias",
                               ident=device_ids.dcc_id(s)))
    for nr in "NR":
        w = fbs[nr]
        rows.append(device_row(level, cp, "fb", f"FB Switch {s} {nr}", w.system, w.node, w.where,
                               jmri=w.system if fb_bound else "", role="fb", ident=device_ids.fb_id(s, nr)))
    return rows


def owner_over(row: Mapping[str, str], field: Mapping[str, str] | None) -> dict:
    """Generated master row `row` with the owner's values over it: each non-empty cell of its field row
    (devices_field.csv, hartlib.devices.FIELD_COLUMNS) replaces the generated one, as hartlib.devices.merge does, so
    the builder gives what readers will see (a user name included: the owner's name is the device's on every level).
    A jmri_comment with hartlib.devices.OCCUPANCY_MARK is the builder's to fill: the generated cell stands when it
    is already the field text with the mark filled (as devices.merge takes it), else the field text is taken as it is
    for the caller to fill (staging_rows' wire_block). The description is written again from the result
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
    out["description"] = devices.describe(out)
    return out


# ---------------------------------------------------------------- what the Layout Editor build reads off a row

BEAN_LEVELS = level_devices.LEVELS      # the levels whose beans the Layout Editor build makes until step 11


def makes_bean(r: Mapping[str, str]) -> bool:
    """Whether the Layout Editor build makes a bean for master row `r` (and so reads its start and bean_comment): a
    main or upper row with a JMRI name that is a turnout (not its LCC alias), a block (not a helix block, whose beans
    are staging's, whatever jmri_name its row is given), a detector (not a spare one: the device maps leave it out),
    a mast or a head. A feedback row gives none (DIRECT feedback), nor a row with assignment none."""
    if r["level"] not in BEAN_LEVELS or r["assignment"] == "none" or r["role"] in ("lcc_alias", "spare"):
        return False
    if r["layer"] == "block":
        return r["role"] != "helix"
    return r["layer"] in ("turnout", "occupancy", "mast", "head")


def bean_cells(rows: list[Mapping[str, str]], thrown: frozenset = frozenset()) -> list[dict]:
    """`rows` (master rows, the owner's values over them) with each main and upper row the Layout Editor build makes a
    bean for given its start and bean_comment (naming-layers step 9), so step 11 can make every bean from the row
    alone; every other row as it is, its two cells emptied. The words are hartlib.level_devices' and tables.xml's as
    it stands (step 11 unifies them, owner 2026-11-23):

    - a turnout (not its LCC alias): start closed, or thrown when its switch number is in `thrown`
      (build_device_map.startup_thrown: the main route runs through leg C); comment LEVEL_COMMENT;
    - a block (not a helix block, whose beans are staging's): comment LEVEL_COMMENT;
    - a detector: start inactive (the sensors-clear LogixNG), comment sensor_comment (its planned detector or why
      there is none);
    - a mast: its cp and switch (or "intermediate"), the planned device and its direction
      (tables_build.with_direction); a virtual (hidden) mast its cp and "buffer stop";
    - a head: its mast's place and the planned head (by its place in the mast's planned system name).
    Only the rows makes_bean names get cells. MapError on a head with no mast row of its id, or a switch in `thrown`
    that is no main or upper turnout row's (the rule and the rows disagree: nothing would start it Thrown)."""
    masts = {r["id"]: r for r in rows if r["level"] in BEAN_LEVELS and r["layer"] == "mast"}
    turnouts = {r["id"].removeprefix("switch:") for r in rows if makes_bean(r) and r["layer"] == "turnout"}
    stray = sorted(set(thrown) - turnouts)
    if stray:
        raise MapError(f"switches {', '.join(stray)} start Thrown (the main route through leg C), but no main or "
                       "upper turnout row is theirs")

    def where(m) -> str:
        return " | ".join(x for x in (m["cp"], f"Switch {m['switch']}" if m["switch"] else "intermediate") if x)

    out = []
    for r in rows:
        r = dict(r, start="", bean_comment="")
        if not makes_bean(r):
            out.append(r)
            continue
        layer = r["layer"]
        if layer == "turnout":
            r["start"] = "thrown" if r["id"].removeprefix("switch:") in thrown else "closed"
            r["bean_comment"] = level_devices.LEVEL_COMMENT
        elif layer == "block":
            r["bean_comment"] = level_devices.LEVEL_COMMENT
        elif layer == "occupancy":
            r["start"] = "inactive"
            r["bean_comment"] = level_devices.sensor_comment(r["system_name"], r["notes"])
        elif layer == "mast" and r["jmri_name"].startswith("IF$vsm:"):
            r["bean_comment"] = with_direction(" | ".join(x for x in (r["cp"], "buffer stop") if x), r["dir"])
        elif layer == "mast":
            r["bean_comment"] = with_direction(f"{where(r)} | {level_devices.signal_note(r['system_name'])}", r["dir"])
        elif layer == "head":
            m = masts.get(r["id"].rsplit(":", 1)[0])
            if m is None:
                raise MapError(f"head {r['user_name']} ({r['id']}): no mast row of its id")
            planned = dict(zip(mast_heads(m["jmri_name"]), mast_heads(m["system_name"])))
            r["bean_comment"] = f"{where(m)} | {level_devices.signal_note(planned.get(r['jmri_name']))}"
        out.append(r)
    return out

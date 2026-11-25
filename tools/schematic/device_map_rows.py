"""The device map's row makers, one for every level (naming-layers step 7): the generator makes each device's row
from the plan, then the owner's values in devices_field.csv go over it (owner_over), the same way on every level.

- device_row: one device-map row (the old form, its comment split later by hartlib.devices.master_row) with the
  role and device ID its caller gives; no role is read off a name.
- switch_device_rows: a switch's turnout, its LCC alias and its two feedback rows, given where each is wired (main
  and upper: the rule's proposal or wiring.csv's frozen row, build_device_map.build; staging: wiring.csv as built,
  device_map_staging.staging_wired_rows).
- owner_over: a generated master row with its field row's cells over it (hartlib.devices.FIELD_COLUMNS), its
  description written again; a row with no field row is returned as it is.

What stays per level is where the wiring comes from and which JMRI name a device has: staging's devices are bound
to their LCOS addresses, main and upper's to the virtual names (hartlib.level_devices) until their plant is wired.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Mapping, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mast_rule import MapError  # noqa: E402
from hartlib import device_ids, devices, railroad  # noqa: E402


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
    A jmri_comment with hartlib.devices.OCCUPANCY_MARK is taken as it is, for the caller to fill. The description is
    written again from the result (devices.describe). `row` as it is (a copy) when `field` is None."""
    out = dict(row)
    if field is None:
        return out
    for c in devices.FIELD_COLUMNS:
        if field[c]:
            out[c] = field[c]
    out["description"] = devices.describe(out)
    return out

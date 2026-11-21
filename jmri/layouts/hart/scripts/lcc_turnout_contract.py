#!/usr/bin/env python3
"""MQTT M2T* plant <-> OpenLCB MTT{dcc} alias (devices.csv: DCC Switch N).

Every field turnout row of devices.csv (an MQTT M2T* plant) has an LCC alias row ``DCC Switch N`` whose system name
is ``MTT{dcc}``, the turnout row's own ``dcc`` column. In tables.xml the alias bean has the alias row's user name and
comment (its wiring, with no DCC group) and the same feedback sensors as the MQTT bean. Do not delete MTT* as
leftovers. Nothing here reads a DCC address out of a comment: the address is the row's ``dcc``.

Every LCOS turnout is a DCC turnout, but not every DCC turnout is LCOS (owner, 2026-11-20): an MTT* with no MQTT plant
(a DCC accessory, a test turnout) is no problem. Only a devices.csv row that names itself an MQTT plant's alias needs
one.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices  # noqa: E402


def child_text(element: ET.Element, tag: str) -> str:
    value = element.findtext(tag)
    return value.strip() if value else ""


@dataclass(frozen=True)
class Plant:
    """A field turnout row of devices.csv and its LCC alias row."""
    line: int
    user: str              # Switch N
    system: str            # M2T...
    dcc: str
    alias: str             # the alias row's system name, MTT{dcc}
    alias_user: str        # DCC Switch N
    alias_comment: str     # the alias row's JMRI comment (devices.comment_of): its wiring, no DCC group


def field_plants(csv_path: Path) -> tuple[dict[str, Plant], set[str], list[str]]:
    """({M2T system name: Plant} of the field turnout rows of devices.csv, the system names of the field turnout rows
    refused, problems): a refused row is a field turnout with no DCC address or no LCC alias row, or one whose alias's
    system name is not MTT{dcc}; an alias with no turnout row is a problem too. DevicesError when the master cannot be
    read."""
    rows = list(enumerate(devices.load(csv_path), 2))
    aliases = {r["user_name"]: r for _n, r in rows if r["role"] == "lcc_alias" and r["assignment"] == "field"}
    out, refused, bad = {}, set(), []
    for n, r in rows:
        if r["role"] != "turnout" or r["assignment"] != "field":
            continue
        at = f"{csv_path.name} line {n} ({r['user_name']}, {r['system_name']})"
        a = aliases.pop(f"DCC {r['user_name']}", None)
        problem = ("a field turnout with no dcc" if not r["dcc"] else
                   f"no LCC alias row DCC {r['user_name']}" if a is None else
                   f"its alias DCC {r['user_name']} is {a['system_name']}, not MTT{r['dcc']} (its dcc)"
                   if a["system_name"] != f"MTT{r['dcc']}" else "")
        if problem:
            bad.append(f"{at}: {problem}")
            refused.add(r["system_name"])
        else:
            out[r["system_name"]] = Plant(n, r["user_name"], r["system_name"], r["dcc"], a["system_name"],
                                          a["user_name"], devices.comment_of(a))
    bad += [f"{csv_path.name}: alias {u} ({a['system_name']}) has no field turnout row {u.removeprefix('DCC ')}"
            for u, a in sorted(aliases.items())]
    return out, refused, bad


def identity_lcc_rows(csv_path: Path) -> dict[str, tuple[str, str]]:
    """MTT* -> (user name, JMRI comment) of the field LCC alias rows of devices.csv."""
    if not csv_path.is_file():
        return {}
    plants, _refused, _bad = field_plants(csv_path)
    return {p.alias: (p.alias_user, p.alias_comment) for p in plants.values()}


def turnout_index(root: ET.Element) -> dict[str, ET.Element]:
    out: dict[str, ET.Element] = {}
    for turnout in root.iter("turnout"):
        sn = child_text(turnout, "systemName")
        if sn:
            out[sn] = turnout
    return out


def contract_violations(root: ET.Element, csv_path: Path) -> list[str]:
    """Human-readable failures of tables.xml `root` against the field turnouts of devices.csv `csv_path`; empty means
    the contract holds. A devices.csv that cannot be read is one failure, naming it."""
    beans = turnout_index(root)
    mqtt = {sn: el for sn, el in beans.items() if sn.startswith("M2T")}
    lcc = {sn: el for sn, el in beans.items() if sn.startswith("MTT")}
    try:
        plants, refused, problems = field_plants(csv_path)
    except devices.DevicesError as exc:
        return [f"{csv_path.name}: cannot check the LCC aliases: {exc}"]

    for sn, el in sorted(mqtt.items()):
        user = child_text(el, "userName")
        plant = plants.get(sn)
        if plant is None:
            if sn not in refused:                   # a refused row is reported once, by field_plants
                problems.append(f"{sn} ({user or '?'}) has no field turnout row in {csv_path.name}")
            continue
        if user != plant.user:
            problems.append(f"{sn} userName {user!r} expected {plant.user!r} ({csv_path.name} line {plant.line})")
        twin = lcc.get(plant.alias)
        if twin is None:
            problems.append(f"{sn} ({plant.user}) has no LCC alias {plant.alias}")
            continue
        got_user = child_text(twin, "userName")
        got_comment = child_text(twin, "comment")
        if got_user != plant.alias_user:
            problems.append(f"{plant.alias} userName {got_user!r} expected {plant.alias_user!r}")
        if got_comment != plant.alias_comment:
            problems.append(f"{plant.alias} comment {got_comment!r} expected {plant.alias_comment!r}")
        mqtt_fb = el.get("feedback") or ""
        lcc_fb = twin.get("feedback") or ""
        if lcc_fb != mqtt_fb:
            problems.append(f"{plant.alias} feedback {lcc_fb!r} expected {mqtt_fb!r}")
        if mqtt_fb == "TWOSENSOR":
            for attr in ("sensor1", "sensor2"):
                want = el.get(attr) or ""
                got = twin.get(attr) or ""
                if got != want:
                    problems.append(f"{plant.alias} {attr} {got!r} expected {want!r}")
        else:
            for attr in ("sensor1", "sensor2"):
                got = twin.get(attr) or ""
                if got:
                    problems.append(f"{plant.alias} {attr}={got!r} but MQTT is {mqtt_fb}")
    problems += [f"{p.alias} ({p.alias_user}): {csv_path.name} line {p.line} has no MQTT plant {sn} in tables.xml"
                 for sn, p in sorted(plants.items()) if sn not in mqtt]
    return problems

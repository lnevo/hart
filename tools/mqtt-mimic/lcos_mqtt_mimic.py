#!/usr/bin/env python3
"""Local LCOS-style MQTT mimic for HART (occupancy + turnout status).

Serves a web UI on this Mac. Publishes to the same broker JMRI/LCOS use:

  track/sensor/{addr}    ACTIVE | INACTIVE     (occupancy and FB)
  track/turnout/{addr}   CLOSED | THROWN       (LCOS status; retain)

Never publishes track/cmd/turnout (that commands motors). TWOSENSOR plants
also flip FB N/R sensors so JMRI KnownState follows feedback.

  python3 tools/mqtt-mimic/lcos_mqtt_mimic.py
  python3 tools/mqtt-mimic/lcos_mqtt_mimic.py --mqtt-host <broker> --http-port 8765

Without --mqtt-host the broker comes from HART_MQTT_BROKER (hartlib.hosts).
  ./tools/mqtt-mimic/install_mimic_launchagent.sh   # stay-up LaunchAgent (survives Cursor quit)

Its parts beside it: mimic_records.py (the layout JSON's records), mimic_bus.py (the mosquitto clients and the
state heard from the broker) and mimic_http.py (the page and its API). build_mimic_web.py writes load_layout() for
the JMRI-hosted page.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices, level_devices, occupancy_bindings, paths, railroad, tables  # noqa: E402
from hartlib.levels import STAGING as STAGING_LEVEL  # noqa: E402
from hartlib.hosts import default as host_default, mqtt_broker, mqtt_port  # noqa: E402

# the mimic's parts beside it: the page's records, the MQTT clients, the web server
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mimic_bus import Bus, BusError, head_leaf, probe  # noqa: E402
from mimic_http import make_handler  # noqa: E402
from mimic_records import Block, Head, Layout, Turnout  # noqa: E402

ROOT = paths.REPO_ROOT
TABLES = paths.TABLES_XML
DEVICES = devices.MASTER
HEAD_CSV = paths.SIGNAL_HEAD_PLAN
HTML = Path(__file__).with_suffix(".html")
# Style and render code shared with the JMRI-hosted page; served here at /<name>.
SHARED_WEB = ROOT / "jmri" / "resources" / "jmri-web" / "mimic"
SHARED_FILES = {
    "/mimic.css": "text/css; charset=utf-8",
    "/mimic_view.js": "text/javascript; charset=utf-8",
}


SWITCH_TIPS = {
    1: "THROWN = Switch 5 / Plane (BOTTOM); CLOSED = LEFT",
    5: "THROWN = Track Scale (RIGHT); CLOSED = Track East Ext (BOTTOM)",
    33: "THROWN = Track Barn (BOTTOM); CLOSED = Track 31 / Track East Lead (LEFT)",
    37: "THROWN = Track K-2 (BOTTOM); CLOSED = Track Helix Inner (RIGHT)",
    39: "THROWN = Track K-1 (TOP); CLOSED = Track Helix Outer (RIGHT)",
}

# West → east along the modeled line. Empty map `cp` falls through to infer_plant.
PLANT_ORDER = [
    "Brick",
    "Plane",
    "Barn",
    "Engine House",
    "South Yard",
    "East End",
    "Princess",
    "Main",
    "Other",
]

# Tabs on the page. Staging runs on LCOS MQTT devices (M2T/M2S), set through MQTT feedback; the main and upper
# levels run on virtual JMRI devices (hartlib.level_devices) named in the device map, set in JMRI directly.
STAGING = "staging"
LEVELS = {2: "main", 3: "upper"}


def plant_rank(plant: str) -> int:
    """A plant's place in PLANT_ORDER; a plant not listed sorts after every listed one."""
    return PLANT_ORDER.index(plant) if plant in PLANT_ORDER else len(PLANT_ORDER)


class MimicError(Exception):
    """The layout cannot be loaded (a missing tables.xml, a device-map row the mimic cannot place) or no broker
    answers; the message says which."""


def pick_mqtt_host(explicit: str | None, port: int) -> str:
    """The first of --mqtt-host, HART_MQTT_BROKER, the hosts default and this machine that takes a connection on
    port; MimicError naming each one tried when none does."""
    hosts = []
    for h in (explicit, mqtt_broker(), host_default("HART_MQTT_BROKER"), "127.0.0.1"):
        if h and h not in hosts:
            hosts.append(h)
    for h in hosts:
        if probe(h, port):
            return h
    raise MimicError(
        f"No MQTT broker on port {port}. Tried: " + ", ".join(hosts)
        + "\nPass --mqtt-host or set HART_MQTT_BROKER."
    )


def _txt(el: ET.Element, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _addr(sysname: str, prefix: str) -> str | None:
    if sysname.startswith(prefix):
        return sysname[len(prefix) :]
    return None


class StagingSensor(NamedTuple):
    """An M2S sensor in tables.xml."""
    addr: str
    user_name: str
    comment: str
    system_name: str


def load_layout(levels: bool = True) -> Layout:
    """Staging from tables.xml and the repo CSVs; with `levels`, also the main and upper levels (load_levels)."""
    if not TABLES.is_file():
        raise MimicError(f"missing {TABLES}")
    root = tables.read(TABLES)
    cps = load_cps()
    sensors = _staging_sensors(root)
    by_user = {s.user_name: s.addr for s in sensors.values() if s.user_name}
    # a device's kind is its device-master row's (layer, role), never its name
    index = devices.index(DEVICES)
    blocks = _staging_blocks(sensors, index, cps)
    turnouts = _staging_turnouts(root, index, by_user, cps)
    heads = _staging_heads(cps)
    if not levels:
        return {"blocks": blocks, "turnouts": turnouts, "heads": heads}
    level = load_levels(root)
    return {
        "blocks": blocks + level["blocks"],
        "turnouts": turnouts + level["turnouts"],
        "heads": heads + level["heads"],
    }


def _staging_sensors(root: ET.Element) -> dict[str, StagingSensor]:
    """{address: sensor} for the LCOS MQTT sensors (M2S) in tables.xml."""
    sensors: dict[str, StagingSensor] = {}
    for el in root.findall(".//sensor"):
        sn = _txt(el, "systemName")
        addr = _addr(sn, "M2S")
        if addr:
            sensors[addr] = StagingSensor(addr, _txt(el, "userName"), _txt(el, "comment"), sn)
    return sensors


def _occupancy_names() -> dict[str, list[str]]:
    """{occupancy sensor user name: the blocks the CATS desks bind to it}, from the device master."""
    occ_names: dict[str, list[str]] = {}
    for row in occupancy_bindings.rows():
        un, name = row["occupancy_sensor_user_name"], row["block_user_name"]
        occ_names.setdefault(un, [])
        if name not in occ_names[un]:
            occ_names[un].append(name)
    return occ_names


def _staging_blocks(sensors: Mapping[str, StagingSensor], index: devices.Index,
                    cps: Mapping[str, Mapping[str, str]]) -> list[Block]:
    """The staging occupancy detectors, by plant then user name; a sensor with no device-master row is left out."""
    detectors = set(index.names("occupancy", roles=set(devices.ROLES) - {"spare"}))
    occ_names = _occupancy_names()
    blocks: list[Block] = []
    for addr, rec in sensors.items():
        un = rec.user_name
        if not any(index.has(layer, un) for layer in ("occupancy", "fb", "sensor")):
            # a Store not split yet can hold it: say so, and leave it out (hartlib.devices is the one source of kinds)
            print(f"lcos_mqtt_mimic: sensor {rec.system_name} ({un or 'no user name'}) in {paths.rel(TABLES)} has "
                  f"no row in {paths.rel(DEVICES)}; left out", file=sys.stderr)
            continue
        if un not in detectors:
            continue
        names = occ_names.get(un, [])
        label = " / ".join(names) if names else un
        blocks.append({
            "addr": addr,
            "label": label,
            "userName": un,
            "comment": rec.comment,
            "plant": _plant_for_block(label, rec.comment, un, cps),
            "level": STAGING,
            "name": rec.system_name,
        })
    blocks.sort(key=lambda b: (plant_rank(b["plant"]), b["userName"]))
    return blocks


def _staging_turnouts(root: ET.Element, index: devices.Index, by_user: Mapping[str, str],
                      cps: Mapping[str, Mapping[str, str]]) -> list[Turnout]:
    """The staging switches (M2T), by plant then number; one with no device-master row is left out."""
    switches = set(index.names("turnout", roles=("turnout",)))
    turnout_cp = cps.get("turnout") or {}
    turnouts: list[Turnout] = []
    for el in root.findall(".//turnout"):
        sn = _txt(el, "systemName")
        addr = _addr(sn, "M2T")
        if not addr:
            continue
        un = _txt(el, "userName")
        if not index.has("turnout", un):
            print(f"lcos_mqtt_mimic: turnout {sn} ({un or 'no user name'}) in {paths.rel(TABLES)} has no row in "
                  f"{paths.rel(DEVICES)}; left out", file=sys.stderr)
            continue
        if un not in switches:
            continue
        try:
            num = int(un.split()[-1])
        except ValueError:
            continue
        turnouts.append({
            "addr": addr,
            "label": un,
            "num": num,
            "plant": turnout_cp.get(un) or infer_plant(un),
            "feedback": (el.get("feedback") or "").upper(),
            "n_addr": by_user.get(el.get("sensor2") or ""),
            "r_addr": by_user.get(el.get("sensor1") or ""),
            "tip": SWITCH_TIPS.get(num, ""),
            "level": STAGING,
            "name": sn,
        })
    turnouts.sort(key=lambda t: (plant_rank(t["plant"]), t["num"]))
    return turnouts


def _staging_heads(cps: Mapping[str, Mapping[str, str]]) -> list[Head]:
    """The staging signal heads from the signal head plan, by plant, mast and topic leaf."""
    heads: list[Head] = []
    mast_cp = cps.get("mast") or {}
    if HEAD_CSV.is_file():
        with HEAD_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                mast = (row.get("mast_user_name") or "").strip()
                plant = mast_cp.get(mast) or infer_plant(mast)
                for h in (row.get("head_system_names") or "").split():
                    heads.append({"id": head_leaf(h), "systemName": h, "mast": mast, "plant": plant,
                                  "level": STAGING})
    heads.sort(key=lambda h: (plant_rank(h["plant"]), h["mast"], h["id"]))
    return heads


def load_levels(root: ET.Element, rr: railroad.Railroad | None = None) -> Layout:
    """Main and upper turnouts, block sensors and heads: the device map's virtual devices that tables.xml holds.

    Each record's `addr` is its JMRI system name and `virtual` is true, so the JMRI page sets it directly
    (no MQTT); a name without the virtual prefix stops the build. Grouped by control point, else by the area of
    the first switch in its name that has one ("Peninsula").
    """
    rr = rr or railroad.Railroad()
    dm = rr.device_map
    in_tables = {
        _txt(el, "systemName")
        for tag in ("turnout", "sensor", "signalhead")
        for el in root.iter(tag)
    }
    blocks_of: dict[str, list[str]] = {}
    for el in root.iter("block"):
        occ = _txt(el, "occupancysensor")
        name = _txt(el, "userName")
        if occ and name:
            blocks_of.setdefault(occ, []).append(name)

    region = {num: sw.cp or sw.area for num, sw in rr.main_upper_switches.items()}

    def virtual(r: railroad.DeviceRow, prefix: str) -> str:
        if not r.jmri_name.startswith(prefix):
            raise MimicError(f"{dm.path} line {r.line}: {r.user_name} is {r.jmri_name!r}, not a virtual "
                             f"{prefix}* device; the mimic sets only those directly")
        return r.jmri_name

    def group(r: railroad.DeviceRow) -> str:
        if r.cp:
            return first_place(r.cp)
        for num in re.findall(r"\d+[a-z]?", r.user_name):
            if region.get(num):
                return region[num]
        sw = re.search(r"\| Switch (\d+)", r.comment or "")     # a spur exit dwarf at a local switch (ADR-024)
        if sw and region.get(sw.group(1)):
            return region[sw.group(1)]
        raise MimicError(f"{dm.path} line {r.line}: {r.user_name} has no cp and names no switch with a region")

    def order(r: railroad.DeviceRow) -> tuple[object, ...]:
        return (r.level, railroad.natural(group(r)), railroad.natural(r.user_name))

    turnouts: list[Turnout] = []
    blocks: list[Block] = []
    heads: list[Head] = []
    for r in sorted(dm.turnouts.values(), key=order):
        if r.jmri_name not in in_tables:
            continue
        name = virtual(r, level_devices.TURNOUT_PREFIX)
        turnouts.append({
            "addr": name, "name": name, "label": r.user_name,
            "plant": group(r), "feedback": "DIRECT", "n_addr": None, "r_addr": None, "tip": "",
            "level": LEVELS[r.level], "virtual": True,
        })
    for r in sorted(dm.of("occupancy"), key=order):
        if r.jmri_name not in in_tables:
            continue
        names = blocks_of.get(r.user_name, [])
        name = virtual(r, level_devices.SENSOR_PREFIX)
        blocks.append({
            "addr": name, "name": name, "label": " / ".join(names) or r.user_name,
            "userName": r.user_name, "comment": "", "plant": group(r),
            "level": LEVELS[r.level], "virtual": True,
        })
    # a hidden virtual mast (a destination at a buffer stop) has no heads and no control point: nothing to show
    for r in sorted((m for m in dm.of("mast") if level_devices.HEAD.findall(m.jmri_name)), key=order):
        for h in level_devices.HEAD.findall(r.jmri_name):
            if h not in in_tables:
                continue
            heads.append({
                "id": head_leaf(h), "systemName": h, "mast": r.user_name, "plant": group(r),
                "level": LEVELS[r.level],
            })
    return {"blocks": blocks, "turnouts": turnouts, "heads": heads}


def first_place(cp: str) -> str:
    """The plant of a cp: the control point, or for a line block's list (the stations or control points it joins,
    its own level's first: build_device_map.line_cp) its first, so a block is grouped once, on its own level."""
    return cp.split(";")[0]


def infer_plant(name: str, cp: str = "") -> str:
    """Control point for mimic grouping (first_place of a list). An empty cp is filled from the public name."""
    if cp:
        return first_place(cp)
    blob = (name or "").lower()
    if blob.startswith("os eh") or blob.startswith("track eh") or blob.startswith("bs eh") or "engine house" in blob:
        return "Engine House"
    if "switch 9" in blob or "switch 11" in blob:
        return "Engine House"
    if "barn" in blob:
        return "Barn"
    if blob.startswith("os main") or blob.startswith("track main") or blob.startswith("bs main"):
        return "Main"
    if "princess" in blob or "mckees" in blob or blob.startswith("os k-") or blob.startswith("track k-"):
        return "Princess"
    if "east end" in blob or "east lead" in blob:
        return "East End"
    if "south yard" in blob or blob.startswith("os s-") or blob.startswith("track s-") or blob.startswith("bs s-"):
        return "South Yard"
    if blob.startswith("os w-") or blob.startswith("track w-") or blob.startswith("bs w-") or "brick" in blob:
        return "Brick"
    if "plane" in blob or "scale" in blob:
        return "Plane"
    return "Other"


def load_cps() -> dict[str, dict[str, str]]:
    """Staging's rows of the device master: user name (and an occupancy sensor's system name) -> its cp, by layer. An LCC
    alias (DCC Switch N) is grouped by its name alone (infer_plant), as the name map, which gave it no cp, had it."""
    turnout: dict[str, str] = {}
    occupancy: dict[str, str] = {}
    block: dict[str, str] = {}
    mast: dict[str, str] = {}
    if not DEVICES.is_file():
        return {"turnout": turnout, "occupancy": occupancy, "block": block, "mast": mast}
    for row in devices.load(DEVICES):
        if row.level != STAGING_LEVEL:      # a Store's level-less row (level None) is not staging's either
            continue
        layer, name = row.layer, row.user_name
        plant = infer_plant(name, "" if row.role == "lcc_alias" else devices.place(row))
        if layer == "turnout":
            turnout[name] = plant
        elif layer == "occupancy":
            occupancy[name] = plant
            if row.system_name:
                occupancy[row.system_name] = plant
        elif layer == "block":
            block[name] = plant
        elif layer == "mast":
            mast[name] = plant
    return {"turnout": turnout, "occupancy": occupancy, "block": block, "mast": mast}


def _plant_for_block(label: str, comment: str, uname: str, cps: Mapping[str, Mapping[str, str]]) -> str:
    occ = cps.get("occupancy") or {}
    blocks = cps.get("block") or {}
    if uname in occ:
        return occ[uname]
    for name in (label or "").split(" / "):
        name = name.strip()
        if name in blocks:
            return blocks[name]
        if name in occ:
            return occ[name]
    match = re.search(r"Block \d+-\d+", comment or "")
    if match and match.group(0) in occ:
        return occ[match.group(0)]
    return infer_plant(f"{label} {uname}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mqtt-host", default=None)
    ap.add_argument("--http-port", type=int, default=8765)
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()

    port = mqtt_port()

    for page in (HTML, *(SHARED_WEB / name.lstrip("/") for name in SHARED_FILES)):
        if not page.is_file():
            raise SystemExit(f"missing UI {page}")

    try:
        host = pick_mqtt_host(args.mqtt_host, port)
        # This server talks only MQTT, so it cannot set the main and upper levels' virtual JMRI devices.
        layout = load_layout(levels=False)
        bus = Bus(host, port)
    except devices.DevicesError as exc:      # a bad row anywhere in the master stops the load, naming file, line and row
        raise SystemExit(f"lcos_mqtt_mimic.py: the device master cannot be used: {exc}") from exc
    except (MimicError, BusError) as exc:
        raise SystemExit(str(exc)) from exc
    bus.start()
    html = HTML.read_bytes()
    httpd = ThreadingHTTPServer((args.bind, args.http_port), make_handler(layout, bus, html, SHARED_WEB, SHARED_FILES))
    url = f"http://127.0.0.1:{args.http_port}/" if args.bind in ("127.0.0.1", "0.0.0.0") else f"http://{args.bind}:{args.http_port}/"
    print(f"LCOS mimic UI  {url}", flush=True)
    print(f"MQTT broker    {host}:{port}", flush=True)
    print(f"Turnouts {len(layout['turnouts'])}  blocks {len(layout['blocks'])}  heads {len(layout['heads'])}", flush=True)
    print("Publishes track/sensor + track/turnout only (no track/cmd). Ctrl-C to stop.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        bus.stop()
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

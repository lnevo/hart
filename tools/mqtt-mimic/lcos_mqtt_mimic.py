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
"""

from __future__ import annotations

import argparse
import csv
import json
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple, NotRequired, TypedDict
from urllib.parse import urlparse

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices, level_devices, occupancy_bindings, paths, railroad, tables  # noqa: E402
from hartlib.hosts import default as host_default, mqtt_broker, mqtt_port  # noqa: E402

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

# Set in main(): importers such as build_mimic_web.py never need the broker port.
MQTT_PORT = 1883
_MOSQUITTO = (
    "/opt/local/bin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    r"C:\Program Files\mosquitto",
    r"C:\Program Files (x86)\mosquitto",
)

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


def _which(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for d in _MOSQUITTO:
        p = Path(d) / name
        if p.is_file():
            return str(p)
        p = Path(d) / (name + ".exe")
        if p.is_file():
            return str(p)
    raise SystemExit(f"{name} not found. Install mosquitto clients.")


def _probe(host: str) -> bool:
    try:
        s = socket.create_connection((host, MQTT_PORT), timeout=0.8)
        s.close()
        return True
    except OSError:
        return False


def pick_mqtt_host(explicit: str | None) -> str:
    hosts = []
    for h in (explicit, mqtt_broker(), host_default("HART_MQTT_BROKER"), "127.0.0.1"):
        if h and h not in hosts:
            hosts.append(h)
    for h in hosts:
        if _probe(h):
            return h
    raise SystemExit(
        f"No MQTT broker on port {MQTT_PORT}. Tried: " + ", ".join(hosts)
        + "\nPass --mqtt-host or set HART_MQTT_BROKER."
    )


def _txt(el: ET.Element, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _addr(sysname: str, prefix: str) -> str | None:
    if sysname.startswith(prefix):
        return sysname[len(prefix) :]
    return None


def _head_leaf(name: str) -> str:
    """MQTT topic leaf: packed digits (IH432 → 432)."""
    name = (name or "").strip()
    if len(name) > 2 and name[:2].upper() == "IH" and name[2:].isdigit():
        return name[2:]
    return name


class Block(TypedDict):
    """An occupancy detector on the page (JSON). A virtual one (main, upper) is set in JMRI directly."""
    addr: str
    label: str
    userName: str
    comment: str
    plant: str
    level: str
    name: str
    virtual: NotRequired[bool]


class Turnout(TypedDict):
    """A switch on the page (JSON): its feedback sensors' addresses when it has two (TWOSENSOR)."""
    addr: str
    label: str
    num: NotRequired[int]       # staging only: the number in its user name
    plant: str
    feedback: str
    n_addr: str | None
    r_addr: str | None
    tip: str
    level: str
    name: str
    virtual: NotRequired[bool]


class Head(TypedDict):
    """A signal head on the page (JSON), by its MQTT topic leaf."""
    id: str
    systemName: str
    mast: str
    plant: str
    level: str


class Layout(TypedDict):
    blocks: list[Block]
    turnouts: list[Turnout]
    heads: list[Head]


class StagingSensor(NamedTuple):
    """An M2S sensor in tables.xml."""
    addr: str
    user_name: str
    comment: str
    system_name: str


def load_layout(levels: bool = True) -> Layout:
    """Staging from tables.xml and the repo CSVs; with `levels`, also the main and upper levels (load_levels)."""
    if not TABLES.is_file():
        raise SystemExit(f"missing {TABLES}")
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
                    heads.append({"id": _head_leaf(h), "systemName": h, "mast": mast, "plant": plant,
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
            raise SystemExit(f"{dm.path} line {r.line}: {r.user_name} is {r.jmri_name!r}, not a virtual "
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
        raise SystemExit(f"{dm.path} line {r.line}: {r.user_name} has no cp and names no switch with a region")

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
                "id": _head_leaf(h), "systemName": h, "mast": r.user_name, "plant": group(r),
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
        if row["level"] != railroad.STAGING_LEVEL:
            continue
        layer, name = row["layer"], row["user_name"]
        plant = infer_plant(name, "" if row["role"] == "lcc_alias" else devices.place(row))
        if layer == "turnout":
            turnout[name] = plant
        elif layer == "occupancy":
            occupancy[name] = plant
            if row["system_name"]:
                occupancy[row["system_name"]] = plant
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


class Bus:
    def __init__(self, host: str):
        self.host = host
        self.pub_bin = _which("mosquitto_pub")
        self.sub_bin = _which("mosquitto_sub")
        self.sensors: dict[str, str] = {}
        self.turnouts: dict[str, str] = {}
        self.heads: dict[str, str] = {}
        self.connected = False
        self.subs: list[queue.Queue] = []
        self.lock = threading.Lock()
        self._stop = threading.Event()

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "mqtt": {"host": self.host, "connected": self.connected},
                "sensors": dict(self.sensors),
                "turnouts": dict(self.turnouts),
                "heads": dict(self.heads),
            }

    def emit(self, event: dict) -> None:
        with self.lock:
            subs = list(self.subs)
        dead = []
        payload = json.dumps(event)
        for q in subs:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        if dead:
            with self.lock:
                self.subs = [s for s in self.subs if s not in dead]

    def add_sub(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=200)
        with self.lock:
            self.subs.append(q)
        return q

    def drop_sub(self, q: queue.Queue) -> None:
        with self.lock:
            self.subs = [s for s in self.subs if s is not q]

    def publish(self, topic: str, payload: str) -> None:
        subprocess.check_call(
            [self.pub_bin, "-h", self.host, "-p", str(MQTT_PORT), "-r", "-t", topic, "-m", payload],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def set_occupancy(self, addr: str, state: str) -> None:
        state = state.upper()
        if state not in ("ACTIVE", "INACTIVE"):
            raise ValueError("occupancy must be ACTIVE or INACTIVE")
        self.publish(f"track/sensor/{addr}", state)

    def set_turnout(self, layout: Layout, addr: str, state: str) -> None:
        state = state.upper()
        if state not in ("CLOSED", "THROWN"):
            raise ValueError("turnout must be CLOSED or THROWN")
        rec = next((t for t in layout["turnouts"] if t["addr"] == addr), None)
        if rec is None:
            raise ValueError(f"unknown turnout {addr}")
        thrown = state == "THROWN"
        if rec["n_addr"] and rec["r_addr"]:
            self.publish(f"track/sensor/{rec['n_addr']}", "INACTIVE" if thrown else "ACTIVE")
            self.publish(f"track/sensor/{rec['r_addr']}", "ACTIVE" if thrown else "INACTIVE")
        self.publish(f"track/turnout/{addr}", state)

    def clear_occupancy(self, layout: Layout) -> None:
        for b in layout["blocks"]:
            self.set_occupancy(b["addr"], "INACTIVE")

    def _on_line(self, line: str) -> None:
        line = line.strip()
        if not line or " " not in line or line.lower().startswith("timed out"):
            return
        topic, payload = line.split(" ", 1)
        payload = payload.strip()
        with self.lock:
            if topic.startswith("track/sensor/"):
                addr = topic.rsplit("/", 1)[-1]
                self.sensors[addr] = payload
                kind = "sensor"
            elif topic.startswith("track/turnout/"):
                addr = topic.rsplit("/", 1)[-1]
                self.turnouts[addr] = payload
                kind = "turnout"
            elif topic.startswith("track/signalhead/"):
                addr = _head_leaf(topic.rsplit("/", 1)[-1])
                self.heads[addr] = payload
                kind = "head"
            else:
                return
        self.emit({"type": kind, "addr": addr, "payload": payload, "topic": topic})

    def loop_sub(self) -> None:
        cmd = [
            self.sub_bin,
            "-h",
            self.host,
            "-p",
            str(MQTT_PORT),
            "-v",
            "-t",
            "track/sensor/#",
            "-t",
            "track/turnout/#",
            "-t",
            "track/signalhead/#",
        ]
        try:
            while not self._stop.is_set():
                self._subscribe_once(cmd)
                if self._stop.is_set():
                    break
                time.sleep(1)
        finally:            # however the thread ends, the page must not keep showing a live connection
            if self.connected:
                self.connected = False
                self.emit({"type": "mqtt", "connected": False, "error": "the subscriber stopped"})

    def _subscribe_once(self, cmd: list[str]) -> None:
        """Run mosquitto_sub until it ends; a client that cannot start or stop is a disconnected event."""
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except (OSError, subprocess.SubprocessError) as e:   # no mosquitto_sub
            self.connected = False
            self.emit({"type": "mqtt", "connected": False, "error": str(e)})
            return
        self.connected = True
        self.emit({"type": "mqtt", "connected": True, "host": self.host})
        assert proc.stdout is not None
        for line in proc.stdout:
            if self._stop.is_set():
                break
            self._read_line(line)
        try:
            proc.wait(timeout=2)
        except subprocess.SubprocessError as e:              # it did not stop in time
            self.connected = False
            self.emit({"type": "mqtt", "connected": False, "error": str(e)})

    def _read_line(self, line: str) -> None:
        """One subscriber line; a line that cannot be read is logged and shown as a warning, and reading goes on."""
        try:
            self._on_line(line)
        except Exception as e:  # noqa: BLE001  one bad message must not stop the subscriber; it is shown, not hidden
            print(f"lcos_mqtt_mimic: cannot read {line.strip()!r}: {e!r}", file=sys.stderr)
            self.emit({"type": "warning", "line": line.strip(), "error": repr(e)})

    def start(self) -> None:
        threading.Thread(target=self.loop_sub, name="mqtt-sub", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


def make_handler(layout: Layout, bus: Bus, html: bytes) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            if "GET /api/events" in (fmt % args):
                return
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def _json(self, code: int, obj) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            return json.loads(raw.decode() or "{}")

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return
            if path in SHARED_FILES:
                body = (SHARED_WEB / path.lstrip("/")).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", SHARED_FILES[path])
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/layout":
                self._json(200, layout)
                return
            if path == "/api/state":
                self._json(200, bus.snapshot())
                return
            if path == "/api/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                q = bus.add_sub()
                try:
                    self.wfile.write(b"data: " + json.dumps({"type": "hello"}).encode() + b"\n\n")
                    self.wfile.flush()
                    while True:
                        try:
                            msg = q.get(timeout=20)
                            self.wfile.write(b"data: " + msg.encode() + b"\n\n")
                            self.wfile.flush()
                        except queue.Empty:
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    bus.drop_sub(q)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                body = self._read_json()
                if path == "/api/occupancy":
                    bus.set_occupancy(str(body["addr"]), str(body["state"]))
                    self._json(200, {"ok": True})
                    return
                if path == "/api/turnout":
                    bus.set_turnout(layout, str(body["addr"]), str(body["state"]))
                    self._json(200, {"ok": True})
                    return
                if path == "/api/occupancy/clear":
                    bus.clear_occupancy(layout)
                    self._json(200, {"ok": True})
                    return
            except (KeyError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as e:
                self._json(400, {"ok": False, "error": str(e)})
                return
            self.send_error(404)

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mqtt-host", default=None)
    ap.add_argument("--http-port", type=int, default=8765)
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()

    global MQTT_PORT
    MQTT_PORT = mqtt_port()

    for page in (HTML, *(SHARED_WEB / name.lstrip("/") for name in SHARED_FILES)):
        if not page.is_file():
            raise SystemExit(f"missing UI {page}")

    host = pick_mqtt_host(args.mqtt_host)
    # This server talks only MQTT, so it cannot set the main and upper levels' virtual JMRI devices.
    try:
        layout = load_layout(levels=False)
    except devices.DevicesError as exc:      # a bad row anywhere in the master stops the load, naming file, line and row
        raise SystemExit(f"lcos_mqtt_mimic.py: the device master cannot be used: {exc}") from None
    bus = Bus(host)
    bus.start()
    html = HTML.read_bytes()
    httpd = ThreadingHTTPServer((args.bind, args.http_port), make_handler(layout, bus, html))
    url = f"http://127.0.0.1:{args.http_port}/" if args.bind in ("127.0.0.1", "0.0.0.0") else f"http://{args.bind}:{args.http_port}/"
    print(f"LCOS mimic UI  {url}", flush=True)
    print(f"MQTT broker    {host}:{MQTT_PORT}", flush=True)
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

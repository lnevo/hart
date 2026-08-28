#!/usr/bin/env python3
"""Local LCOS-style MQTT mimic for HART (occupancy + turnout status).

Serves a web UI on this Mac. Publishes to the same broker JMRI/LCOS use:

  track/sensor/{addr}    ACTIVE | INACTIVE     (occupancy and FB)
  track/turnout/{addr}   CLOSED | THROWN       (LCOS status; retain)

Never publishes track/cmd/turnout (that commands motors). TWOSENSOR plants
also flip FB N/R sensors so JMRI KnownState follows feedback.

  python3 cats/scripts/lcos_mqtt_mimic.py
  python3 cats/scripts/lcos_mqtt_mimic.py --mqtt-host 192.168.137.2 --http-port 8765
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "jmri" / "layouts" / "hart" / "output" / "tables.xml"
NAME_MAP = ROOT / "jmri" / "layouts" / "hart" / "data" / "public_name_map.csv"
OCC_CSV = ROOT / "cats" / "data" / "occupancy_bindings.csv"
HEAD_CSV = ROOT / "cats" / "data" / "signal_head_plan.csv"
HTML = Path(__file__).with_suffix(".html")

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
    5: "THROWN = OS Scale (RIGHT); CLOSED = OS East Main Ext (BOTTOM)",
    33: "THROWN = OS Barn (BOTTOM); CLOSED = OS 31 / OS East Lead (LEFT)",
    37: "THROWN = OS McKeesport (BOTTOM); CLOSED = OS K-2 (RIGHT)",
    39: "THROWN = OS McKees Rocks (TOP); CLOSED = OS K-1 (RIGHT)",
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
    env = (os.environ.get("MQTT_HOST") or os.environ.get("HART_MQTT_HOST") or "").strip()
    hosts = []
    for h in (explicit, env, "192.168.137.2", "minipc-e5h6x.local", "127.0.0.1"):
        if h and h not in hosts:
            hosts.append(h)
    for h in hosts:
        if _probe(h):
            return h
    raise SystemExit(
        "No MQTT broker on port 1883. Tried: " + ", ".join(hosts)
        + "\nPass --mqtt-host or set MQTT_HOST."
    )


def _txt(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _addr(sysname: str, prefix: str) -> str | None:
    if sysname.startswith(prefix):
        return sysname[len(prefix) :]
    return None


def load_layout() -> dict:
    if not TABLES.is_file():
        raise SystemExit(f"missing {TABLES}")
    root = ET.parse(TABLES).getroot()
    cps = load_cps()

    sensors: dict[str, dict] = {}
    by_user: dict[str, str] = {}
    for el in root.findall(".//sensor"):
        sn = _txt(el, "systemName")
        addr = _addr(sn, "M2S")
        if not addr:
            continue
        un = _txt(el, "userName")
        comment = _txt(el, "comment")
        rec = {"addr": addr, "userName": un, "comment": comment, "systemName": sn}
        sensors[addr] = rec
        if un:
            by_user[un] = addr

    occ_names: dict[str, list[str]] = {}
    if OCC_CSV.is_file():
        with OCC_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                un = (row.get("occupancy_sensor_user_name") or "").strip()
                name = (row.get("block_user_name") or "").strip()
                if un and name:
                    occ_names.setdefault(un, [])
                    if name not in occ_names[un]:
                        occ_names[un].append(name)

    blocks = []
    for addr, rec in sensors.items():
        un = rec["userName"]
        if not un.startswith("BS "):
            continue
        names = occ_names.get(un, [])
        label = " / ".join(names) if names else un
        plant = _plant_for_block(label, rec["comment"], un, cps)
        blocks.append(
            {
                "addr": addr,
                "label": label,
                "userName": un,
                "comment": rec["comment"],
                "plant": plant,
            }
        )
    blocks.sort(key=lambda b: (PLANT_ORDER.index(b["plant"]) if b["plant"] in PLANT_ORDER else 99, b["userName"]))

    turnouts = []
    turnout_cp = cps.get("turnout") or {}
    for el in root.findall(".//turnout"):
        sn = _txt(el, "systemName")
        addr = _addr(sn, "M2T")
        if not addr:
            continue
        un = _txt(el, "userName")
        if not un.startswith("Switch "):
            continue
        try:
            num = int(un.split()[-1])
        except ValueError:
            continue
        fb = (el.get("feedback") or "").upper()
        n_name = el.get("sensor2") or ""
        r_name = el.get("sensor1") or ""
        n_addr = by_user.get(n_name)
        r_addr = by_user.get(r_name)
        plant = turnout_cp.get(un) or infer_plant(un)
        turnouts.append(
            {
                "addr": addr,
                "label": un,
                "num": num,
                "plant": plant,
                "feedback": fb,
                "n_addr": n_addr,
                "r_addr": r_addr,
                "tip": SWITCH_TIPS.get(num, ""),
            }
        )
    turnouts.sort(key=lambda t: (PLANT_ORDER.index(t["plant"]) if t["plant"] in PLANT_ORDER else 99, t["num"]))

    heads = []
    mast_cp = cps.get("mast") or {}
    if HEAD_CSV.is_file():
        with HEAD_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                mast = (row.get("mast_user_name") or "").strip()
                plant = mast_cp.get(mast) or infer_plant(mast)
                for h in (row.get("head_system_names") or "").split():
                    heads.append({"id": h, "mast": mast, "plant": plant})
    heads.sort(
        key=lambda h: (
            PLANT_ORDER.index(h["plant"]) if h["plant"] in PLANT_ORDER else 99,
            h["mast"],
            h["id"],
        )
    )

    return {"blocks": blocks, "turnouts": turnouts, "heads": heads}


def infer_plant(name: str, cp: str = "") -> str:
    """Control point for mimic grouping. Empty map cp is filled from the public name."""
    if cp:
        return cp
    blob = (name or "").lower()
    if blob.startswith("os eh") or blob.startswith("bs eh") or "engine house" in blob:
        return "Engine House"
    if "switch 9" in blob or "switch 11" in blob:
        return "Engine House"
    if "barn" in blob:
        return "Barn"
    if blob.startswith("os main") or blob.startswith("bs main"):
        return "Main"
    if "princess" in blob or "mckees" in blob or blob.startswith("os k-"):
        return "Princess"
    if "east end" in blob or "east lead" in blob:
        return "East End"
    if "south yard" in blob or blob.startswith("os s-") or blob.startswith("bs s-"):
        return "South Yard"
    if blob.startswith("os w-") or blob.startswith("bs w-") or "brick" in blob:
        return "Brick"
    if "plane" in blob or "scale" in blob:
        return "Plane"
    return "Other"


def load_cps() -> dict[str, dict[str, str]]:
    """Identity rows from public_name_map.csv: name/hardware → cp."""
    turnout: dict[str, str] = {}
    occupancy: dict[str, str] = {}
    block: dict[str, str] = {}
    mast: dict[str, str] = {}
    if not NAME_MAP.is_file():
        return {"turnout": turnout, "occupancy": occupancy, "block": block, "mast": mast}
    with NAME_MAP.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            layer = (row.get("layer") or "").strip()
            current = (row.get("current") or "").strip()
            proposed = (row.get("proposed") or "").strip()
            if current != proposed or not proposed:
                continue
            if proposed.endswith(" alias"):
                continue
            plant = infer_plant(proposed, (row.get("cp") or "").strip())
            hardware = (row.get("hardware") or "").strip()
            if layer == "turnout":
                turnout[proposed] = plant
            elif layer == "occupancy":
                occupancy[proposed] = plant
                for token in hardware.split():
                    occupancy[token] = plant
            elif layer == "block":
                block[proposed] = plant
            elif layer == "mast":
                mast[proposed] = plant
    return {"turnout": turnout, "occupancy": occupancy, "block": block, "mast": mast}


def _plant_for_block(label: str, comment: str, uname: str, cps: dict[str, dict[str, str]]) -> str:
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
            [self.pub_bin, "-h", self.host, "-r", "-t", topic, "-m", payload],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def set_occupancy(self, addr: str, state: str) -> None:
        state = state.upper()
        if state not in ("ACTIVE", "INACTIVE"):
            raise ValueError("occupancy must be ACTIVE or INACTIVE")
        self.publish(f"track/sensor/{addr}", state)

    def set_turnout(self, layout: dict, addr: str, state: str) -> None:
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

    def clear_occupancy(self, layout: dict) -> None:
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
                addr = topic.rsplit("/", 1)[-1]
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
            "-v",
            "-t",
            "track/sensor/#",
            "-t",
            "track/turnout/#",
            "-t",
            "track/signalhead/#",
        ]
        while not self._stop.is_set():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                self.connected = True
                self.emit({"type": "mqtt", "connected": True, "host": self.host})
                assert proc.stdout is not None
                for line in proc.stdout:
                    if self._stop.is_set():
                        break
                    self._on_line(line)
                proc.wait(timeout=2)
            except Exception as e:
                self.connected = False
                self.emit({"type": "mqtt", "connected": False, "error": str(e)})
            if self._stop.is_set():
                break
            time.sleep(1)

    def start(self) -> None:
        threading.Thread(target=self.loop_sub, name="mqtt-sub", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


def make_handler(layout: dict, bus: Bus, html: bytes):
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

    if not HTML.is_file():
        raise SystemExit(f"missing UI {HTML}")

    host = pick_mqtt_host(args.mqtt_host)
    layout = load_layout()
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

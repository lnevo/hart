"""The mimic's MQTT side: the mosquitto clients it runs, and the state it has heard from the broker.

Bus publishes LCOS-style status (track/sensor, track/turnout, retained) through mosquitto_pub and follows
track/sensor, track/turnout and track/signalhead through one mosquitto_sub, passing each change to the page's event
streams. It never publishes track/cmd/turnout (that commands motors).
"""
from __future__ import annotations

import json
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TypedDict

from mimic_records import Layout

# where the mosquitto clients are when they are not on PATH
_MOSQUITTO = (
    "/opt/local/bin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    r"C:\Program Files\mosquitto",
    r"C:\Program Files (x86)\mosquitto",
)
SUBSCRIBED = ("track/sensor/#", "track/turnout/#", "track/signalhead/#")
WAIT_GRACE = 2.0    # seconds a started subscriber must keep running before the page shows it waiting for traffic
_TOPIC_PREFIXES = tuple(t.removesuffix("#") for t in SUBSCRIBED)

Event = dict[str, object]     # one message to the page's event stream (JSON)


class BusError(Exception):
    """A mosquitto client the mimic needs is not installed; the message names it."""


class Connection(TypedDict):
    host: str
    connected: bool
    waiting: bool       # the subscriber runs but has passed on no message yet (a quiet broker): neither up nor down
    error: str          # why it is down, "" when it is not


class State(TypedDict):
    """What the broker has said so far (/api/state): each sensor's, turnout's and head's last payload by address."""
    mqtt: Connection
    sensors: dict[str, str]
    turnouts: dict[str, str]
    heads: dict[str, str]


def head_leaf(name: str) -> str:
    """MQTT topic leaf: packed digits (IH432 → 432)."""
    name = (name or "").strip()
    if len(name) > 2 and name[:2].upper() == "IH" and name[2:].isdigit():
        return name[2:]
    return name


def _which(name: str) -> str:
    """The path of mosquitto client `name`: on PATH, else in one of _MOSQUITTO. BusError when it is in neither."""
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
    raise BusError(f"{name} not found. Install mosquitto clients.")


def is_message(line: str) -> bool:
    """Whether a mosquitto_sub -v line is a message on one of SUBSCRIBED (not the client's own output, such as an
    error): its first word is a subscribed topic, with or without a payload (a cleared retained topic has none)."""
    words = line.split(maxsplit=1)
    return bool(words) and words[0].startswith(_TOPIC_PREFIXES)


def probe(host: str, port: int) -> bool:
    """Whether something accepts a TCP connection on host:port within 0.8 s."""
    try:
        s = socket.create_connection((host, port), timeout=0.8)
        s.close()
        return True
    except OSError:
        return False


class Bus:
    """The broker at host:port, as the page sees it: last payloads, the connection, and the event streams."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.pub_bin = _which("mosquitto_pub")
        self.sub_bin = _which("mosquitto_sub")
        self.sensors: dict[str, str] = {}
        self.turnouts: dict[str, str] = {}
        self.heads: dict[str, str] = {}
        self.connected = False      # True only once the running subscriber has passed on a message
        self.waiting = False        # True while a running subscriber has passed on nothing yet (WAIT_GRACE)
        self._error = ""            # why the subscriber is not connected, as last shown on the page
        self.subs: list[queue.Queue[str]] = []
        self.lock = threading.Lock()
        self._stop = threading.Event()

    def snapshot(self) -> State:
        with self.lock:
            return {
                "mqtt": {"host": self.host, "connected": self.connected, "waiting": self.waiting,
                         "error": self._error},
                "sensors": dict(self.sensors),
                "turnouts": dict(self.turnouts),
                "heads": dict(self.heads),
            }

    def emit(self, event: Event) -> None:
        """Send event to every event stream; a stream whose queue is full is dropped."""
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

    def add_sub(self) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue(maxsize=200)
        with self.lock:
            self.subs.append(q)
        return q

    def drop_sub(self, q: queue.Queue[str]) -> None:
        with self.lock:
            self.subs = [s for s in self.subs if s is not q]

    def publish(self, topic: str, payload: str) -> None:
        subprocess.check_call(
            [self.pub_bin, "-h", self.host, "-p", str(self.port), "-r", "-t", topic, "-m", payload],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def set_occupancy(self, addr: str, state: str) -> None:
        state = state.upper()
        if state not in ("ACTIVE", "INACTIVE"):
            raise ValueError("occupancy must be ACTIVE or INACTIVE")
        self.publish(f"track/sensor/{addr}", state)

    def set_turnout(self, layout: Layout, addr: str, state: str) -> None:
        """A turnout's LCOS status, and for a TWOSENSOR one its N and R feedback sensors first."""
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
        """One `topic payload` line of mosquitto_sub -v: the state it sets, passed on as an event."""
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
                addr = head_leaf(topic.rsplit("/", 1)[-1])
                self.heads[addr] = payload
                kind = "head"
            else:
                return
        self.emit({"type": kind, "addr": addr, "payload": payload, "topic": topic})

    def sub_command(self) -> list[str]:
        """The mosquitto_sub command line that follows SUBSCRIBED, one `topic payload` line per message."""
        topics = [w for t in SUBSCRIBED for w in ("-t", t)]
        return [self.sub_bin, "-h", self.host, "-p", str(self.port), "-v", *topics]

    def _set_connected(self, connected: bool, error: str = "") -> None:
        """Record the subscriber's state and send it to the page when it changes, or when the reason it is down does."""
        with self.lock:
            changed = (connected != self.connected or self.waiting
                       or (not connected and error != self._error))
            self.connected, self.waiting, self._error = connected, False, error
        if not changed:
            return
        if connected:
            self.emit({"type": "mqtt", "connected": True, "host": self.host})
        else:
            self.emit({"type": "mqtt", "connected": False, "error": error})

    def _set_waiting(self) -> None:
        """The subscriber has run WAIT_GRACE without a message or an exit: the broker took it and is quiet. The page
        shows it waiting (neither up nor down) until the first message or the exit."""
        with self.lock:
            changed = not (self.connected or self.waiting)
            if changed:
                self.waiting, self._error = True, ""
        if changed:
            self.emit({"type": "mqtt", "connected": False, "waiting": True, "host": self.host})

    def loop_sub(self) -> None:
        """Run the subscriber until stop(), starting it again a second after it ends."""
        cmd = self.sub_command()
        try:
            while not self._stop.is_set():
                self._subscribe_once(cmd)
                if self._stop.is_set():
                    break
                time.sleep(1)
        finally:            # a thread that ends without stop() must not leave the page showing a live connection
            if not self._stop.is_set():
                self._set_connected(False, "the subscriber stopped")

    def _subscribe_once(self, cmd: list[str]) -> None:
        """Run mosquitto_sub until it ends. It counts as connected from its first message; when it exits, the page is
        told so with its exit code and the last thing it printed that was not a message (its error, if any)."""
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except (OSError, subprocess.SubprocessError) as e:   # no mosquitto_sub
            self._set_connected(False, str(e))
            return
        assert proc.stdout is not None
        said = ""
        # A subscriber the broker refuses exits at once and keeps its error shown; one that keeps running is waiting.
        def still_running() -> None:
            if proc.poll() is None:
                self._set_waiting()
        quiet = threading.Timer(WAIT_GRACE, still_running)
        quiet.daemon = True
        quiet.start()
        code: int | None = None
        at_end = False      # its output closed: it is exiting by itself, with its own exit code
        try:
            for line in proc.stdout:
                if self._stop.is_set():
                    break
                if is_message(line):
                    if not self.connected:
                        self._set_connected(True)
                elif line.strip():
                    said = line.strip()
                self._read_line(line)
            else:
                at_end = True
        finally:            # however the reading ends (stop, exit or an error), the client ends too, so only one runs
            quiet.cancel()
            if not at_end and proc.poll() is None:
                proc.terminate()
            try:
                code = proc.wait(timeout=2)
            except subprocess.TimeoutExpired as e:          # it did not stop in time: kill it
                proc.kill()
                self._set_connected(False, str(e))
        if code is None:
            return
        if not self._stop.is_set():
            self._set_connected(False, f"mosquitto_sub exited ({code}): {said}" if said
                                else f"mosquitto_sub exited ({code})")

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

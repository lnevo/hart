"""The mosquitto client command lines the MQTT tools run, with their failures raised as MosquittoError.

subscribe reads the retained messages of a topic filter until mosquitto_sub's -W wait ends. set_retained sets or
clears one retained topic. Both take the command runner as an argument (`run`), so a test passes a fake one;
nothing here connects to a broker on import.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from typing import NamedTuple

SUB = "mosquitto_sub"
PUB = "mosquitto_pub"
# mosquitto_sub's exit status and message when its -W wait ends: the normal end of a read of retained messages.
TIMED_OUT_STATUS = 27
TIMED_OUT_TEXT = "timed out"

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


class MosquittoError(RuntimeError):
    """A mosquitto client could not be started or exited with an error: the message names the command and topic."""


class Message(NamedTuple):
    """One message mosquitto_sub -v printed: its topic and payload."""

    topic: str
    payload: str


def run_command(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run one mosquitto client and capture its output. MosquittoError when it cannot be started."""
    try:
        return subprocess.run(list(cmd), capture_output=True, text=True, check=False)
    except OSError as exc:
        raise MosquittoError(f"{cmd[0]} could not be started (are the mosquitto clients installed?): {exc}") from exc


def _timed_out(proc: subprocess.CompletedProcess[str]) -> bool:
    # the client's own notice is a line of its own; "Connection timed out" from the network is a failure
    lines = f"{proc.stdout or ''}\n{proc.stderr or ''}".lower().splitlines()
    return proc.returncode == TIMED_OUT_STATUS or TIMED_OUT_TEXT in (line.strip() for line in lines)


def _failure(proc: subprocess.CompletedProcess[str], what: str) -> MosquittoError:
    detail = (proc.stderr or proc.stdout or "").strip() or "no message"
    return MosquittoError(f"{what} exited {proc.returncode}: {detail}")


def parse_messages(out: str) -> list[Message]:
    """The (topic, payload) lines of mosquitto_sub -v output; blank lines and its "Timed out" line are not messages."""
    rows: list[Message] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or " " not in line or line.lower().startswith(TIMED_OUT_TEXT):
            continue
        topic, payload = line.split(" ", 1)
        rows.append(Message(topic, payload.strip()))
    return rows


def subscribe(host: str, topic: str, *, wait: int = 1, count: int | None = None,
              run: Runner = run_command) -> list[Message]:
    """The messages on `topic` (a filter) at `host` within `wait` seconds, at most `count` of them when given.
    The wait running out ends the read; any other failure (no broker, a refused connection) is MosquittoError."""
    cmd = [SUB, "-h", host, "-t", topic, "-v", "-W", str(wait)]
    if count is not None:
        cmd += ["-C", str(count)]
    proc = run(cmd)
    if proc.returncode != 0 and not _timed_out(proc):
        raise _failure(proc, f"{SUB} {topic} on {host}")
    return parse_messages(proc.stdout or "")


def set_retained(host: str, topic: str, payload: str | None, *, run: Runner = run_command) -> None:
    """Retain `payload` on `topic` at `host`; None clears the topic's retained message. MosquittoError on a failure."""
    cmd = [PUB, "-h", host, "-t", topic] + (["-n"] if payload is None else ["-m", payload]) + ["-r"]
    proc = run(cmd)
    if proc.returncode != 0:
        raise _failure(proc, f"{PUB} {topic} on {host}")

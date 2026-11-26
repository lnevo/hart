#!/usr/bin/env python3
"""Clear MQTT junk that must never be on this broker.

1) track/cmd/sensor/#          — sensors are status-only (never commanded)
2) bare "{addr}" topics        — ACTIVE|INACTIVE at broker root (bug from
   MqttSensor.setKnownState with an empty JMRI send-topic template)
3) _discard/cmd/sensor/#       — retired 11.3 sink retain
4) track/signalhead/IH<digits> — legacy leaf; live is track/signalhead/<packed>
5) track/sensor/<non-digits>   — JMRI auto-creates M2SBlock 1-1 from those topics

Does not touch track/sensor/{addr}, track/turnout/{addr}, or packed
track/signalhead/<digits> status/set retain.

    python3 tools/mqtt/clear_mqtt_cmd_sensor_retain.py

Broker: HART_MQTT_BROKER (hartlib.hosts), default the Pi.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib.hosts import mqtt_broker  # noqa: E402

MQTT_HOST = mqtt_broker()


def _sub(topic: str, wait: str = "1") -> list[tuple[str, str]]:
    try:
        out = subprocess.check_output(
            ["mosquitto_sub", "-h", MQTT_HOST, "-t", topic, "-v", "-W", wait],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        out = e.output or ""
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or " " not in line:
            continue
        if line.lower().startswith("timed out"):
            continue
        t, p = line.split(" ", 1)
        rows.append((t, p.strip()))
    return rows


def _clear(topic: str) -> None:
    subprocess.run(
        ["mosquitto_pub", "-h", MQTT_HOST, "-t", topic, "-n", "-r"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _under(prefix: str) -> Callable[[str, str], bool]:
    return lambda topic, _payload: topic.startswith(prefix)


def _leaf(topic: str, prefix: str) -> str | None:
    return topic[len(prefix):] if topic.startswith(prefix) else None


def _root_sensor(topic: str, payload: str) -> bool:
    # Bare numeric root topics with sensor payloads (layout bug artifacts).
    return topic.isdigit() and payload.upper() in ("ACTIVE", "INACTIVE")


def _ih_head_leaf(topic: str, _payload: str) -> bool:
    # Legacy Digicon SET leaf (IH and digits in the topic). The live publisher uses packed digits.
    leaf = _leaf(topic, "track/signalhead/")
    return leaf is not None and leaf.upper().startswith("IH") and leaf[2:].isdigit()


def _nondigit_sensor(topic: str, _payload: str) -> bool:
    # JMRI MQTT receive track/sensor/{0} creates M2S{0}. Non-digit leaves are junk
    # (M2SBlock 1-1). Live occupancy is packed digits (M2S100 ↔ track/sensor/100).
    leaf = _leaf(topic, "track/sensor/")
    return leaf is not None and leaf != "" and not leaf.isdigit()


class Junk(NamedTuple):
    """One kind of junk retain: the subscription that finds it and the test a topic must pass to be cleared."""

    name: str
    subscription: str
    is_junk: Callable[[str, str], bool]


# The clear and the leftover count after it use the same test, so a topic counts as left only if it was one to clear.
JUNK = (
    Junk("cmd", "track/cmd/sensor/#", _under("track/cmd/sensor/")),
    Junk("root_numeric", "+", _root_sensor),
    # Discard sink if someone setKnownState with the disabled send template.
    Junk("discard", "_discard/cmd/sensor/#", _under("_discard/cmd/sensor/")),
    Junk("ih_leaf", "track/signalhead/#", _ih_head_leaf),
    Junk("nondigit_sensor", "track/sensor/#", _nondigit_sensor),
)


def _junk_topics(kind: Junk) -> list[str]:
    return [t for t, p in _sub(kind.subscription) if kind.is_junk(t, p)]


def main() -> int:
    cleared: list[str] = []
    for kind in JUNK:
        for t in _junk_topics(kind):
            _clear(t)
            cleared.append(t)

    left = {kind.name: len(_junk_topics(kind)) for kind in JUNK}
    print(
        "cleared=%d remaining_cmd=%d remaining_root_numeric=%d remaining_discard=%d remaining_ih_leaf=%d remaining_nondigit_sensor=%d host=%s"
        % (
            len(cleared),
            left["cmd"],
            left["root_numeric"],
            left["discard"],
            left["ih_leaf"],
            left["nondigit_sensor"],
            MQTT_HOST,
        )
    )
    return 0 if not any(left.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

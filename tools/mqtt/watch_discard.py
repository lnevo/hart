#!/usr/bin/env python3
"""Watch _discard writes on the layout broker, read-only, one timestamped line each.

    python3 tools/mqtt/watch_discard.py            (or: make mqtt-watch; Ctrl-C stops)

JMRI sends a sensor state it set itself to _discard/cmd/sensor/<addr> (option 11.3,
docs/ctc/MQTT_SENSOR_STATUS_ONLY.md), and stock JMRI always retains it. Run this while testing
CATS, PanelPro or the mimic to see which action writes them; clear them with `make mqtt-clean`.

Each line says whether the message was already stored on the broker when the watch started
("stored") or was written while watching ("NEW"). Under MQTT 3.1.1 the broker sets the retain
bit only on stored messages it hands to a new subscriber, so that bit tells the two apart; it
does not say how the writer published (JMRI retains every one).

Broker: HART_MQTT_BROKER (hartlib.hosts), default the Pi. Subscribes only; never publishes.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib.hosts import mqtt_broker  # noqa: E402

TOPIC = "_discard/#"


def command(host: str) -> list[str]:
    """The mosquitto_sub call (MQTT 3.1.1): receive time, retain bit, topic and payload per message."""
    return ["mosquitto_sub", "-V", "mqttv311", "-h", host, "-t", TOPIC, "-F", "%I\t%r\t%t\t%p"]


def describe(line: str) -> str:
    """One output line from a mosquitto_sub line: time, stored or NEW, topic, payload."""
    parts = line.rstrip("\n").split("\t", 3)
    if len(parts) != 4:
        return line.rstrip("\n")
    when, retained, topic, payload = parts
    kind = "stored" if retained == "1" else "NEW   "
    return f"{when}  {kind}  {topic}  {payload}"


def main() -> int:
    if not shutil.which("mosquitto_sub"):
        print("watch_discard: mosquitto_sub is not installed (brew install mosquitto)", file=sys.stderr)
        return 2
    host = mqtt_broker()
    print(f"watching {TOPIC} on {host} (read-only; Ctrl-C stops). 'stored' = already on the broker "
          f"when the watch started; 'NEW' = written since", file=sys.stderr, flush=True)
    try:
        with subprocess.Popen(command(host), stdout=subprocess.PIPE, text=True) as proc:
            for line in proc.stdout:
                print(describe(line), flush=True)
            return proc.wait()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())

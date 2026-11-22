#!/usr/bin/env python3
"""Watch _discard writes on the layout broker, read-only, one timestamped line each.

    python3 tools/mqtt/watch_discard.py            (or: make mqtt-watch; Ctrl-C stops)

JMRI sends a sensor state it set itself to _discard/cmd/sensor/<addr> (option 11.3,
docs/ctc/MQTT_SENSOR_STATUS_ONLY.md), retained. Run this while testing CATS, PanelPro or the
mimic to see which action writes them; clear them with `make mqtt-clean`.

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
    """The mosquitto_sub call: timestamp, topic, payload and retain flag per message."""
    return ["mosquitto_sub", "-h", host, "-t", TOPIC, "-F", "%I %t %p retained=%r"]


def main() -> int:
    if not shutil.which("mosquitto_sub"):
        print("watch_discard: mosquitto_sub is not installed (brew install mosquitto)", file=sys.stderr)
        return 2
    host = mqtt_broker()
    print(f"watching {TOPIC} on {host} (read-only; Ctrl-C stops)", file=sys.stderr, flush=True)
    try:
        return subprocess.call(command(host))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())

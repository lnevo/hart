"""Set the retained messages on the repro's private broker.

Clears every retained topic, then publishes one retained ACTIVE per
track/sensor/<n> and one THROWN per track/turnout/<n> for n in 1..N
(N=0 only clears). Prints the retained count afterwards.

Talks only to 127.0.0.1 on a port other than 1883, so it cannot reach the
layout broker. See docs/jmri/MQTT_STARTUP_RACE.md.

usage: python retain.py PORT N
"""
from __future__ import annotations

import sys
import time

import paho.mqtt.client as mqtt

HOST = "127.0.0.1"


def retained_topics(port: int, wait: float = 1.5) -> set[str]:
    seen: set[str] = set()
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.on_message = lambda _c, _u, m: seen.add(m.topic) if m.retain and m.payload else None
    c.connect(HOST, port)
    # EMQX does not send retained messages to a bare "#"; track/# covers ours.
    c.subscribe([("#", 0), ("track/#", 0)])
    c.loop_start()
    time.sleep(wait)
    c.loop_stop()
    c.disconnect()
    return seen


def main() -> int:
    port, n = int(sys.argv[1]), int(sys.argv[2])
    if port == 1883:
        print("refusing port 1883: the repro uses its own broker", file=sys.stderr)
        return 2
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.connect(HOST, port)
    c.loop_start()
    for t in retained_topics(port):
        c.publish(t, b"", retain=True).wait_for_publish()
    for i in range(1, n + 1):
        c.publish(f"track/sensor/{i}", "ACTIVE", retain=True).wait_for_publish()
        c.publish(f"track/turnout/{i}", "THROWN", retain=True).wait_for_publish()
    c.loop_stop()
    c.disconnect()
    print(f"retained: {len(retained_topics(port))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

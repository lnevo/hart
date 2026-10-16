# MQTT broker — infrastructure prerequisite

The broker is **part of the HART package boundary**: LCOS, JMRI PanelPro, and CATS MQTT mimic all assume a reachable Mosquitto (or compatible) bus before any layout package starts.

## Role in the stack

```text
JMRI PanelPro  ←→  MQTT broker  ←→  serial_to_mqtt.py  ←→  Nano (LCOS)
CATS mimic QA  ←→  MQTT broker
STS            (no MQTT — separate HTTP stack)
```

| Consumer | Topics (examples) |
|----------|-------------------|
| LCOS bridge | `track/turnout/#`, `track/sensor/#`, `track/signalmast/#`, `track/cmd/turnout/#` |
| JMRI | Same broker connection as configured in PanelPro MQTT connection |
| Signal publisher | `track/signalhead/#`, `track/bridge/sml_mode` |

## Lab / consolidation default

Document your broker host in [`hosts.env.example`](../../packages/layout-hosts/hosts.env.example):

```bash
HART_MQTT_BROKER=minipc-e5h6x.local   # or 192.168.x.x
HART_MQTT_PORT=1883
```

JMRI and `serial_to_mqtt.py` must use the **same broker**.

## Operator checklist

1. Mosquitto running and reachable from Mac lab, Windows mini PC, and Pi.
2. No TLS required for bench (adjust if you add it later).
3. JMRI MQTT connection configured once per profile; retained `track/signalmast/*` topics enroll the live roster.
4. Start **`serial_to_mqtt.py` in the foreground** on Windows before expecting LCOS feedback (see [`../lcos-bridge/README.md`](../lcos-bridge/README.md)).

## Validation

```bash
mosquitto_pub -h "$HART_MQTT_BROKER" -t track/bridge/cmd -m PING
# Expect ACK PING on serial when Nano bridge is up
```

Tier B: [`../../cross-repo/lcos/TIER_B.md`](../../cross-repo/lcos/TIER_B.md)

## Not bundled

We do not ship Mosquitto binaries in git. Install on the layout mini PC / Pi per OS docs; record hostnames in `hosts.env`.

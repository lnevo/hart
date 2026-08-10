# MQTT sensors are status-only

HART never commands field sensors over MQTT.

| Topic | Role |
|-------|------|
| `track/sensor/{addr}` | **Status** (ACTIVE / INACTIVE), often retained — field → JMRI |
| `track/cmd/sensor/{addr}` | **Forbidden** on the field |
| bare `{addr}` at broker root | **Bug artifact** — clear it |

## JMRI

- Option **11.5** (receive): `track/sensor/{0}`
- Option **11.3** (send): `_discard/cmd/sensor/{0}` — **not empty**. An empty send
  template made `MqttSensor.setKnownState` publish payloads to topic `{addr}`
  at the broker root.
- `apply_mqtt_retain_at_startup.py` uses **`setOwnState`** (JMRI-only paint).
  Never `setKnownState` for MQTT sensors from that script.

Turnouts still use `track/cmd/turnout/{0}` and `track/turnout/{0}`.

## Cleanup (manual / rare)

Do **not** put cleanup on `launch_cats.sh`. Launch must not publish, clear,
or probe MQTT.

When broker junk appears (usually after a bad profile or script), run once:

```bash
python3 cats/scripts/clear_mqtt_cmd_sensor_retain.py
```

Clears `track/cmd/sensor/#`, bare numeric ACTIVE/INACTIVE roots, and
`_discard/cmd/sensor/#`. Leaves `track/sensor/#` and `track/turnout/#`
status retain alone.

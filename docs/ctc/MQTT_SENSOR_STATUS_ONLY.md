# MQTT sensors are status-only

HART never commands field sensors over MQTT.

| Topic | Role |
|-------|------|
| `track/sensor/{addr}` | **Status** (ACTIVE / INACTIVE), often retained — field → JMRI |
| `track/cmd/sensor/{addr}` | **Forbidden** on the field |
| `_discard/cmd/sensor/{addr}` | **Retired sink** — do not use; clear retain if it reappears |
| bare `{addr}` at broker root | **Bug artifact** — empty JMRI send template published here |

## JMRI

- Option **11.5** (receive): `track/sensor/{0}`
- Option **11.3** (send): keep `_discard/cmd/sensor/{0}` so `MqttSensor.setKnownState` cannot hit LCOS. Do **not** empty it: JMRI then publishes `ACTIVE`/`INACTIVE` to bare `{addr}` at the broker root.
- JMRI is stock, so these publishes reach the broker and can be retained under `_discard/`. They go nowhere near the field. Clear them with `tools/mqtt/clear_mqtt_cmd_sensor_retain.py` if they build up.
- Never `setKnownState` for MQTT sensors from scripts.

Turnouts still use `track/cmd/turnout/{0}` and `track/turnout/{0}`.

## Cleanup (manual / rare)

Do **not** put cleanup on `launch_cats.sh`. Launch must not publish, clear, or probe MQTT.

```bash
python3 tools/mqtt/clear_mqtt_cmd_sensor_retain.py
```

Clears `track/cmd/sensor/#`, bare numeric ACTIVE/INACTIVE roots, and leftover `_discard/cmd/sensor/#`. Leaves `track/sensor/#` and `track/turnout/#` status retain alone.

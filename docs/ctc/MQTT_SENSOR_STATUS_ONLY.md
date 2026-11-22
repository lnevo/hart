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
- Publishes to this sink never reach the field.
- Never `setKnownState` for MQTT sensors from scripts.

Turnouts still use `track/cmd/turnout/{0}` and `track/turnout/{0}`.

## Cleanup (manual / rare)

Do **not** put cleanup on `launch_cats.sh`. Launch must not publish, clear, or probe MQTT.

```bash
make mqtt-clean    # python3 tools/mqtt/clear_mqtt_cmd_sensor_retain.py
make mqtt-watch    # python3 tools/mqtt/watch_discard.py: read-only, Ctrl-C stops
```

`mqtt-clean` clears `track/cmd/sensor/#`, bare numeric ACTIVE/INACTIVE roots, and leftover `_discard/cmd/sensor/#`. It leaves `track/sensor/#` and `track/turnout/#` status retain alone.

`mqtt-watch` prints each `_discard` write with its time and retain flag. Run it while testing CATS, PanelPro or the mimic to see which action writes them (owner, 2026-11-21). No startup or deploy wrote any on 2026-11-21; the writer is still unknown.

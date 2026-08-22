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
- Option **11.3** (send): do **not** point at `_discard/cmd/sensor/{0}`. That was a trash-can so `MqttSensor.setKnownState` would not hit LCOS. An **empty** send template is worse: JMRI published `ACTIVE`/`INACTIVE` to topic `{addr}` at the broker root.
- `apply_maintain_mqtt.py` uses **`setOwnState`** (JMRI-only paint). Never `setKnownState` for MQTT sensors from scripts.

Turnouts still use `track/cmd/turnout/{0}` and `track/turnout/{0}`.

## Cleanup (manual / rare)

Do **not** put cleanup on `launch_cats.sh`. Launch must not publish, clear, or probe MQTT.

```bash
python3 cats/scripts/clear_mqtt_cmd_sensor_retain.py
```

Clears `track/cmd/sensor/#`, bare numeric ACTIVE/INACTIVE roots, and leftover `_discard/cmd/sensor/#`. Leaves `track/sensor/#` and `track/turnout/#` status retain alone.

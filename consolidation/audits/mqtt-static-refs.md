# Audit — MQTT static head references (D6)

**Date:** 2026-08-31  
**Decision:** Live roster from `track/signalmast/<packed>` — verify no static allow-lists.

## Files scanned

| Path | Result |
|------|--------|
| `jmri/scripts/mqtt_signalhead_publisher.py` | OK — comment says no HEAD_NAMES; enroll from signalmast |
| `LCOS_ESP32_MQTT_Client/serial_to_mqtt.py` | OK — `note_signalmast()`, subscribe `track/signalmast/#`, SET gated on roster |
| `cats/scripts/build_hart_signal_heads.py` | OK — rejects HEAD_NAMES patch |
| `cats/scripts/tests/test_mqtt_signalhead_publisher.py` | OK — asserts HEAD_NAMES absent |

## Forbidden patterns (must not reappear)

- `MQTT_HEAD_NAMES`
- `HEAD_NAMES_BEGIN` / `HEAD_NAMES = [`
- `DIGICON_PACKED_HEADS` static lists in publisher or bridge

## Live behavior (confirmed in code)

**Publisher (`mqtt_signalhead_publisher.py`):**

- `_enroll_packed` from `track/signalmast/<packed>`
- SET/Unheld requires enrollment

**Bridge (`serial_to_mqtt.py`):**

- `SIGNALMAST_SUBSCRIBE = "track/signalmast/#"`
- `sml_guard.note_signalmast(packed)` on retain
- Ignores SET when `not on live roster`

## Validator

`consolidation/validators/check_mqtt_no_static_lists.py` — fails if forbidden strings appear in live publisher/bridge/build script.

## Manual smoke (Tier B)

1. Subscribe `track/signalmast/#` on broker.
2. Confirm retain after bridge connect.
3. SET on unknown packed → ignored (bridge log).
4. SET after enroll → serial forward.

Spec: [`cross-repo/lcos/WORKING_BASELINE.md`](../cross-repo/lcos/WORKING_BASELINE.md)

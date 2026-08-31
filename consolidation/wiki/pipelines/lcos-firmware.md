> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record

| Kind | Live (read-only) | Consolidation |
|------|------------------|---------------|
| Runbook | `wiki/pipelines/lcos-firmware.md` | this file |
| Sibling repo | `LCOS_ESP32_MQTT_Client` | [`cross-repo/lcos/SUBMODULE_PIN.md`](../../cross-repo/lcos/SUBMODULE_PIN.md) |
| Tier B smokes | — | [`cross-repo/lcos/TIER_B.md`](../../cross-repo/lcos/TIER_B.md) |
| Vendor (no edit) | `lcos/`, `reference/` | protected |

**Tier:** B · **D10:** spec-only until bridge/firmware promotion requested

---

# Pipeline 9 — LCOS Nano firmware

Flash the Arduino Nano that bridges LCOS radio (nRF24) to USB serial MQTT lines.

**Status:** Live. Repo: [`LCOS_ESP32_MQTT_Client`](https://github.com/lnevo/LCOS_ESP32_MQTT_Client) (folder name is historical; hardware is Nano).

**API truth:** `lcos/lcos.h`, `lcos/lcos.cpp`, `reference/` — do not edit vendor `lcos/` or `reference/` unless merging an official drop.

## Inputs

- `lcos-bridge.ino` — RF channel, `thisNode` (sketch name matches submodule folder `lcos-bridge/`)
- `lcos_mqtt_bridge.cpp` — `kSubscribeDisplayNodes[]` (event **125** to those display nodes)

## Outputs

- Firmware on the Nano. Boot should log `Subscription accepted` per node. Host `RESUBSCRIBE` re-emits 125.

## Run

Configure nodes, then flash (`scripts/windows/flash_nano.py` or Arduino IDE). Host bridge:

```bash
python -u serial_to_mqtt.py --com COM3 --broker <mqtt-host> --verbose
```

Run the Windows serial bridge in the **foreground**. Do not start it from an agent (`Start-Process` Hidden stole COM3).

Detail: that repo’s `README.md`, `docs/serial_mqtt_windows.md`.

Periodic 125 after a master RAM wipe is a known follow-up (mast MQTT vanishes until 125 is replayed).

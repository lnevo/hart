# MQTT mimic QA (CATS + JMRI)

Cross-cutting pipelines 3, 5 and 9: LCOS Digicon aspect QA without the physical layout.

## Live paths

| Path | Role |
|------|------|
| `tools/mqtt-mimic/lcos_mqtt_mimic.py` | CATS-side mimic; reads `public_name_map.csv` |
| `jmri/scripts/signal_coordinator.py` | JMRI jython publisher |
| `LCOS_ESP32_MQTT_Client/serial_to_mqtt.py` | Host serial ↔ MQTT bridge |

## Behavior

- **Live roster:** non-empty `track/signalmast/<packed>` from LCOS — not static allow-lists.
- **Topics:** `track/signalhead/<packed>` (SET), `track/signalmast/<packed>` (field status).
- **Packed ID:** deploy `IH*` digits; wiring CSV may use other schemes — pipeline 8 crosswalk.
- **Bridge:** Windows serial bridge runs **foreground** only (do not `Start-Process` Hidden).

## Run

```bash
# JMRI PanelPro with signal_coordinator active
python3 tools/mqtt-mimic/lcos_mqtt_mimic.py --help
python -u ../LCOS_ESP32_MQTT_Client/serial_to_mqtt.py --com COM3 --broker minipc-e5h6x.local
```

## Bridge smoke test

Run this by hand after a bridge or firmware change.

1. Subscribe to `track/signalmast/#` on broker `minipc-e5h6x.local`.
2. After the bridge connects, confirm non-empty retained mast topics for live heads.
3. A SET on `track/signalhead/<packed>` must be gated when the mast topic is absent.

### Native SML QA

`python3 tools/mqtt-mimic/qa/run_native_sml_qa.py` drives retained MQTT states and checks mast aspects through JMRI JSON. It covers 100, 102, 110, 111, 114/115, K-1/K-2, the A48 balloon and 117/117b. It never publishes `track/cmd/*`, and it captures the retained baseline and restores it. Run it by hand with no operating session in progress. Its last recorded results are in `tools/mqtt-mimic/qa/`.

### Broker cleanup

The one-shot retain clear for stale `track/signalhead/*` and `track/signalmast/*` (keeping 432 and 433) has been done by hand. Do not encode it in a permanent script.

## Related pipelines

- [Digicon signal beans](digicon-signal-beans.md) — pipeline 3
- [CATS Masters](cats-panels.md) — pipeline 5
- [LCOS firmware](lcos-firmware.md) — pipeline 9

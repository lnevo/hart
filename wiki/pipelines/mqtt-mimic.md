# MQTT mimic QA (CATS + JMRI)

Cross-cutting pipelines 3, 5 and 9: LCOS Digicon aspect QA without the physical layout.

## Live paths

| Path | Role |
|------|------|
| `jmri/resources/jmri-web/mimic/index.html` | Mimic page on the Pi, served by JMRI at `http://10.0.0.150:12080/web/mimic/`; reads state over the JMRI JSON WebSocket |
| `jmri/resources/jmri-web/mimic/mimic.css`, `mimic_view.js` | Markup, style and `render()` shared by both mimic pages; each page keeps only its transport. The Mac server serves them at `/mimic.css` and `/mimic_view.js` |
| `jmri/layouts/hart/scripts/mimic_relay.py` | Pi Start Up script: publishes the page's clicks (memory `IMHART_MIMIC`) as retained `track/sensor` / `track/turnout`, never `track/cmd` |
| `tools/mqtt-mimic/build_mimic_web.py` | Deploy step: writes the page's `mimic_layout.json` from the same sources as the Mac mimic |
| `tools/mqtt-mimic/lcos_mqtt_mimic.py` | Mac mimic (own web server on 127.0.0.1:8765); reads `public_name_map.csv`. Its launch agent `com.hart.mqtt-mimic` is disabled since 2026-11-11 |
| `jmri/scripts/signal_coordinator.py` | JMRI jython publisher |
| `LCOS_ESP32_MQTT_Client/serial_to_mqtt.py` | Host serial ↔ MQTT bridge |

## Behavior

- **Live roster:** non-empty `track/signalmast/<packed>` from LCOS — not static allow-lists.
- **Topics:** `track/signalhead/<packed>` (SET), `track/signalmast/<packed>` (field status).
- **Packed ID:** deploy `IH*` digits, the same as `system_name` in `signal_wiring.csv` (`check_wiring_crosswalk.py`).
- **Bridge:** Windows serial bridge runs **foreground** only (do not `Start-Process` Hidden).

## Broker setting

The Mac tools (`tools/mqtt/`, `tools/mqtt-mimic/`, `seed_default_thrown_turnouts.py`) read the broker and JMRI address through `tools/ops/lib/hart_hosts.py`. Set `HART_MQTT_BROKER`, `HART_MQTT_PORT` and `HART_JMRI_JSON` in the environment or in `tools/env/hart.env`; the default is the Pi (`10.0.0.150`, `http://10.0.0.150:12080/json`). The older `MQTT_HOST` and `JMRI_JSON` still work, and the environment beats `hart.env`.

## Run

```bash
# JMRI PanelPro with signal_coordinator active
python3 tools/mqtt-mimic/lcos_mqtt_mimic.py --help
python -u ../LCOS_ESP32_MQTT_Client/serial_to_mqtt.py --com COM3 --broker 10.0.0.150
```

## Bridge smoke test

Run this by hand after a bridge or firmware change.

1. Subscribe to `track/signalmast/#` on broker `10.0.0.150` (the Pi).
2. After the bridge connects, confirm non-empty retained mast topics for live heads.
3. A SET on `track/signalhead/<packed>` must be gated when the mast topic is absent.

### Native SML QA

`python3 tools/mqtt-mimic/qa/run_native_sml_qa.py` drives retained MQTT states and checks mast aspects through JMRI JSON. It covers 100, 102, 110, 111, 114/115, McKees Rocks/McKeesport, the A48 balloon and 117/117b. It never publishes `track/cmd/*`, and it captures the retained baseline and restores it. Run it by hand with no operating session in progress. Its last recorded results are in `tools/mqtt-mimic/qa/`.

### Broker cleanup

The one-shot retain clear for stale `track/signalhead/*` and `track/signalmast/*` (keeping 432 and 433) has been done by hand. Do not encode it in a permanent script.

## Related pipelines

- [Digicon signal beans](digicon-signal-beans.md) — pipeline 3
- [CATS Masters](cats-panels.md) — pipeline 5
- [LCOS firmware](lcos-firmware.md) — pipeline 9

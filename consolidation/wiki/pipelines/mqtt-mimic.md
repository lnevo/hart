# MQTT mimic QA (CATS + JMRI)

**Consolidation topic:** Pipeline 3/5 cross-cutting — LCOS Digicon aspect QA without physical layout.

## Live paths (read-only)

| Path | Role |
|------|------|
| `cats/scripts/lcos_mqtt_mimic.py` | CATS-side mimic; reads `public_name_map.csv` |
| `jmri/scripts/mqtt_signalhead_publisher.py` | JMRI jython publisher (deployed to `preference:jython/`) |
| `LCOS_ESP32_MQTT_Client/serial_to_mqtt.py` | Host serial ↔ MQTT bridge |

## Behavior (consolidation documented)

- **Live roster:** non-empty `track/signalmast/<packed>` from LCOS — not static allow-lists.
- **Topics:** `track/signalhead/<packed>` (SET), `track/signalmast/<packed>` (field status).
- **Packed ID:** radio node × 100 + UID (e.g. node 4 UID 32 → `432` / `IH432`).
- **Bridge:** Windows serial bridge runs **foreground** only (do not `Start-Process` Hidden).

## Run (live — do not change from consolidation)

```bash
# JMRI PanelPro with mqtt_signalhead_publisher active
python3 cats/scripts/lcos_mqtt_mimic.py --help
python -u ../LCOS_ESP32_MQTT_Client/serial_to_mqtt.py --com COM3 --broker minipc-e5h6x.local
```

## Pending (D10)

- Periodic event **125** after master RAM wipe
- USB serial ACK / pacing on Windows bridge

Spec: [`cross-repo/lcos/TIER_B.md`](../../cross-repo/lcos/TIER_B.md)

## Related pipelines

- [Digicon signal beans](digicon-signal-beans.md) — pipeline 3
- [CATS Masters](cats-masters.md) — pipeline 5
- [LCOS firmware](lcos-firmware.md) — pipeline 9

> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record

| Kind | Live (read-only) | Consolidation |
|------|------------------|---------------|
| CATS mimic | `cats/scripts/lcos_mqtt_mimic.py` | — |
| JMRI publisher | `jmri/scripts/mqtt_signalhead_publisher.py` | — |
| Bridge | `LCOS_ESP32_MQTT_Client/serial_to_mqtt.py` | [`cross-repo/lcos/TIER_B.md`](../../cross-repo/lcos/TIER_B.md) |

**Tier:** B (manual smoke) · Cross-cutting pipelines **3 / 5 / 9** · **D6:** live `track/signalmast/#` roster

---

# MQTT mimic QA (CATS + JMRI)

**Consolidation topic:** Pipeline 3/5/9 cross-cutting — LCOS Digicon aspect QA without physical layout.

## Live paths

| Path | Role |
|------|------|
| `cats/scripts/lcos_mqtt_mimic.py` | CATS-side mimic; reads `public_name_map.csv` |
| `jmri/scripts/mqtt_signalhead_publisher.py` | JMRI jython publisher |
| `LCOS_ESP32_MQTT_Client/serial_to_mqtt.py` | Host serial ↔ MQTT bridge |

## Behavior

- **Live roster:** non-empty `track/signalmast/<packed>` from LCOS — not static allow-lists.
- **Topics:** `track/signalhead/<packed>` (SET), `track/signalmast/<packed>` (field status).
- **Packed ID:** deploy `IH*` digits; wiring CSV may use other schemes — pipeline 8 crosswalk.
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

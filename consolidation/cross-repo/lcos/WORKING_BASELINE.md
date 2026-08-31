# LCOS — working baseline (D10)

**Decision:** Move **working published version as-is** into consolidation review with standard validation — minimal modification.

**Sibling repo:** [`LCOS_ESP32_MQTT_Client`](../../../LCOS_ESP32_MQTT_Client)  
**Do not edit** vendor `lcos/` or `reference/` without explicit merge request.

## Production behavior (current)

| Component | Role |
|-----------|------|
| `LCOS_ESP32_MQTT_Client.ino` | Nano firmware; RF + USB serial |
| `lcos_mqtt_bridge.cpp` | IH SET + `track/signalmast/<packed>` status |
| `serial_to_mqtt.py` | Host bridge; roster from `track/signalmast/#` |
| `mqtt_serial.cpp` | Serial line discipline |

## MQTT contract

| Topic | Direction | Notes |
|-------|-----------|-------|
| `track/signalmast/<packed>` | LCOS → JMRI | Retain; enrolls live roster |
| `track/signalhead/<packed>` | JMRI → LCOS | SET / Unheld; gated on roster |
| `track/cmd/turnout/<packed>` | JMRI → LCOS | Turnout commands |

Packed = radio node × 100 + UID (e.g. 432 = node 4, UID 32).

## Validation checklist (consolidation)

- [ ] Bridge starts foreground on Windows (`serial_to_mqtt.py --com … --broker …`)
- [ ] Boot log: subscription accepted per display node
- [ ] Retained mast topics after connect
- [ ] SET ignored when not enrolled (log message)
- [ ] PanelPro publisher + bridge together — aspects paint

Automated grep: `validators/check_mqtt_no_static_lists.py`

## Known follow-ups (not blockers if production stable)

Documented in [`TIER_B.md`](TIER_B.md):

- Periodic event **125** after master RAM wipe
- USB serial ACK / pacing refinements

Implement in sibling repo only after consolidation review + user promotion.

## Wiring cross-reference

Inventory v85: `hart/docs/wiring/LCOS_Layout_Inventory_v85.xlsx`  
Crosswalk validator: `consolidation/validators/check_wiring_crosswalk.py`

## Promotion to meta-repo

When D7 submodules reopen: pin this doc to a git tag on `LCOS_ESP32_MQTT_Client` at promotion time.

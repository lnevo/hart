# LCOS — Tier B validation spec (consolidation)

**Repo:** [`LCOS_ESP32_MQTT_Client`](../../../LCOS_ESP32_MQTT_Client) — do not edit vendor `lcos/` or `reference/` from consolidation.

## Manual smokes (manifest tier B)

### B1 — Mast roster from MQTT

1. Subscribe `track/signalmast/#` on broker `minipc-e5h6x.local`.
2. After bridge connect, confirm non-empty retained mast topics for live heads.
3. SET on `track/signalhead/<packed>` must be gated when mast topic absent.

### B2 — Event 125 replay

After LCOS master RAM wipe, mast MQTT disappears until display subscription (event 125) is replayed.

**Proposal:** Periodic 125 to `kSubscribeDisplayNodes[]` after master restart.

- [ ] Approve firmware/bridge change (D10)

### B3 — USB serial ACK / pacing

Windows bridge TODOs in live STATUS — document pacing before promotion.

## Files to change on promotion (not now)

- `lcos_mqtt_bridge.cpp` — subscription + 125
- `serial_to_mqtt.py` — ACK pacing
- `mqtt_serial.cpp` — serial layer

## Broker cleanup note

One-shot retain clear for stale `track/signalhead/*` and `track/signalmast/*` (keep 432/433) — already done manually; do not encode in immortal scripts.

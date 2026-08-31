# LCOS bridge — submodule pin spec (consolidation)

**Sibling repo:** [LCOS_ESP32_MQTT_Client](https://github.com/lnevo/LCOS_ESP32_MQTT_Client)  
**Status:** Pin active · submodule path `consolidation/external/lcos-bridge` — see [`SUBMODULE_MANIFEST.yaml`](../SUBMODULE_MANIFEST.yaml)

## Pin (2026-08-31)

| Field | Value |
|-------|--------|
| Commit | `ec16af8c85a5d8c9acb05eed854a5b69cc8ca90d` |
| Message | Remind on ops traffic when HBLOOP is down that layout feedback is missing. |
| Branch | (record at pin time: current default branch HEAD) |

## Validation before any bridge/firmware promotion

Run from consolidation checklist — manual Tier B smokes in [`TIER_B.md`](TIER_B.md):

1. **B1** — Live `track/signalmast/#` roster; SET gated on mast topic present  
2. **B2** — Event 125 replay after master RAM wipe (spec only until D10 approves change)  
3. **B3** — USB serial ACK / pacing on Windows bridge  

Working baseline narrative: [`WORKING_BASELINE.md`](WORKING_BASELINE.md).

## Protected paths (do not edit from consolidation)

- `lcos/` — vendor LCOS library  
- `reference/LCOS_Client_Bare.ino` — upstream pattern  

Project-specific changes belong in `lcos_mqtt_bridge.*`, `mqtt_serial.*`, `LCOS_ESP32_MQTT_Client.ino`, `serial_to_mqtt.py`.

## Future submodule layout (D7)

```
consolidation/external/lcos-bridge  →  LCOS_ESP32_MQTT_Client @ ec16af8…
```

Init: [`wiki/REPOS.md`](../../wiki/REPOS.md) · `bash consolidation/scripts/init_external_submodules.sh`

## Re-pin procedure

1. Note new commit hash + one-line reason in this file.  
2. Re-run Tier B smokes.  
3. Update `cross-repo/lcos/WORKING_BASELINE.md` if behavior changed.  
4. Validators: `bash consolidation/validators/run_all.sh` (hart side unchanged unless MQTT static refs shift).

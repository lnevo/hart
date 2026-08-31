# Audit — script and doc headers

**Date:** 2026-08-31 (consolidation bootstrap)

## Summary

Live script headers are largely current. No Gate1-as-live references found in `lcos_mqtt_mimic.py`.

| File | Status | Notes |
|------|--------|-------|
| `cats/scripts/lcos_mqtt_mimic.py` | OK | Describes MQTT mimic; uses `tables.xml` + name map |
| `wiki/projects/cats-integration.md` | OK | Master4 present tense; hold panels documented |
| `jmri/layouts/hart/scripts/cleanup_uss_ctc_leftovers.py` | OK | Small `DELETE_SYSTEM_NAMES` set (OpenLCB MS01 only); no IO:AUTO routes |
| `wiki/pipelines/lcos-bom.md` | N/A | Excluded from consolidation scope (D8) |

## Recommendations (consolidation only)

1. Draft pipeline SoR tables in `consolidation/wiki/pipelines/` — done via sync script.
2. MQTT mimic consolidated page: `wiki/pipelines/mqtt-mimic.md`.
3. No live header edits required at this time.

## Live paths reviewed (read-only)

- `cats/scripts/lcos_mqtt_mimic.py`
- `wiki/projects/cats-integration.md`
- `jmri/layouts/hart/scripts/cleanup_uss_ctc_leftovers.py`

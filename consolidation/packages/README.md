# Consolidation packages

Deployable units in the standalone workspace. Each package includes runbooks, env templates, and scripts that resolve paths under `consolidation/external/`.

| Package | Path | Role |
|---------|------|------|
| **Infra prerequisites** | [`infra/mqtt-broker/`](infra/mqtt-broker/) | MQTT broker (required before LCOS + JMRI) |
| **LCOS bridge** | [`lcos-bridge/`](lcos-bridge/) | Nano firmware + Windows COM serial bridge |
| **Layout hosts** | [`layout-hosts/`](layout-hosts/) | Pi / Windows panel deploy from `hart-runtime` |
| **Car cards** | [`car-cards/`](car-cards/) | Raw drop-in → crop → OCR → cards (no legacy Images mirror) |
| **STS** | [`sts/`](sts/) | Docker + data mirror compose |
| **DJ Trains** | [`../external/desktop-data/dj-trains/`](../external/desktop-data/dj-trains/) | Prototype photos (mirrored) |

## Refresh mirrors then deploy

```bash
bash consolidation/scripts/mirror_all_live.sh
bash consolidation/packages/layout-hosts/sync_from_consolidation.sh --dry-run
```

## Environment

[`../env/consolidation.env.example`](../env/consolidation.env.example)

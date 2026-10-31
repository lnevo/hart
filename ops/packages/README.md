# Packages

Deployable units in the standalone workspace. Each package includes runbooks, env templates, and scripts that resolve paths under `external/`.

| Package | Path | Role |
|---------|------|------|
| **Infra prerequisites** | [`infra/mqtt-broker/`](infra/mqtt-broker/) | MQTT broker (required before LCOS + JMRI) |
| **LCOS bridge** | [`lcos-bridge/`](lcos-bridge/) | Nano firmware + Windows COM serial bridge |
| **Car cards** | [`car-cards/`](car-cards/) | Raw drop-in → crop → OCR → cards (no legacy Images mirror) |
| **STS** | [`sts/`](sts/) | Docker + data mirror compose |
| **DJ Trains** | [`../media/dj-trains/`](../../media/dj-trains/) | Prototype photos (mirrored) |

## Refresh mirrors then deploy

```bash
```

## Environment

[`../../tools/env/hart.env.example`](../../tools/env/hart.env.example)

# Packages

Runbooks for the parts of the railroad that run outside JMRI. Each package says where its code lives (usually a submodule under `external/` or `ops/hart-ops/`) and how to start it.

| Package | Path | Role |
|---------|------|------|
| **Infra prerequisites** | [`infra/mqtt-broker/`](infra/mqtt-broker/) | MQTT broker (required before LCOS + JMRI) |
| **LCOS bridge** | [`lcos-bridge/`](lcos-bridge/) | Nano firmware + Windows COM serial bridge |
| **Car cards** | [`car-cards/`](car-cards/) | Car photos and records through `bin/cars`; print templates and spot waybills |
| **STS** | [`sts/`](sts/) | Docker + data mirror compose |
| **DJ Trains** | [`../../media/dj-trains/`](../../media/dj-trains/) | Prototype photos (mirrored) |

## Environment

[`../../tools/env/hart.env.example`](../../tools/env/hart.env.example)

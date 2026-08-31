# external/ — sibling repos (hart meta-repo)

| Path | Repo | Pin |
|------|------|-----|
| `lcos-bridge/` | LCOS_ESP32_MQTT_Client | `ec16af8` |
| `sts-docker/` | sts-docker | `899b458` |
| `sts-helpers/` | sts-docker-helpers | `cdbbfce` |
| `hart-ops/` | **hart-ops** | `bc6ce55` |

```bash
bash consolidation/scripts/init_external_submodules.sh
git submodule update --init --recursive
```

Car inventory SoR: **`external/hart-ops/data/`** — see ADR in `consolidation/wiki/decisions/ADR-car-roster-single-sor.md`.

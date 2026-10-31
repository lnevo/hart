# External repos

Git submodules live here so nothing spreads to `~/hart-ops` or other home-directory clones.

| Path | Repo |
|------|------|
| `lcos-bridge/` | LCOS_ESP32_MQTT_Client |
| `sts-docker/` | sts-docker |
| `sts-helpers/` | sts-docker-helpers |
| `hart-ops/` | hart-ops |
| `sts-docker-data/` | STS runtime mirror (not git); see [`sts-docker-data/README.md`](sts-docker-data/README.md) |

```bash
# From hart repo root
bash tools/ops/init_external_submodules.sh
git submodule update --init --recursive
```


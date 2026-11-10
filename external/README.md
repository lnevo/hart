# External repos

Git submodules live here so nothing spreads to home-directory clones.

| Path | Repo |
|------|------|
| `lcos-bridge/` | LCOS_ESP32_MQTT_Client |
| `sts-docker/` | sts-docker |
| `sts-helpers/` | sts-docker-helpers |
| `sts-plugins/` | sts-plugins (STS addons: track_scale, coke_orders, hart_layout; bind-mounted into the sts-docker web container) |
| `model-railroad-skills/` | model-railroad-skills (public agent skills) |
| `jmri-cs105-roster-sync/` | jmri-cs105-roster-sync (JMRI roster → CS-105) |
| `sts-docker-data/` | STS runtime mirror (not git); see [`sts-docker-data/README.md`](sts-docker-data/README.md) |

```bash
# From hart repo root
make submodules    # git submodule update --init --recursive
```


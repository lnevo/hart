# External repos

Git submodules live here so nothing spreads to `~/hart-ops` or other home-directory clones.

| Path | Repo | Pin doc |
|------|------|---------|
| `lcos-bridge/` | LCOS_ESP32_MQTT_Client | [`../archive/consolidation/cross-repo/lcos/SUBMODULE_PIN.md`](../archive/consolidation/cross-repo/lcos/SUBMODULE_PIN.md) |
| `sts-docker/` | sts-docker | [`../archive/consolidation/cross-repo/sts-docker/SUBMODULE_PIN.md`](../archive/consolidation/cross-repo/sts-docker/SUBMODULE_PIN.md) |
| `sts-helpers/` | sts-docker-helpers | [`../archive/consolidation/cross-repo/sts-helpers/SUBMODULE_PIN.md`](../archive/consolidation/cross-repo/sts-helpers/SUBMODULE_PIN.md) |
| `hart-ops/` | hart-ops | [`../archive/consolidation/cross-repo/hart-ops/SUBMODULE_PIN.md`](../archive/consolidation/cross-repo/hart-ops/SUBMODULE_PIN.md) |
| `sts-docker-data/` | STS runtime mirror (not git) | [`sts-docker-data/README.md`](sts-docker-data/README.md) · [`../archive/consolidation/audits/standalone-gaps.md`](../archive/consolidation/audits/standalone-gaps.md) |

```bash
# From hart repo root
bash tools/ops/init_external_submodules.sh
git submodule update --init --recursive
```


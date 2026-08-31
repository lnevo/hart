# External repos (consolidation workspace)

Git submodules live **inside** `consolidation/` so nothing spreads to `~/hart-ops` or other home-directory clones.

| Path | Repo | Pin doc |
|------|------|---------|
| `lcos-bridge/` | LCOS_ESP32_MQTT_Client | [`../cross-repo/lcos/SUBMODULE_PIN.md`](../cross-repo/lcos/SUBMODULE_PIN.md) |
| `sts-docker/` | sts-docker | [`../cross-repo/sts-docker/SUBMODULE_PIN.md`](../cross-repo/sts-docker/SUBMODULE_PIN.md) |
| `sts-helpers/` | sts-docker-helpers | [`../cross-repo/sts-helpers/SUBMODULE_PIN.md`](../cross-repo/sts-helpers/SUBMODULE_PIN.md) |
| `hart-ops/` | hart-ops | [`../cross-repo/hart-ops/SUBMODULE_PIN.md`](../cross-repo/hart-ops/SUBMODULE_PIN.md) |
| `hart-runtime/` | Layout ops mirror (not git) | [`hart-runtime/README.md`](hart-runtime/README.md) |
| `desktop-data/` | Desktop/HART mirror (not git) | [`desktop-data/README.md`](desktop-data/README.md) |
| `sts-docker-data/` | STS runtime mirror (not git) | [`sts-docker-data/README.md`](sts-docker-data/README.md) · [`../audits/standalone-gaps.md`](../audits/standalone-gaps.md) |

```bash
# From hart repo root
bash consolidation/scripts/init_external_submodules.sh
git submodule update --init --recursive
```

From consolidation docs, shorthand **`external/hart-ops`** means this folder.

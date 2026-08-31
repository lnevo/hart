# HART meta-repo — sibling repos and submodules

**Status:** P3b **approved** — stage via [`scripts/init_external_submodules.sh`](../scripts/init_external_submodules.sh)  
**Manifest:** [`cross-repo/SUBMODULE_MANIFEST.yaml`](../cross-repo/SUBMODULE_MANIFEST.yaml)  
**Locks:** D7 · [`DECISIONS_RECORDED.md`](../DECISIONS_RECORDED.md)

## Hub

| Repo | Role |
|------|------|
| **`lnevo/hart`** | Layout, CATS panels, JMRI tables, wiring docs, consolidation |
| **`LCOS_ESP32_MQTT_Client`** | Nano firmware + MQTT bridge → `external/lcos-bridge` |
| **`sts-docker`** | STS PHP runtime → `external/sts-docker` |
| **`sts-docker-helpers`** | Seed, warm-start, switch lists → `external/sts-helpers` |
| **hart-ops** | Car inventory SoR, cards, waybills, publications → `external/hart-ops` @ `bc6ce55` |

## Submodule layout

```
hart/
  external/
    lcos-bridge/      → LCOS_ESP32_MQTT_Client @ ec16af8
    sts-docker/       → sts-docker @ 899b458
    sts-helpers/      → sts-docker-helpers @ cdbbfce
    hart-ops/         → hart-ops @ bc6ce55
```

## Init (operator)

```bash
bash consolidation/scripts/init_external_submodules.sh
git submodule update --init --recursive
```

Or manual:

```bash
git submodule add git@github.com:lnevo/LCOS_ESP32_MQTT_Client.git external/lcos-bridge
git -C external/lcos-bridge checkout ec16af8c85a5d8c9acb05eed854a5b69cc8ca90d
# … sts-docker, sts-helpers per SUBMODULE_MANIFEST.yaml
```

## Pins

| Submodule | Doc |
|-----------|-----|
| LCOS | [`cross-repo/lcos/SUBMODULE_PIN.md`](../cross-repo/lcos/SUBMODULE_PIN.md) |
| sts-docker | [`cross-repo/sts-docker/SUBMODULE_PIN.md`](../cross-repo/sts-docker/SUBMODULE_PIN.md) |
| sts-helpers | [`cross-repo/sts-helpers/SUBMODULE_PIN.md`](../cross-repo/sts-helpers/SUBMODULE_PIN.md) |
| hart-ops | [`cross-repo/hart-ops/MIGRATION_PLAN.md`](../cross-repo/hart-ops/MIGRATION_PLAN.md) |

## Car inventory SoR

Lives in **hart-ops** `data/` — not in JMRI Operations Pro GUI. See [`wiki/decisions/ADR-car-roster-single-sor.md`](decisions/ADR-car-roster-single-sor.md).

## Clone recipe

```bash
git clone --recurse-submodules git@github.com:lnevo/hart.git
export JMRI_LAYOUT=hart
bash consolidation/validators/run_all.sh
```

## Do not

- Monorepo-merge LCOS vendor `lcos/` into hart
- Edit car inventory in Operations Pro as SoR (export target only)
- Commit Desktop Car Cards tree into hart (use hart-ops)

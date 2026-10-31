# HART meta-repo — sibling repos and submodules

**Status:** P3b **done** — submodules under `consolidation/external/`  
**Manifest:** [`cross-repo/SUBMODULE_MANIFEST.yaml`](../cross-repo/SUBMODULE_MANIFEST.yaml)  
**Init:** [`scripts/init_external_submodules.sh`](../scripts/init_external_submodules.sh)

## Hub

| Repo | Role |
|------|------|
| **`lnevo/hart`** | Layout, CATS panels, JMRI tables, wiring docs, consolidation workspace |
| **`LCOS_ESP32_MQTT_Client`** | Nano firmware + MQTT bridge → `consolidation/external/lcos-bridge` |
| **`sts-docker`** | STS PHP runtime → `consolidation/external/sts-docker` |
| **`sts-docker-helpers`** | Seed, warm-start, switch lists → `consolidation/external/sts-helpers` |
| **`hart-ops`** | Car inventory SoR, cards, waybills, publications → `consolidation/external/hart-ops` @ `761c1f9` |

## Submodule layout

```
hart/consolidation/external/
  lcos-bridge/      → LCOS_ESP32_MQTT_Client @ ae2d8da
  sts-docker/       → sts-docker @ 899b458
  sts-helpers/      → sts-docker-helpers @ cdbbfce
  hart-ops/         → hart-ops @ 761c1f9
```

## Init (operator)

```bash
bash consolidation/scripts/init_external_submodules.sh
git submodule update --init --recursive
```

## Pins

| Submodule | Doc |
|-----------|-----|
| LCOS | [`cross-repo/lcos/SUBMODULE_PIN.md`](../cross-repo/lcos/SUBMODULE_PIN.md) |
| sts-docker | [`cross-repo/sts-docker/SUBMODULE_PIN.md`](../cross-repo/sts-docker/SUBMODULE_PIN.md) |
| sts-helpers | [`cross-repo/sts-helpers/SUBMODULE_PIN.md`](../cross-repo/sts-helpers/SUBMODULE_PIN.md) |
| hart-ops | [`cross-repo/hart-ops/SUBMODULE_PIN.md`](../cross-repo/hart-ops/SUBMODULE_PIN.md) |

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
- Clone submodules under `$HOME` — use `consolidation/external/` only

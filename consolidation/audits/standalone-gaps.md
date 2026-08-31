# Standalone consolidation — package boundaries

**Date:** 2026-08-31  
**Goal:** Complete operational package under `hart/consolidation/` with documented deploy scripts.

---

## Package index

See [`packages/README.md`](packages/README.md).

| Package | Standalone? | Deploy script |
|---------|-------------|---------------|
| **MQTT broker** | Prerequisite (infra) | [`packages/infra/mqtt-broker/`](packages/infra/mqtt-broker/) |
| **LCOS bridge** | Yes (firmware + COM host) | [`packages/lcos-bridge/run_bridge.sh`](packages/lcos-bridge/run_bridge.sh) |
| **Layout hosts** | Yes (from hart-runtime mirror) | [`packages/layout-hosts/sync_from_consolidation.sh`](packages/layout-hosts/sync_from_consolidation.sh) |
| **STS** | Yes | [`packages/sts/README.md`](packages/sts/README.md) |
| **Car cards** | Yes (pipeline; no legacy raw mirror) | [`packages/car-cards/README.md`](packages/car-cards/README.md) |
| **hart-ops** | Yes | submodule + `.venv` |
| **DJ Trains** | Yes (prototype mirror) | `external/desktop-data/dj-trains/` |

---

## Mirrors

| Mirror | Source | Refresh |
|--------|--------|---------|
| `external/hart-runtime/` | `hart/` repo | `mirror_hart_runtime.sh` |
| `external/sts-docker-data/` | `~/sts/*` | `mirror_sts_docker_data.sh` |
| `external/desktop-data/` | `~/Desktop/HART/` | `mirror_desktop_data.sh` |
| `external/desktop-data/dj-trains/` | DJ Trains prototype | same |
| `external/desktop-data/car-cards/incoming/` | *(empty drop folder)* | `setup_car_cards_workspace.sh` |

**One command:** `bash consolidation/scripts/mirror_all_live.sh`

---

## Intentionally excluded

| Item | Policy |
|------|--------|
| Legacy Car Cards `Images/` (~982 MB) | Not mirrored; drop new raws in `car-cards/incoming/` |
| Mosquitto binaries | Install on broker host; document in infra package |
| JMRI / PanelPro app | Operator install on layout hosts |

---

## Validators

Tier A uses `HART_LIVE_ROOT` → `external/hart-runtime/` when mirrored. **ALL PASSED** after refresh.

---

## Host config template

[`packages/layout-hosts/hosts.env.example`](packages/layout-hosts/hosts.env.example) — MQTT broker, SSH, COM port.

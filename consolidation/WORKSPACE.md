# Consolidation workspace — complete standalone tree

**Charter:** One clean workspace under `hart/consolidation/` containing every operational module, with dependencies resolved locally. Live paths (`~/hart/`, `~/sts/`, `~/Desktop/HART/`) are **copy sources only**.

## Quick start

```bash
bash consolidation/scripts/mirror_all_live.sh
bash consolidation/scripts/setup_car_cards_workspace.sh
open consolidation/index.html
```

Optional: `cp consolidation/env/consolidation.env.example consolidation/env/consolidation.env`

## Where everything lives

| Was scattered at… | Consolidation home |
|-------------------|-------------------|
| `hart/` jmri + cats + tables | `external/hart-runtime/` |
| `~/sts/*` | `external/sts-docker-data/` |
| CarImagesFinal | `external/desktop-data/car-images/CarImagesFinal/` |
| New raw car photos | `external/desktop-data/car-cards/incoming/` |
| Wiring Documentation | `external/desktop-data/wiring-bench/` |
| DJ Trains prototype | `external/desktop-data/dj-trains/` |
| F-root archive | `external/desktop-data/f-root/` |
| Git sibling repos | `external/{lcos-bridge,sts-docker,sts-helpers,hart-ops}/` |
| CSV SoR | `sor/` |

## Deploy packages

[`packages/README.md`](packages/README.md):

| Package | Script |
|---------|--------|
| MQTT broker (prerequisite) | [`packages/infra/mqtt-broker/`](packages/infra/mqtt-broker/) |
| LCOS bridge + COM host | [`packages/lcos-bridge/run_bridge.sh`](packages/lcos-bridge/run_bridge.sh) |
| Pi / Windows layout sync | [`packages/layout-hosts/sync_from_consolidation.sh`](packages/layout-hosts/sync_from_consolidation.sh) |
| Car cards pipeline | [`packages/car-cards/`](packages/car-cards/) |
| STS Docker | [`packages/sts/`](packages/sts/) |

## Submodules

```bash
bash consolidation/scripts/init_external_submodules.sh
git submodule update --init --recursive
```

## Boundaries

[`audits/standalone-gaps.md`](audits/standalone-gaps.md) — legacy raw Car Images not mirrored; Mosquitto/JMRI app installed on hosts.

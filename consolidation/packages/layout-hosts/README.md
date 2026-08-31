# Layout hosts — Pi / Windows deploy (consolidation)

Deploy the HART panel package from **`external/hart-runtime/`** (mirrored layout ops tree), not from live `~/hart/` paths.

## Prerequisites

- Tier A validators green: `bash consolidation/validators/run_all.sh`
- MQTT broker up if testing LCOS/JMRI MQTT
- SSH to Pi and Windows mini PC (see `hosts.env.example`)

## Sync from consolidation

```bash
# Refresh mirror first
bash consolidation/scripts/mirror_hart_runtime.sh

# Dry-run staging
bash consolidation/packages/layout-hosts/sync_from_consolidation.sh --dry-run

# Deploy
bash consolidation/packages/layout-hosts/sync_from_consolidation.sh --pi
bash consolidation/packages/layout-hosts/sync_from_consolidation.sh --win
bash consolidation/packages/layout-hosts/sync_from_consolidation.sh --all
```

This invokes the same `sync_hart_package.sh` logic shipped inside the mirror at  
`external/hart-runtime/cats/scripts/sync_hart_package.sh`, with `ROOT` = `hart-runtime`.

## What gets staged

- CATS hold panels (`HART_Master_*_hold.xml`)
- Jython startup scripts, dispatcher traininfo
- CTC icons, hart-aar appearances, USS sensor icons
- Deploy `tables.xml` bundle

## Host paths (defaults)

| Host | Package dir | JMRI user files |
|------|-------------|-----------------|
| Pi | `/home/pi/hart` | `/home/pi/JMRI_UserFiles` |
| Windows | `%USERPROFILE%/hart` | `C:/Users/lnevo/JMRI_UserFiles` |

Override via `hosts.env` (copy from `hosts.env.example`).

## Review / refactor notes

- Live script reference: `hart/cats/scripts/sync_hart_package.sh` (identical copy in mirror)
- Future: thin wrapper only in consolidation; upstream changes flow via `mirror_hart_runtime.sh`
- Tier B before production deploy: [`../../validators/TIER_B_MANUAL_SMOKES.md`](../../validators/TIER_B_MANUAL_SMOKES.md)

## Cutover manifest

[`../../cutover/layout-hosts/manifest.yaml`](../../cutover/layout-hosts/manifest.yaml)

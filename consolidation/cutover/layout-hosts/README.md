# Cutover — layout hosts (Pi / Windows)

**Status:** Package scripts in consolidation workspace; live hosts unchanged until operator runs sync.

## Consolidation deploy

| Artifact | Path |
|----------|------|
| Package README | [`../../packages/layout-hosts/README.md`](../../packages/layout-hosts/README.md) |
| Sync script | [`../../packages/layout-hosts/sync_from_consolidation.sh`](../../packages/layout-hosts/sync_from_consolidation.sh) |
| Host env template | [`../../packages/layout-hosts/hosts.env.example`](../../packages/layout-hosts/hosts.env.example) |
| Layout ops mirror | [`../../external/hart-runtime/`](../../external/hart-runtime/) |

```bash
bash consolidation/scripts/mirror_hart_runtime.sh
bash consolidation/packages/layout-hosts/sync_from_consolidation.sh --dry-run
```

## Prerequisites

- MQTT broker — [`../../packages/infra/mqtt-broker/README.md`](../../packages/infra/mqtt-broker/README.md)
- Tier A green + Tier B manual smokes before production deploy

## Test before cutover

- Tier A: `bash consolidation/validators/run_all.sh`
- Tier B: [`../../validators/TIER_B_MANUAL_SMOKES.md`](../../validators/TIER_B_MANUAL_SMOKES.md)
- LCOS: [`../../packages/lcos-bridge/README.md`](../../packages/lcos-bridge/README.md)

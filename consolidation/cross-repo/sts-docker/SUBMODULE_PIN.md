# sts-docker — submodule pin spec

**Sibling repo:** [lnevo/sts-docker](https://github.com/lnevo/sts-docker)  
**Path in hart:** `consolidation/external/sts-docker`

## Pin (2026-08-31)

| Field | Value |
|-------|--------|
| Commit | `899b45809c99b92614f99990a88fee1dd4e63be2` |
| Local clone | `~/sts/sts-docker` |

## Role

STS PHP runtime (Docker). Pipeline 14 consumer. Desktop `Car Cards/sts-docker/` is a bench copy; canonical path is `~/sts/sts-docker` or `consolidation/external/sts-docker` after submodule init.

## Re-pin

1. Update commit in this file and `cross-repo/SUBMODULE_MANIFEST.yaml`.
2. `cd consolidation/external/sts-docker && git fetch && git checkout <pin>`.
3. Re-run Tier B STS smokes — [`validators/TIER_B_MANUAL_SMOKES.md`](../../validators/TIER_B_MANUAL_SMOKES.md).

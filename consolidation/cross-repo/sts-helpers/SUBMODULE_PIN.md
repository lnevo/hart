# sts-docker-helpers — submodule pin spec

**Sibling repo:** [lnevo/sts-docker-helpers](https://github.com/lnevo/sts-docker-helpers)  
**Path in hart:** `consolidation/external/sts-helpers`

## Pin (2026-08-31)

| Field | Value |
|-------|--------|
| Commit | `31b8583851482d270f45c233f67190d0d8b80c10` |
| Message | Consolidation sts-docker-data backup path + session tooling updates. |
| Local clone | `~/Desktop/HART/Car Cards/sts-docker-helpers/` |

## Role

HART seed generator (`seed/generate_hart_seed.py`), warm-start, session scripts. Reads **`HART_MergedCarRoster.xml`** + `image_metadata.csv`; STS fleet filter excludes passenger/caboose types per ADR car roster SoR.

## Re-pin

1. Update commit in this file and `cross-repo/SUBMODULE_MANIFEST.yaml`.
2. Regenerate seed smoke after roster SoR changes.

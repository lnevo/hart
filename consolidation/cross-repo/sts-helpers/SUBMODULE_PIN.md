# sts-docker-helpers — submodule pin spec

**Sibling repo:** [lnevo/sts-docker-helpers](https://github.com/lnevo/sts-docker-helpers)  
**Path in hart:** `consolidation/external/sts-helpers`

## Pin (2026-08-31)

| Field | Value |
|-------|--------|
| Commit | `cdbbfce8ab2ef915430b8e3eafc31267b518cde5` |
| Message | Align HART workflows to Pre→load_unload→Starting and refresh seed/traffic tooling. |
| Local clone | `~/Desktop/HART/Car Cards/sts-docker-helpers/` |

## Role

HART seed generator (`seed/generate_hart_seed.py`), warm-start, session scripts. Reads **`HART_MergedCarRoster.xml`** + `image_metadata.csv`; STS fleet filter excludes passenger/caboose types per ADR car roster SoR.

## Re-pin

1. Update commit in this file and `cross-repo/SUBMODULE_MANIFEST.yaml`.
2. Regenerate seed smoke after roster SoR changes.

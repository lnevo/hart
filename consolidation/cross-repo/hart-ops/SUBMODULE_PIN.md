# hart-ops — submodule pin spec

**Repo:** [lnevo/hart-ops](https://github.com/lnevo/hart-ops)  
**Path in hart:** `consolidation/external/hart-ops`

## Pin (2026-08-31)

| Field | Value |
|-------|--------|
| Commit | `0fecf5ecf6195b03048f0829fc4b00ee223bc521` |
| Message | Add print SoR: car card templates, waybills, and car_paths resolver. |

## Role

Car inventory SoR (`data/image_metadata.csv`), card pipeline, waybills, publications, industries. STS session scripts remain in `consolidation/external/sts-helpers`.

## Local clone (standalone)

```bash
use consolidation/external/hart-ops submodule
export HART_CAR_IMAGES_FINAL=~/Desktop/HART/Car\ Cards/CarImagesFinal
```

## Re-pin

After hart-ops changes: update pin here and in `SUBMODULE_MANIFEST.yaml`, then `git -C external/hart-ops checkout <pin>` from hart root.

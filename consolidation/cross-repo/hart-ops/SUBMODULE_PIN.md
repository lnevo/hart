# hart-ops — submodule pin spec

**Repo:** [lnevo/hart-ops](https://github.com/lnevo/hart-ops)  
**Path in hart:** `external/hart-ops`

## Pin (2026-08-31)

| Field | Value |
|-------|--------|
| Commit | `c276b85432118bd2d3f02299c3336169181e6670` |
| Message | Initial hart-ops: car SoR, card pipeline, publications, industries. |

## Role

Car inventory SoR (`data/image_metadata.csv`), card pipeline, waybills, publications, industries. STS session scripts remain in `external/sts-helpers`.

## Local clone (standalone)

```bash
git clone git@github.com:lnevo/hart-ops.git ~/hart-ops
export HART_CAR_IMAGES_FINAL=~/Desktop/HART/Car\ Cards/CarImagesFinal
```

## Re-pin

After hart-ops changes: update pin here and in `SUBMODULE_MANIFEST.yaml`, then `git -C external/hart-ops checkout <pin>` from hart root.

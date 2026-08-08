# Live status — HART / CATS

Updated: 2026-08-08 (agent)

## Now

Hand-built Brick `TRACKPLAN` is **not viable** — CATS reported SecEdge mismatches, multiple Block definitions, VitalLogic NPE, ClassCastException.

**Reset:** panels are based on **ArmstrongMagnet** (known-good). Real HART plant must be drawn in **Designer** (`cats/docs/DESIGNER_REQUIRED.md`).

## Try now

```bash
cd /Users/lnevo/Panel
./cats/scripts/launch_cats.sh
# default open hint: cats/panels/HART_smoke_Armstrong.xml
# File → Open that file — expect full Armstrong Digicon track (not blank)
```

Then: `./cats/scripts/launch_designer.sh` → redraw Brick → save `cats/panels/HART.xml`.

## Human replies

<!-- leave notes below -->


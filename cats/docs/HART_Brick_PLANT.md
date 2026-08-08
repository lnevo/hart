# HART Brick plant (CATS)

## What works

CATS only loads panels with **complete** Digicon topology. Cutting out a yard subgraph caused `MyBlock is null` crashes.

**Working approach:** keep the full **ArmstrongMagnet** track plan (same as the smoke test that painted), rename blocks/labels to HART geography. You get a full Digicon board; the west end reads as Brick / West Yard.

| File | Notes |
|------|--------|
| `HART_Brick_magnet.xml` | Full board, HART names, no MQTT — **open this** |
| `HART_Brick.xml` | Same + occupancy on Brick/west blocks |
| `HART_smoke_Armstrong.xml` | Unmodified Armstrong labels (install check) |

## Brick-focused names (west)

| CATS block | Meaning |
|------------|---------|
| Main West, West Main Ext | Approach |
| OS 100 (Brick), OS 101 (Brick) | Switch plants |
| Block 100-102 | Between them |
| West Yard 1 / 2 | Yard tracks |

East/south names (Plane, South Yard, East End, Princess, etc.) are mapped onto the rest of the Armstrong geometry as placeholders until a Designer redraw.

## Try

```bash
./cats/scripts/launch_cats.sh
# File → Open HART_Brick_magnet.xml
# Should look like Armstrong smoke, with "West Yard / Brick" etc. labels
```

True Neville Island geometry (matching Layout Editor) still needs a **Designer** redraw later; this is the loadable Digicon CTC stand-in.

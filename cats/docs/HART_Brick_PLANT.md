# HART Brick plant (CATS)

Drawn by extracting the **ArmstrongMagnet yard interlocking** (proven topology), rebasing it, and renaming blocks to HART Brick.

## Files

| File | Purpose |
|------|---------|
| `panels/HART_Brick_magnet.xml` | **Open this first** — Digicon Brick plant, no MQTT IO |
| `panels/HART_Brick.xml` | Same track + MQTT occupancy + Switch 100/101 |
| `panels/HART_smoke_Armstrong.xml` | Full Armstrong board (install smoke test) |

## Named blocks

| CATS block | Role |
|------------|------|
| Main West | West approach |
| OS 100 (Brick) | Switch 100 plant |
| Block 100-102 | Between 100 and 101 |
| OS 101 (Brick) | Switch 101 plant |
| West Yard 1 / 2 | Yard tracks |

## Try

```bash
./cats/scripts/launch_cats.sh
# File → Open cats/panels/HART_Brick_magnet.xml
# expect Digicon yard/Brick shape (not blank, not Armstrong full board)

./cats/scripts/launch_cats.sh cats/panels/HART_Brick.xml
# then test occupancy / throws
```

If magnet paints but wired crashes, stay on magnet and bind devices in Designer (safer for feedback timing).

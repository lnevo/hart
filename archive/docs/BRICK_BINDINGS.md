# Brick plant — Designer bind cheat-sheet

Copy these user names into CATS Designer for the first live plant.

## Occupancy

| Designer block name | Occupied report (JMRI sensor userName) |
|---------------------|------------------------------------------|
| OS 1 | `Block 4-2` |
| OS 3 | `Block 4-1` |
| OS Main West Brick–Plane | `Block 4-6` |
| OS Main West | `Block 2-1` |
| OS West Main Ext | `Block 1-8` |
| OS W-1 | (see `occupancy_bindings.csv`) |
| OS W-2 | (see `occupancy_bindings.csv`) |

## Points

| OS | Turnout command (prefer system name) | Layout ident |
|----|----------------------------------------|--------------|
| OS 1 | `M2T408` (Switch 1) | TOL3 |
| OS 3 | `M2T409` (Switch 3) | TOL38 |

## Adjacent (wire after Brick proves out)

| Plant | OS | Turnout |
|-------|-----|---------|
| Plane | OS 5 | `M2T410` |
| West Yard | OS 13–119 | Switch 13–119 |

## Test

1. Occupy Brick OS physically or force sensor `Block 4-2` → CATS colors OS 1.
2. Throw `M2T408` from CATS → field switch 100 + LE panel follow.
3. Confirm NextTrain is not also commanding.

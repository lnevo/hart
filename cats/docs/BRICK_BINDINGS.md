# Brick plant — Designer bind cheat-sheet

Copy these user names into CATS Designer for the first live plant.

## Occupancy

| Designer block name | Occupied report (JMRI sensor userName) |
|---------------------|------------------------------------------|
| OS 100 | `Block 4-2` |
| OS 101 | `Block 4-1` |
| Main West Brick–Plane | `Block 4-6` |
| Main West | `Block 2-1` |
| West Main Ext | `Block 1-8` |
| W-1 | (see `occupancy_bindings.csv`) |
| W-2 | (see `occupancy_bindings.csv`) |

## Points

| OS | Turnout command (prefer system name) | Layout ident |
|----|----------------------------------------|--------------|
| OS 100 | `M2T408` (Switch 100) | TOL3 |
| OS 101 | `M2T409` (Switch 101) | TOL38 |

## Adjacent (wire after Brick proves out)

| Plant | OS | Turnout |
|-------|-----|---------|
| Plane | OS 102 | `M2T410` |
| West Yard | OS 116–119 | Switch 116–119 |

## Test

1. Occupy Brick OS physically or force sensor `Block 4-2` → CATS colors OS 100.
2. Throw `M2T408` from CATS → field switch 100 + LE panel follow.
3. Confirm NextTrain is not also commanding.

# HART Digicon map

Primary board is built from **JMRI Layout Editor** turnout coordinates + tip-block
connectivity (`hart_prod.xml`), not from invented Designer filler.

```bash
python3 cats/scripts/build_hart_digicon_from_le.py --mqtt
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART.xml
```

## What the builder uses

| LE source | Digicon use |
|-----------|-------------|
| `layoutturnout` xcen order | West→east plant columns |
| ycen clusters | Upper parallel (y≈252) vs main spine vs yard ladders |
| Segment `TURNOUT_A/B/C/D` tip blocks | Entry/exit neighbors for each plant |
| `layoutblock` + MQTT sensors | Occupancy on every named block |
| `turnout_bindings.csv` | Plant ↔ JMRI turnout identity |

## Rows

| Y | Role (LE) |
|---|-----------|
| 1 | Upper parallel: Main West → OS 111a/b → West Main Ext → OS 113b → OS 115 → McKees Rocks |
| 2 | Main spine: Brick → 100-102 → Plane → EME → 117b → Main East → 112 → East Lead → 113a → 114 → McKeesport |
| 3 | West Yard 116–119 + South Yard 103–106 + East End 107–110 |
| 4 | Yard T1/T6 + Yard Tracks 1–5 |

## Coverage

All occupancy names from `cats/data/occupancy_bindings.csv` and all 20 LE
turnouts as `SWITCHPOINTS` plants (111b is the CD mate of TO111).

Gate-1 Designer draw remains available via `wire_designer_ctc_rules.py` for
hand-tuning Brick/Plane only — it is not the full-railroad primary.

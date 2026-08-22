# HART Digicon map

Two boards are maintained:

| Panel | Source | Role |
|-------|--------|------|
| `cats/panels/HART.xml` | Designer `HART_designer_raw.xml` + `wire_designer_ctc_rules.py` | **Primary** Gate 1 |
| `cats/panels/HART_le.xml` | JMRI LE tip connectivity + `build_hart_digicon_from_le.py` | **WIP** Gate 1–5 schematic |

```bash
# Primary (Designer Gate 1)
python3 cats/scripts/wire_designer_ctc_rules.py --mqtt
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART.xml

# LE full railroad (WIP — does not overwrite HART.xml)
python3 cats/scripts/build_hart_digicon_from_le.py --mqtt
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART_le.xml
```

## What the LE builder uses

| LE source | Digicon use |
|-----------|-------------|
| `layoutturnout` xcen order | West→east plant columns |
| ycen clusters | Upper parallel (y≈252) vs main spine vs yard ladders |
| Segment `TURNOUT_A/B/C/D` tip blocks | Entry/exit neighbors for each plant |
| `layoutblock` + MQTT sensors | Occupancy on every named block |
| `turnout_bindings.csv` | Plant ↔ JMRI turnout identity |

## LE rows (after Y+1 shift)

| Y | Role (LE) |
|---|-----------|
| 1 | Labels |
| 2 | Upper parallel: Main West → OS 111a/b → West Main Ext → OS 113b → OS 115 → McKees Rocks |
| 3 | Main spine: Brick → 100-102 (HORIZONTAL) → Plane → EME → 117b → Main East → 112 → East Lead → 113 → 114 → McKeesport |
| 4 | W-116–119 + S-103–106 + East End 107–110 |
| 5 | Scale/T6 + Yard Tracks 1–5 |

## Coverage

| Board | Named blocks | Notes |
|-------|--------------|-------|
| Designer `HART.xml` | 14 | Gate 1 + partial West Yard (116/117); 117b merged into 117 |
| LE `HART_le.xml` | 43 | All names from `occupancy_bindings.csv`; 22 SWITCHPOINTS plants |

Gate-1 Designer draw remains authoritative for Neville LH100 geography until Mac accept promotes a fuller board. LE keeps Brick-Plane on the **continuing HORIZONTAL** (not a diverge into Plane).

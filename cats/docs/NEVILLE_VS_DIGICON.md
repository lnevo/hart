# Neville Island (JMRI) vs HART Digicon (CATS)

## Topology (Neville Island — SoR)

```
West Yard ── Brick(100/101) ── OS Brick-Plane ── Plane(102) ── …
        │         │ LH100 continuing = main east into 100-102
        │         └── diverge = yard / OS 3
        └── ladder 116–119 / 117b …
South Yard · East End · OS East Lead · Princess (OS McKees Rocks / OS McKeesport)
```

## Digicon status

| Approach | Status |
|----------|--------|
| Chubb/Armstrong **rename** | Rejected as primary — wrong route roles (e.g. 100–102 on plant approach) |
| **Gate 1 abutted fragments** | Interim only (`jmri_to_cats_digicon.py --only gate1`) |
| **Designer plant-by-plant** | **Primary** Gate 1 — `cats/panels/HART.xml` ([`GATE1_BRICK_PLANE.md`](GATE1_BRICK_PLANE.md)) |
| **LE tip schematic** | WIP Gate 1–5 — `cats/panels/HART_le.xml` (100–102 on HORIZONTAL; needs Mac accept) |

## Operator guidance

1. Draw / accept Gate 1 per checklist (LH100 continuing = straight).  
2. Expand Gates 2–5 ([`GATE2_PLUS.md`](GATE2_PLUS.md)).  
3. Always launch with Local Network: `CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh`.

Occupancy bindings: `M2S` DECADDRs from hart layoutblocks / `occupancy_bindings.csv`.
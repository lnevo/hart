# Neville Island (JMRI) vs HART Digicon (CATS)

## Topology (Neville Island — SoR)

```
West Yard ── Brick(100/101) ── Block 100-102 ── Plane(102) ── …
        │         │ LH100 continuing = main east into 100-102
        │         └── diverge = yard / OS 101
        └── ladder 116–119 / 117b …
South Yard · East End · East Lead · Princess (McKees Rocks / McKeesport)
```

## Digicon status

| Approach | Status |
|----------|--------|
| Chubb/Armstrong **rename** | Rejected as primary — wrong route roles (e.g. 100–102 on plant approach) |
| **Gate 1 abutted fragments** | Interim primary — long HORIZONTAL 100–102 between Brick and Plane |
| **Designer plant-by-plant** | Authoritative path (ADR-004) — [`GATE1_BRICK_PLANE.md`](GATE1_BRICK_PLANE.md) |

## Operator guidance

1. Draw / accept Gate 1 per checklist (LH100 continuing = straight).  
2. Expand Gates 2–5 ([`GATE2_PLUS.md`](GATE2_PLUS.md)).  
3. Always launch with Local Network: `CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh`.

Occupancy bindings: `M2S` DECADDRs from hart layoutblocks / `occupancy_bindings.csv`.
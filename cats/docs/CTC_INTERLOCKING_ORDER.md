# HART Digicon interlocking order (dispatcher SoR)

West → east on the **main**. Yards hang off plants — they are not inserted as a fake “station” between Plane and South Yard.

```
Main West ═══[ 100 Brick ]═══ Brick-Plane ═══[ 102 Plane ]═══ East Main Ext ═══[ 117 Barn ]═══ Main East ═══ …
                  │                                 │                              │
                  │                                 │                              ├─ yard side: Scale ↔ Barn
                  ▼                                 ▼                              ▼
            [ 101 ]                            Scale (lead)              [ TO1 trailing ]
         N → W-1                      (south-yard west lead)        N → eng terminal (118/119/T9–T11)
         R → W-2                                                    R → OS 103 → S-104–106
```

## JMRI tip truth (`hart_prod.xml`)

| Plant | Tips | Continuing |
|-------|------|------------|
| TOL3 Brick | A=Main West, B=OS100, C=Brick-Plane | → 100-102 |
| TOL38 101 | A=OS101, B=W-1, C=W-2 | → WY1 (normal) |
| TOL42 Plane | A=100-102, B=East Main Ext, C=Scale | → EME |
| TO117 Barn | A=Scale, B=Barn, C=Main East, D=EME | crossover main ↔ yard lead |
| TO1 | A=OS103, B=Barn, C=OS118 | trailing into eng terminal vs South Yard |
| TOR14…TOL19 | South Yard ladder 103–106 | yard tracks 1–5 |

## Station labels (Digicon) — PR #4 order

BRICK → PLANE → WEST YARD / ENG → MAIN EAST → **112** → EAST LEAD → EAST END → **PRINCESS**
(with **111 / WME** on the upper parallel into **113 top**)

- **Runaround:** Plane → East Main Ext → 117 → Main East → 112 → East Lead.
- **Engine terminal** hangs off the **yard lead / TO1** (not off the main).
- **East End 107–110** is the east end of South Yard; **110 feeds East Lead → Princess**.
- **Princess 113 top** → WME → **111** (virtual return to Main West @ Brick).
- Digicon cells use **HORIZONTAL + 45° slash plants** (PR4 diagonal language). CATS cannot render Pillow PNG art.

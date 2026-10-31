# HART Digicon interlocking order (dispatcher SoR)

West → east on the **main**. Yards hang off plants — they are not inserted as a fake “station” between Plane and South Yard.

```
OS Main West ═══[ 100 Brick ]═══ OS Brick-Plane ═══[ 102 Plane ]═══ OS East Main Ext ═══[ 117 OS Barn ]═══ OS Main East ═══ …
                  │                                 │                              │
                  │                                 │                              ├─ yard side: OS Scale ↔ OS Barn
                  ▼                                 ▼                              ▼
            [ 101 ]                            OS Scale (lead)              [ TO1 trailing ]
         N → OS W-1                      (south-yard west lead)        N → eng terminal (118/119/T9–T11)
         R → OS W-2                                                    R → OS 15 → S-104–106
```

## JMRI tip truth (`hart_prod.xml`)

| Plant | Tips | Continuing |
|-------|------|------------|
| TOL3 Brick | A=OS Main West, B=OS100, C=OS Brick-Plane | → 100-102 |
| TOL38 101 | A=OS101, B=OS W-1, C=OS W-2 | → WY1 (normal) |
| TOL42 Plane | A=100-102, B=OS East Main Ext, C=OS Scale | → EME |
| TO117 OS Barn | A=OS Scale, B=OS Barn, C=OS Main East, D=EME | crossover main ↔ yard lead |
| TO1 | A=OS103, B=OS Barn, C=OS118 | trailing into eng terminal vs South Yard |
| TOR14…TOL19 | South Yard ladder 103–106 | yard tracks 1–5 |

## Station labels (Digicon) — PR #4 order

BRICK → PLANE → WEST YARD / ENG → MAIN EAST → **112** → EAST LEAD → EAST END → **PRINCESS**
(with **111 / WME** on the upper parallel into **113 top**)

- **Runaround:** Plane → OS East Main Ext → 117 → OS Main East → 112 → OS East Lead.
- **Engine terminal** hangs off the **yard lead / TO1** (not off the main).
- **East End 107–110** is the east end of South Yard; **110 feeds OS East Lead → Princess**.
- **Princess 113 top** → WME → **111** (virtual return to OS Main West @ Brick).
- Digicon cells use **HORIZONTAL + 45° slash plants** (PR4 diagonal language). CATS cannot render Pillow PNG art.

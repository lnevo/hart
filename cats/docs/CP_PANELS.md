# HART control-point Digicon panels (critique set)

Each panel is **one CP** drawn to the Neville station-map sheet language.
Critique these individually before we reassemble the full Digicon.

Station maps: `cats/docs/station_maps/`

Rebuild: `python3 cats/scripts/build_hart_cp_panels.py`

**All CPs left-to-right (spaced):** [`HART_cp_all.xml`](../panels/cp/HART_cp_all.xml) · [schematic](../screenshots/cp/HART_cp_all.png)

```bash
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/cp/HART_cp_all.xml
```

Launch one: `CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/cp/HART_cp_100.xml`

| CP | Sheet | Title | Panel | Schematic | Verify |
|----|-------|-------|-------|-----------|--------|
| **101** | West Yard | CP 101 — OS W-1 / OS W-2 merge | [`HART_cp_101.xml`](../panels/cp/HART_cp_101.xml) | — | PASS |
| **100** | West Yard | CP 100 — Brick (OS Main West / to Plane) | [`HART_cp_100.xml`](../panels/cp/HART_cp_100.xml) | — | PASS |
| **102** | West Yard | CP 102 — Plane (West Lead / OS Main East) | [`HART_cp_102.xml`](../panels/cp/HART_cp_102.xml) | — | PASS |
| **117** | West Yard | CP 117 — OS Barn crossover | [`HART_cp_117.xml`](../panels/cp/HART_cp_117.xml) | — | PASS |
| **116** | South Yard | CP 116 — West Lead / OS EH-3...3 | [`HART_cp_116.xml`](../panels/cp/HART_cp_116.xml) | — | PASS |
| **103** | South Yard | CP 103 — West Lead -> OS S-R + ladder | [`HART_cp_103.xml`](../panels/cp/HART_cp_103.xml) | — | PASS |
| **104** | South Yard | CP 104 — ladder -> OS S-1 | [`HART_cp_104.xml`](../panels/cp/HART_cp_104.xml) | — | PASS |
| **105** | South Yard | CP 105 — ladder -> OS S-2 | [`HART_cp_105.xml`](../panels/cp/HART_cp_105.xml) | — | PASS |
| **106** | South Yard | CP 106 — OS S-3 + OS S-4 | [`HART_cp_106.xml`](../panels/cp/HART_cp_106.xml) | — | PASS |
| **111** | East End | CP 111 — OS Main West ↔ OS Main East | [`HART_cp_111.xml`](../panels/cp/HART_cp_111.xml) | — | PASS |
| **110** | East End | CP 110 — OS Main East / OS S-R + EE ladder | [`HART_cp_110.xml`](../panels/cp/HART_cp_110.xml) | — | PASS |
| **109** | East End | CP 109 — ladder -> OS S-1 | [`HART_cp_109.xml`](../panels/cp/HART_cp_109.xml) | — | PASS |
| **108** | East End | CP 108 — ladder -> OS S-2 | [`HART_cp_108.xml`](../panels/cp/HART_cp_108.xml) | — | PASS |
| **107** | East End | CP 107 — OS S-3 + OS S-4 | [`HART_cp_107.xml`](../panels/cp/HART_cp_107.xml) | — | PASS |
| **112** | East End | CP 112 — OS East Lead / OS Main East to OS Barn | [`HART_cp_112.xml`](../panels/cp/HART_cp_112.xml) | — | PASS |
| **113** | Shenango | CP 113 — Princess crossover | [`HART_cp_113.xml`](../panels/cp/HART_cp_113.xml) | — | PASS |
| **115** | Shenango | CP 115 — OS Main West -> OS K-1 | [`HART_cp_115.xml`](../panels/cp/HART_cp_115.xml) | — | PASS |
| **114** | Shenango | CP 114 — OS Main East -> OS K-2 | [`HART_cp_114.xml`](../panels/cp/HART_cp_114.xml) | — | PASS |

## Suggested review order

1. West Yard: **101 -> 100 -> 102 -> 117** (matches West Yard sheet left->right)
2. South Yard: **116/ET -> 103 -> 104 -> 105 -> 106**
3. East End: **111 -> 110 -> 109 -> 108 -> 107 -> 112**
4. Shenango: **113 -> 115 -> 114**

For each CP, confirm: plant geometry, which tracks join, and destination labels
(`to Brick`, `West Lead`, `OS S-R`, `OS K-1`, ...) against the station-map PNG.


# Neville station maps → Digicon CTC

Source maps (Car Cards docs → extracted under `cats/docs/station_maps/`):

| Map | Digicon role |
|-----|----------------|
| West Yard | CP Brick 100 / 101, Plane 102, Barn 117, West Lead |
| South Yard | West Lead → ET + ladder 103–106 → S-1…S-5 (Fall River A/D style) |
| East End | Ladder 107–110, 111 x-over, 112, mains → Princess |
| Shenango (+ rotated) | Princess 113–115, K-1/K-2, Rocks / McKeesport |

Visual SoR for yard body: CATS sample [cats.jpg](https://cats4ctc.wdfiles.com/local--files/home:home/cats.jpg) **FALL RIVER A/D 1–4** — parallel horizontal tracks fed by a diagonal ladder.

**Labels (station-map language):**
- On-track `STATION` shows map names (`W-1`, `West Lead`, `S-1`…`S-5`, `K-1`/`K-2`, CP `100`…`115`) while `NAME` stays the JMRI occupancy id.
- Header/footer `SEC_NAME` callouts spell connections: e.g. `103→S-1`, `West Lead: Plane → Barn → 103 → S-1`, `112 → East Lead → Princess`.

Block / turnout names: `cats/data/occupancy_bindings.csv`, `turnout_bindings.csv`.

**Sheet panels (critique unit = station-map doc):**

| Sheet | Builder | Panel |
|-------|---------|-------|
| West Yard | `wire_hart_sheet_west_yard2.py` | `cats/panels/sheets/HART_sheet_West_Yard2.xml` |
| South Yard + East End CPs | `compose_hart_sheet_west_yard2_row2.py` (row under West Yard) | same panel |
| Shenango | *(next)* | |

```bash
python3 cats/scripts/wire_hart_sheet_west_yard2.py --with-row2
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/sheets/HART_sheet_West_Yard2.xml
```

Full railroad Digicon only after each sheet is signed off.

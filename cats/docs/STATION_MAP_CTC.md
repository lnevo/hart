# Neville station maps → Digicon CTC

Source maps (Car Cards docs → extracted under `cats/docs/station_maps/`):

| Map | Digicon role |
|-----|----------------|
| West Yard | CP Brick 100 / 101, Plane 102, OS Barn 117, West Lead |
| **Barn** | Local sheet for **Switch 7 / 9 / 11 / 13** (LE: TO117 xover, TO10, TO11, TO1). Rebuild: `python3 cats/scripts/render_barn_station_map.py`. SM-06 docx in hart-ops. South Yard still shows Barn in context. |
| South Yard | West Lead → **EH-1 / EH-2 / EH-3** (shrunken Barn plant) + **Switch 13** + ladder **15 / 17 / 19 / 21**; **Switch 7** Barn xover. Rebuild: `python3 cats/scripts/render_south_yard_station_map.py`. |
| East End | Ladder 107–110, 111 x-over, 112, mains → Princess |
| Shenango (+ rotated) | Princess 113–115, OS K-1/OS K-2, Rocks / OS McKeesport |

Visual SoR for yard body: CATS sample [cats.jpg](https://cats4ctc.wdfiles.com/local--files/home:home/cats.jpg) **FALL RIVER A/D 1–4** — parallel horizontal tracks fed by a diagonal ladder.

**Labels (station-map language):**
- On-track `STATION` shows map names (`OS W-1`, `West Lead`, `OS S-R`…`OS S-4`, `OS K-1`/`OS K-2`, CP `100`…`115`) while `NAME` stays the JMRI occupancy id.
- Header/footer `SEC_NAME` callouts spell connections: e.g. `15→OS S-R`, `West Lead: Plane → OS Barn → 15 → OS S-R`, `112 → OS East Lead → Princess`.

Block / turnout names: `cats/data/occupancy_bindings.csv`, `turnout_bindings.csv`.

**Sheet panels:** West Yard sheets are archived at `cats/panels/sheets/archive/west_yard/`. Live Digicon is Master 4.

```bash
python3 cats/scripts/wire_hart_master4.py --live
```

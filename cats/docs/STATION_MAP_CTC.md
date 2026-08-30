# Neville station maps → Digicon CTC

Source maps (Car Cards docs → extracted under `cats/docs/station_maps/`):

| Map | Digicon role |
|-----|----------------|
| West Yard | CP Brick 100 / 101, Plane 102, OS Barn 117, West Lead |
| South Yard | West Lead → ET + ladder 103–106 → OS S-R…OS S-4 (Fall River A/D style) |
| East End | Ladder 107–110, 111 x-over, 112, mains → Princess |
| Shenango (+ rotated) | Princess 113–115, OS K-1/OS K-2, Rocks / OS McKeesport |

Visual SoR for yard body: CATS sample [cats.jpg](https://cats4ctc.wdfiles.com/local--files/home:home/cats.jpg) **FALL RIVER A/D 1–4** — parallel horizontal tracks fed by a diagonal ladder.

**Labels (station-map language):**
- On-track `STATION` shows map names (`OS W-1`, `West Lead`, `OS S-R`…`OS S-4`, `OS K-1`/`OS K-2`, CP `100`…`115`) while `NAME` stays the JMRI occupancy id.
- Header/footer `SEC_NAME` callouts spell connections: e.g. `103→OS S-R`, `West Lead: Plane → OS Barn → 103 → OS S-R`, `112 → OS East Lead → Princess`.

Block / turnout names: `cats/data/occupancy_bindings.csv`, `turnout_bindings.csv`.

**Sheet panels:** West Yard sheets are archived at `cats/panels/sheets/archive/west_yard/`. Live Digicon is Master 4.

```bash
python3 cats/scripts/wire_hart_master4.py --live
```

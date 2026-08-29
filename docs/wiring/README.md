# HART LCOS wiring documentation

Git copy of the Desktop `HART/Wiring Documentation` package, refreshed against current public names and Digicon searchlight heads.

Desktop originals stay at `~/Desktop/HART/Wiring Documentation/`. That tree is **not** git — it has a Python venv and an `ARCHIVE/` of every inventory bump. Root `.gitignore` still ignores a repo-root `Wiring Documentation/` folder so that checkout is not committed by accident.

## Current files

| File | Role |
|------|------|
| [`LCOS_Layout_Inventory_v85.xlsx`](LCOS_Layout_Inventory_v85.xlsx) | LCOS nodes, DNOU8/DNIN8, block sensors, turnout summary. **DigiconSignals** sheet is generated from `cats/data/signal_wiring.csv`. **Node ID = C{radio Address}** (helix DCC is **D5**). **Legacy Node ID** is the old sequential C1–C13 / D1 label. |
| [`Wiring_Schematic.pptx`](Wiring_Schematic.pptx) | One slide per client node, regenerated from v85. |
| [`signals_asbuilt_abs_v2.xlsx`](signals_asbuilt_abs_v2.xlsx) | Live lower-deck Digicon ABS matrix (100L, 117LA, 114LA, …). |
| [`signals_split_v8.xlsx`](signals_split_v8.xlsx) | Frozen Nov 2025 **planned RGB** matrix (`S1-1`…`S6-15`). Upper deck still uses this plan. Do not rename those IDs to Digicon 11x names. |
| [`imported/`](imported/) | Unmodified Desktop snapshots (v84, asbuilt v1, split v8, v84 changelog). Sequential C1–C13 IDs. |

CSV source of truth for Digicon ports: [`cats/data/signal_wiring.csv`](../../cats/data/signal_wiring.csv). Public block names: [`occupancy_bindings.csv`](../../cats/data/occupancy_bindings.csv) / [ADR-005](../../wiki/decisions/ADR-005-public-equipment-names.md).

**Enclosure = radio Address.** Cabinets sit with their plants: **C4** Brick+Plane, **C13** Barn, **C12** East End 34, **C2** East End west 24, **C1** Princess west (36+38), **C11** Princess east (40) + balloon. **C3** is 103–106 motors only (no Digicon heads). Packed MQTT = radio. Never **D5**.

**Block-sensor calibration:** every node that has occupancy detectors reserves **pin 8 of its first 5V DNOU8** for detector calibration current (not a lamp, not a relay). First 5V board is the lowest-numbered OU on the 5V rail (OU1 when that board is 5V; otherwise OU2).

## Digicon heads and OU boards

Pin-level source: [`cats/data/signal_wiring.csv`](../../cats/data/signal_wiring.csv). G/Y/R is one 3-pin `STOP/APPROACH/CLEAR` object. **T** = top, **B** = bottom, blank = dwarf. Each 2-head mast uses 6 consecutive pins on one DNOU8 so that board can sit next to the mast. A neighboring dwarf uses the leftover 2; the 3rd pin spills to the adjacent cluster when the plant needs 9.

New 5V **OU4** on C1 / C4 / C13 only.

### C4 — Brick + Plane (radio 4, packed `4xx`)

OU1 stays 12V motors Switch 1 / 3 / 5 / 13 (this box is already at the plant). Place **OU2** at Plane, **OU3** at Brick east (2L), **OU4** at Brick west (4RA/4RB).

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 12V | Switch 1, 3, 5, 13 motors |
| OU2 | 5V | 6LB T+B, 6LA G; **OU2-8 block-sensor cal** |
| OU3 | 5V | 2L T+B, 6LA Y/R |
| **OU4** | 5V **new** | 4RA, 4RB; OU4-7/8 spare |

| Mast | Disc | Packed | G | Y | R |
|------|------|--------|---|---|---|
| 6LB | T | `IH432` | OU2-1 | OU2-2 | OU2-3 |
| 6LB | B | `IH433` | OU2-4 | OU2-5 | OU2-6 |
| 6LA | | `IH434` | OU2-7 | OU3-8 | OU3-7 |
| 2L | T | `IH438` | OU3-1 | OU3-2 | OU3-3 |
| 2L | B | `IH439` | OU3-4 | OU3-5 | OU3-6 |
| 4RA | | `IH436` | OU4-1 | OU4-2 | OU4-3 |
| 4RB | | `IH437` | OU4-4 | OU4-5 | OU4-6 |

`IH435` stays an unused packed hole.

### C13 — Barn (radio 13)

Place **OU1** with 8RA (left), **OU4** with 8RB (left), **OU2** with 8LA+8LB (right). 8LB R spills to the 8RB board.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 5V | 8RA T+B; OU1-7 leftover S3-14 G; **OU1-8 block-sensor cal** |
| OU2 | 5V | 8LA T+B, 8LB G/Y |
| OU3 | 12V | Switch 7, 11, 9 motors; OU3-7/8 spare |
| **OU4** | 5V **new** | 8RB T+B, 8LB R; OU4-8 spare |

| Mast | Disc | Packed | G | Y | R |
|------|------|--------|---|---|---|
| 8RA | T | `IH1332` | OU1-1 | OU1-2 | OU1-3 |
| 8RA | B | `IH1333` | OU1-4 | OU1-5 | OU1-6 |
| 8RB | T | `IH1335` | OU4-1 | OU4-2 | OU4-3 |
| 8RB | B | `IH1336` | OU4-4 | OU4-5 | OU4-6 |
| 8LA | T | `IH1337` | OU2-1 | OU2-2 | OU2-3 |
| 8LA | B | `IH1338` | OU2-4 | OU2-5 | OU2-6 |
| 8LB | | `IH1334` | OU2-7 | OU2-8 | OU4-7 |

### C12 — East End 34 (radio 12, packed `12xx`)

Same box as Switch 25–33. Place **OU2+OU3** at 34. 32R leftover sits on these boards.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 12V | Switch 25, 27, 29, 31 motors |
| OU2 | 5V | 34L T+B, 32R G; **OU2-8 block-sensor cal** |
| OU3 | 5V | 34R T+B, 32R Y/R |
| OU4 | 12V | Switch 23, 33 motors |

| Mast | Disc | Packed | G | Y | R |
|------|------|--------|---|---|---|
| 34L | T | `IH1232` | OU2-1 | OU2-2 | OU2-3 |
| 34L | B | `IH1233` | OU2-4 | OU2-5 | OU2-6 |
| 32R | | `IH1234` | OU2-7 | OU3-8 | OU3-7 |
| 34R | T | `IH1235` | OU3-1 | OU3-2 | OU3-3 |
| 34R | B | `IH1236` | OU3-4 | OU3-5 | OU3-6 |

Old East End `2xx` holes `IH235`–`IH237` / `IH240`–`IH241` are unused.

### C2 — East End west overflow (radio 2, packed `2xx`)

C2 sits on the **west end of East End** — 24RA / 24L / 24RB only. 24RB lives on leftover OU3 so that dwarf stays on one board.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 5V | 24RA T+B; OU1-7 spare; **OU1-8 block-sensor cal** |
| OU2 | 5V | 24L T+B; OU2-7 spare; **OU2-8 relay** |
| OU3 | 5V | leftover S2 RGB; **24RB G/Y/R on 6–8** |

| Mast | Disc | Packed | G | Y | R |
|------|------|--------|---|---|---|
| 24RA | T | `IH232` | OU1-1 | OU1-2 | OU1-3 |
| 24RA | B | `IH238` | OU1-4 | OU1-5 | OU1-6 |
| 24RB | | `IH234` | OU3-6 | OU3-7 | OU3-8 |
| 24L | T | `IH233` | OU2-1 | OU2-2 | OU2-3 |
| 24L | B | `IH239` | OU2-4 | OU2-5 | OU2-6 |

### C1 — Princess west (radio 1, packed `1xx`)

Place **OU2+OU3** at Switch 35 (36RA / 36RB), **OU4** at Switch 37 (38LB). 38LA uses the leftover trio on the 36 boards (OU3-7/8 + OU2-7) so G/Y are not on OU4.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 12V | Switch 35, 37, 39 motors; OU1-7/8 reserved |
| OU2 | 5V | 36RA T+B, 38LA R; **OU2-8 block-sensor cal** |
| OU3 | 5V | 36RB T+B, 38LA G/Y |
| **OU4** | 5V **new** | 38LB T+B; OU4-7/8 spare |

| Mast | Disc | Packed | G | Y | R |
|------|------|--------|---|---|---|
| 36RA | T | `IH135` | OU2-1 | OU2-2 | OU2-3 |
| 36RA | B | `IH136` | OU2-4 | OU2-5 | OU2-6 |
| 36RB | T | `IH132` | OU3-1 | OU3-2 | OU3-3 |
| 36RB | B | `IH133` | OU3-4 | OU3-5 | OU3-6 |
| 38LB | T | `IH139` | OU4-1 | OU4-2 | OU4-3 |
| 38LB | B | `IH140` | OU4-4 | OU4-5 | OU4-6 |
| 38LA | | `IH143` | OU3-7 | OU3-8 | OU2-7 |

### C11 — Princess east + balloon (radio 11, packed `11xx`)

Place **OU2** at SW39 (40), **OU3** at the balloon. 40LA R spills to the balloon board. Balloon packed IDs stay `1133` / `1134`.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 12V | SW129, SW127, SW138 motors; OU1-7/8 spare |
| OU2 | 5V | 40LB T+B, 40LA G; **OU2-8 block-sensor cal** |
| OU3 | 5V | 2036, 2035, 40LA Y/R |

| Mast | Disc | Packed | G | Y | R |
|------|------|--------|---|---|---|
| 40LB | T | `IH1132` | OU2-1 | OU2-2 | OU2-3 |
| 40LB | B | `IH1135` | OU2-4 | OU2-5 | OU2-6 |
| 40LA | | `IH1136` | OU2-7 | OU3-8 | OU3-7 |
| 2036 | | `IH1133` | OU3-1 | OU3-2 | OU3-3 |
| 2035 | | `IH1134` | OU3-4 | OU3-5 | OU3-6 |

`signals_split_v8.xlsx` stays the frozen RGB plan.

Block-sensor calibration pin (first 5V OU, channel 8):

| Node | Port |
|------|------|
| C1 | C1-OU2-8 |
| C2 | C2-OU1-8 |
| C3 | C3-OU2-8 |
| C4 | C4-OU2-8 |
| C11 | C11-OU2-8 |
| C12 | C12-OU2-8 |
| C13 | C13-OU1-8 |
| C14 | C14-OU2-8 |
| C21 | C21-OU2-8 |
| C22 | C22-OU2-8 |
| C23 | C23-OU2-8 |
| C24 | C24-OU2-8 |

Relays that used to sit on those pins (C3, C14, C21–C24) need a different 5V channel.

### Other cabinets (no Digicon 3-pin heads)

These OUs stay motors / planned RGB (`S*-*`) / relays. Do not overlay Digicon searchlights here. **D5** is helix DCC (no DNOU8).

| Node | Radio | Plant | Boards |
|------|------:|-------|--------|
| C3 | 3 | West lower | OU1 12V Switch 15–21 motors; OU2/OU3 5V leftover RGB; **OU2-8 BS cal** |
| C14 | 14 | West upper | OU1 12V SW144–SW147; OU2/OU3 5V S6-* + relay |
| C21 | 21 | Helix upper | OU1 12V NIX (SW125/126/139/140); OU2/OU3 5V S4-* + relay |
| C22 | 22 | North upper | OU1 12V DJE/DJW (SW120–123); OU2/OU3 5V S5-1…5 + relay |
| C23 | 23 | West upper | OU1 12V SW143 / CBX (SW141/142); OU2/OU3 5V S6-* + relay |
| C24 | 24 | Peninsula upper | OU1 12V SW148–SW150 + S6-10 G/R; OU2/OU3 5V S6-* + relay |
| C32 | 32 | North upper | OU1 12V SW124; OU2 5V S5-6/7 |

Copy the three current workbooks **and** `Wiring_Schematic.pptx` back to `~/Desktop/HART/Wiring Documentation/` after a refresh (and after XML apply) so the bench copy matches git.

## Refresh

```bash
python3 docs/wiring/scripts/refresh_wiring_docs.py
# needs python-pptx (Desktop wiring venv is fine):
python3 docs/wiring/scripts/create_wiring_schematic_ppt.py
```

Copy `LCOS_Layout_Inventory_v85.xlsx`, `signals_asbuilt_abs_v2.xlsx`, `signals_split_v8.xlsx`, and `Wiring_Schematic.pptx` to `~/Desktop/HART/Wiring Documentation/`. Do not refresh Desktop until JMRI XML is applied so the bench pack matches live beans.

## What v85 changed vs Desktop v84

- Lower-deck **BlockSensors** names follow the panel: Scale, Barn, S-1…S-5, W-1/W-2, EH-1…EH-3, OS 100… (MQTT `Block n-n` stays in Notes).
- **DNOU8** ports listed in `signal_wiring.csv` are overlayed as searchlight heads (replacing planned RGB `S3-6 G` etc. on those ports). Previous RGB label is kept in Notes.
- **D1-OU2/OU3** Princess rows were a mistaken overlay (D1 is DCC radio 5, now labeled **D5**). Princess is on C1; do not recreate D5 signal boards.
- Upper-deck RGB (`S4-*` / `S5-*` / `S6-*`) left as planned.
- **Node ID = radio Address**. Digicon heads: C4 Brick+Plane, C13 Barn, C12 East End 34, C2 East End west 24, C1 Princess west, C11 Princess east + balloon. v84 sequential C1–C13 IDs live in **Legacy Node ID** and `imported/`.

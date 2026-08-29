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

**Enclosure = radio Address.** Two-head masts are two 3-pin discs (T+B) on the **same DNOU8** so that board can sit next to the mast. Neighbor dwarf uses the leftover 2 pins; the 3rd dwarf pin spills to the adjacent cluster when a plant needs 9 pins (8-channel board). Packed MQTT unchanged (Plane/Brick stay `4xx` on **C3**). Princess **C1** (never **D5**). East End signals **C2**; turnouts **C12**. Barn **C13**. Overflow **C11**.

## Digicon heads and OU boards

Pin-level source: [`cats/data/signal_wiring.csv`](../../cats/data/signal_wiring.csv). G/Y/R is lamp color of one 3-pin `STOP/APPROACH/CLEAR` object. **T** = top disc, **B** = bottom, blank = single dwarf. Packed IDs did not change; only ports did.

### C3 — Plane / Brick (radio 3, packed `4xx`)

Place **OU2** at Plane, **OU3** at Brick east (2L, next to Plane), **OU4** at Brick west (4RA/4RB). 6LA R is the one-pin spill from Plane onto the 2L board.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 12V | Switch 103–106 motors |
| OU2 | 5V | 6LB T+B, 6LA G/Y |
| OU3 | 5V | 2L T+B, 6LA R; OU3-8 leftover S3-11 R (move C3 relay here from OU2-8) |
| **OU4** | 5V **new** | 4RA, 4RB; OU4-7/8 spare |

| Mast | Disc | Packed | G | Y | R |
|------|------|--------|---|---|---|
| 6LB | T | `IH432` | OU2-1 | OU2-2 | OU2-3 |
| 6LB | B | `IH433` | OU2-4 | OU2-5 | OU2-6 |
| 6LA | | `IH434` | OU2-7 | OU2-8 | OU3-7 |
| 2L | T | `IH438` | OU3-1 | OU3-2 | OU3-3 |
| 2L | B | `IH439` | OU3-4 | OU3-5 | OU3-6 |
| 4RA | | `IH436` | OU4-1 | OU4-2 | OU4-3 |
| 4RB | | `IH437` | OU4-4 | OU4-5 | OU4-6 |

`IH435` (old 6LA Bottom) stays an unused packed hole.

### C13 — Barn (radio 13)

Place **OU1** with 8RA (left), **OU4** with 8RB (left), **OU2** with 8LA+8LB (right). 8LB R spills to the 8RB board.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 5V | 8RA T+B; OU1-7/8 leftover S3-14 G/R |
| OU2 | 5V | 8LA T+B, 8LB G/Y |
| OU3 | 12V | Switch 117–119 motors; OU3-7/8 spare |
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

### C2 — East End signals (radio 2)

Place **OU1+OU2** at 24 (SW111), **OU3+OU4** at 34 (SW112). 32R leftover sits on the 34 boards. **OU2-8 relay**.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 5V | 24RA T+B, 24RB G/Y |
| OU2 | 5V | 24L T+B, 24RB R; **OU2-8 relay** |
| OU3 | 5V | 34L T+B, 32R G/Y |
| **OU4** | 5V **new** | 34R T+B, 32R R; OU4-8 spare |

| Mast | Disc | Packed | G | Y | R |
|------|------|--------|---|---|---|
| 24RA | T | `IH232` | OU1-1 | OU1-2 | OU1-3 |
| 24RA | B | `IH238` | OU1-4 | OU1-5 | OU1-6 |
| 24RB | | `IH234` | OU1-7 | OU1-8 | OU2-7 |
| 24L | T | `IH233` | OU2-1 | OU2-2 | OU2-3 |
| 24L | B | `IH239` | OU2-4 | OU2-5 | OU2-6 |
| 34L | T | `IH235` | OU3-1 | OU3-2 | OU3-3 |
| 34L | B | `IH240` | OU3-4 | OU3-5 | OU3-6 |
| 32R | | `IH236` | OU3-7 | OU3-8 | OU4-7 |
| 34R | T | `IH237` | OU4-1 | OU4-2 | OU4-3 |
| 34R | B | `IH241` | OU4-4 | OU4-5 | OU4-6 |

East End turnout motors stay on **C12** (radio 12), not C2.

### C1 — Princess interlocking (radio 1)

Place **OU2** at SW35 (36RA), **OU3** at SW39 (40L), **OU4** at SW37 (38L). 40LA R and 38LA R spill onto the 36RA board. 36RB stays on C11.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 12V | Switch 113–115 motors; OU1-7/8 reserved |
| OU2 | 5V | 36RA T+B, 40LA R, 38LA R |
| OU3 | 5V | 40LB T+B, 40LA G/Y |
| **OU4** | 5V **new** | 38LB T+B, 38LA G/Y |

| Mast | Disc | Packed | G | Y | R |
|------|------|--------|---|---|---|
| 36RA | T | `IH135` | OU2-1 | OU2-2 | OU2-3 |
| 36RA | B | `IH136` | OU2-4 | OU2-5 | OU2-6 |
| 40LB | T | `IH132` | OU3-1 | OU3-2 | OU3-3 |
| 40LB | B | `IH133` | OU3-4 | OU3-5 | OU3-6 |
| 40LA | | `IH142` | OU3-7 | OU3-8 | OU2-7 |
| 38LB | T | `IH139` | OU4-1 | OU4-2 | OU4-3 |
| 38LB | B | `IH140` | OU4-4 | OU4-5 | OU4-6 |
| 38LA | | `IH143` | OU4-7 | OU4-8 | OU2-8 |

### C11 — Princess overflow (radio 11)

No new board. Place **OU2** near Princess (36RB T+B); **OU3** at the balloon (2036 + 2035).

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 12V | Helix turnout motors; OU1-7/8 spare |
| OU2 | 5V | 36RB T+B; OU2-7 spare; **OU2-8 relay** |
| OU3 | 5V | 2036, 2035; OU3-7/8 spare |

| Mast | Disc | Packed | G | Y | R |
|------|------|--------|---|---|---|
| 36RB | T | `IH1132` | OU2-1 | OU2-2 | OU2-3 |
| 36RB | B | `IH1135` | OU2-4 | OU2-5 | OU2-6 |
| 2036 | | `IH1133` | OU3-1 | OU3-2 | OU3-3 |
| 2035 | | `IH1134` | OU3-4 | OU3-5 | OU3-6 |

`signals_split_v8.xlsx` stays the frozen RGB plan.

### Other cabinets (no Digicon 3-pin heads)

These OUs stay motors / planned RGB (`S*-*`) / relays. Do not overlay Digicon searchlights here. **D5** is helix DCC (no DNOU8).

| Node | Radio | Plant | Boards |
|------|------:|-------|--------|
| C4 | 4 | Peninsula lower | OU1 12V motors 100–102, 116; OU2/OU3 5V S3-1/2/3/13 + relay |
| C12 | 12 | East End turnouts | OU1 12V 107–110; OU4 12V 111–112; OU2/OU3 5V S2-* + relay |
| C14 | 14 | West upper | OU1 12V 10044–10047; OU2/OU3 5V S6-* + relay |
| C21 | 21 | Helix upper | OU1 12V NIX; OU2/OU3 5V S4-* + relay |
| C22 | 22 | North upper | OU1 12V DJE/DJW; OU2/OU3 5V S5-1…5 + relay |
| C23 | 23 | West upper | OU1 12V 10043 / CBX; OU2/OU3 5V S6-* + relay |
| C24 | 24 | Peninsula upper | OU1 12V 10048–10050 + S6-10 G/R; OU2/OU3 5V S6-* + relay |
| C32 | 32 | North upper | OU1 12V 1124; OU2 5V S5-6/7 |

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
- **Node ID = radio Address** (`C2` is radio 2 / East End signals; old C2 tape is **C12**). v84 sequential C1–C13 IDs live in **Legacy Node ID** and `imported/`.

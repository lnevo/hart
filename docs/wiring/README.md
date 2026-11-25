# HART LCOS wiring documentation

The LCOS wiring documentation, refreshed against current public names and Digicon searchlight heads. This folder is the only copy: the old `~/Desktop/HART/Wiring Documentation` bench copy was retired on 2026-11-09 (ADR-007). Root `.gitignore` still ignores a repo-root `Wiring Documentation/` folder so an old checkout is not committed by accident.

## Current files

| File | Role |
|------|------|
| [`LCOS_Layout_Inventory_v86.xlsx`](LCOS_Layout_Inventory_v86.xlsx) | Current inventory of every level, a view written by `tools/wiring/write_inventory.py` (nobody edits it). Staging is what JMRI has wired, from `jmri/layouts/hart/data/wiring.csv` (the physical wiring source, owner 2026-11-20); main and upper are the draft `tools/schematic/build_device_map.py` gives them, shaded light blue on the Nodes, DNOU8, DNIN8, TurnoutSummary and BlockSensors sheets. **Node ID = C{radio Address}**; **Legacy Node ID** is a staging node's old sequential label. On **TurnoutSummary** a staging crossover (Switches 7, 23 and 35: one turnout, two OS blocks) has one row per half, labelled `Switch 7 (OS Switch 7)` and `Switch 7 (OS Switch 7b)`, each with its own entry and exit signal slots (a mast goes to the half it faces into, its `protects` column); both rows repeat the turnout's feedback and button and carry the turnout's own name in the **JMRI Turnout** column, which the site viewer and the slide deck group the halves by (owner, 2026-11-21). Every other switch has one row. The **DigiconSignals** sheet is `wiring.csv`'s wired heads, one row per lamp pin. |
| [`LCOS_Layout_Inventory_v85.xlsx`](../../archive/docs/wiring/LCOS_Layout_Inventory_v85.xlsx) | History, frozen: the staging inventory as the old refresh wrote it from the v84 import, with the old signal plan's ports. Archived 2026-11-25 with the signal split, its only reader. Its generator is in `archive/tools-wiring/`. |
| [`Wiring_Schematic.pptx`](Wiring_Schematic.pptx) | One slide per client node, regenerated from v86 (2026-11-21) by `create_wiring_schematic_ppt.py`. |
| [`Layout Documentation.pptx`](Layout%20Documentation.pptx) | History, superseded: the hand-drawn track bus, power district, bus wiring and node slides. Kept in place (owner, 2026-11-22). `www/behind/layout-docs.html` replaces it: it began as the SOQ's text and drawings and is now maintained on its own (`www/scripts/build_layout_docs.py`). |
| [`terminal_blocks.md`](terminal_blocks.md) | Terminal block wiring recovered from an October 2025 draft. Not verified against the railroad. |
| [`signals_asbuilt_abs_v2.xlsx`](signals_asbuilt_abs_v2.xlsx) | History, frozen: the lower-deck Digicon ABS matrix of the old signal plan (100L, 117LA, 114LA, …). |
| [`signals_split_v8.xlsx`](../../archive/docs/wiring/signals_split_v8.xlsx) | Archived 2026-11-25 (owner: the signals and their rules are generated for the whole layout), with the last `signal-splits.json`. Frozen Nov 2025 **planned RGB** matrix. Lower-deck switch columns use CTC names. Upper-deck plants are Switch 61+ / heads 62L…. Historical `S4-1` IDs are in Notes. |
| [`archive/docs/wiring-imported/`](../../archive/docs/wiring-imported/) | Unmodified Desktop snapshots (v84, asbuilt v1, split v8, v84 changelog), moved to the archive on 2026-11-20. Sequential C1–C13 IDs. |

LCOS Signal Manager punch list (ports + Main/Diverged + OR): [`docs/wiring/lcos/lcos_signal_manager_config_plan.xlsx`](../../docs/wiring/lcos/lcos_signal_manager_config_plan.xlsx). Source table: [`docs/wiring/lcos/lcos_signal_logic.csv`](../../docs/wiring/lcos/lcos_signal_logic.csv).

Source of truth for Digicon ports: the head rows of [`jmri/layouts/hart/data/wiring.csv`](../../jmri/layouts/hart/data/wiring.csv) (`signal_wiring.csv` is folded into it, 2026-11-21). Public block names: [`occupancy_bindings.csv`](../../cats/data/occupancy_bindings.csv) / [ADR-005](../../wiki/decisions/ADR-005-public-equipment-names.md).

**Enclosure = radio Address.** Cabinets sit with their plants: **C4** Brick+Plane, **C13** Barn, **C12** East End 34, **C2** East End west 24, **C1** Princess west (36+38), **C11** Princess east (40) + balloon. **C3** is Switch 15–21 motors only (no Digicon heads). Packed MQTT = radio. Never **D5**.

**Calibration relay:** every node that has occupancy detectors has a relay that resets the DCC power so the detectors calibrate, on **pin 8 of its first 5V DNOU8** by the rule (owner, 2026-11-21). Staging's are `calibration` rows of `jmri/layouts/hart/data/wiring.csv`; main and upper's follow the rule. First 5V board is the lowest-numbered OU on the 5V rail (OU1 when that board is 5V; otherwise OU2).

## Digicon heads and OU boards

Pin-level source: the head rows of [`jmri/layouts/hart/data/wiring.csv`](../../jmri/layouts/hart/data/wiring.csv), one row per disc (node, LCOS signal, board, its three ports). Each disc is one 3-pin `STOP/APPROACH/CLEAR` object wired **R then Y then G** on consecutive increasing LCOS ports (Port A Stop, B Approach, C Clear). **T** = top, **B** = bottom, blank = dwarf. Each 2-head mast uses 6 consecutive pins on one DNOU8 so that board can sit next to the mast. A neighboring dwarf uses the leftover 2; the 3rd pin spills to the adjacent cluster when the plant needs 9.

New 5V **OU4** on C1 / C4 / C13 only.

### C4 — Brick + Plane (radio 4, packed `4xx`)

OU1 stays 12V motors Switch 1 / 3 / 5 / 13 (this box is already at the plant). Place **OU2** at Plane, **OU3** at Brick east (2L), **OU4** at Brick west (4RA/4RB).

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 12V | Switch 1, 3, 5, 13 motors |
| OU2 | 5V | 6LB T+B, 6LA R (Stop); **OU2-8 block-sensor cal** |
| OU3 | 5V | 2L T+B, 6LA Y/G |
| **OU4** | 5V **new** | 4RA, 4RB; OU4-7/8 spare |

| Mast | Disc | Packed | R (Stop) | Y (Approach) | G (Clear) |
|------|------|--------|----------|--------------|-----------|
| 6LB | T | `IH432` | OU2-1 | OU2-2 | OU2-3 |
| 6LB | B | `IH433` | OU2-4 | OU2-5 | OU2-6 |
| 6LA | | `IH434` | OU2-7 | OU3-8 | OU3-7 |
| 2L | T | `IH438` | OU3-1 | OU3-2 | OU3-3 |
| 2L | B | `IH439` | OU3-4 | OU3-5 | OU3-6 |
| 4RA | | `IH436` | OU4-1 | OU4-2 | OU4-3 |
| 4RB | | `IH437` | OU4-4 | OU4-5 | OU4-6 |

`IH435` stays an unused packed hole.

### C13 — Barn (radio 13)

Place **OU1** with 8RA (left), **OU4** with 8RB (left), **OU3** with 8LA+8LB (right). **OU2** is 12V motors for Switch 7 / 11 / 9 (TWOSENSOR FB on IN1). 8LB Clear (G) spills to the 8RB board.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 5V | 8RA T+B; OU1-7 spare; **OU1-8 block-sensor cal** |
| OU2 | 12V | Switch 7, 11, 9 motors; OU2-7/8 spare |
| OU3 | 5V | 8LA T+B, 8LB R/Y |
| **OU4** | 5V **new** | 8RB T+B, 8LB G; OU4-8 spare |

| Mast | Disc | Packed | R (Stop) | Y (Approach) | G (Clear) |
|------|------|--------|----------|--------------|-----------|
| 8RA | T | `IH1332` | OU1-1 | OU1-2 | OU1-3 |
| 8RA | B | `IH1333` | OU1-4 | OU1-5 | OU1-6 |
| 8RB | T | `IH1335` | OU4-1 | OU4-2 | OU4-3 |
| 8RB | B | `IH1336` | OU4-4 | OU4-5 | OU4-6 |
| 8LA | T | `IH1337` | OU3-1 | OU3-2 | OU3-3 |
| 8LA | B | `IH1338` | OU3-4 | OU3-5 | OU3-6 |
| 8LB | | `IH1334` | OU3-7 | OU3-8 | OU4-7 |

### C12 — East End 34 (radio 12, packed `12xx`)

Same box as Switch 25–33. Place **OU2+OU3** at 34. 32R leftover sits on these boards.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 12V | Switch 25, 27, 29, 31 motors |
| OU2 | 5V | 34L T+B, 32R R (Stop); **OU2-8 block-sensor cal** |
| OU3 | 5V | 34R T+B, 32R Y/G |
| OU4 | 12V | Switch 23, 33 motors |

| Mast | Disc | Packed | R (Stop) | Y (Approach) | G (Clear) |
|------|------|--------|----------|--------------|-----------|
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
| OU3 | 5V | spare 1–5; **24RB R/Y/G on 6–8** |

| Mast | Disc | Packed | R (Stop) | Y (Approach) | G (Clear) |
|------|------|--------|----------|--------------|-----------|
| 24RA | T | `IH232` | OU1-1 | OU1-2 | OU1-3 |
| 24RA | B | `IH238` | OU1-4 | OU1-5 | OU1-6 |
| 24RB | | `IH234` | OU3-6 | OU3-7 | OU3-8 |
| 24L | T | `IH233` | OU2-1 | OU2-2 | OU2-3 |
| 24L | B | `IH239` | OU2-4 | OU2-5 | OU2-6 |

### C1 — Princess west (radio 1, packed `1xx`)

Place **OU2+OU3** at Switch 35 (36RA / 36RB), **OU4** at Switch 37 (38LA). 38LB uses the leftover trio on the 36 boards (OU3-7/8 + OU2-7) so R/Y are not on OU4.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 12V | Switch 35, 37, 39 motors; OU1-7/8 reserved |
| OU2 | 5V | 36RA T+B, 38LB G (Clear); **OU2-8 block-sensor cal** |
| OU3 | 5V | 36RB T+B, 38LB R/Y |
| **OU4** | 5V **new** | 38LA T+B; OU4-7/8 spare |

| Mast | Disc | Packed | R (Stop) | Y (Approach) | G (Clear) |
|------|------|--------|----------|--------------|-----------|
| 36RA | T | `IH135` | OU2-1 | OU2-2 | OU2-3 |
| 36RA | B | `IH136` | OU2-4 | OU2-5 | OU2-6 |
| 36RB | T | `IH132` | OU3-1 | OU3-2 | OU3-3 |
| 36RB | B | `IH133` | OU3-4 | OU3-5 | OU3-6 |
| 38LA | T | `IH139` | OU4-1 | OU4-2 | OU4-3 |
| 38LA | B | `IH140` | OU4-4 | OU4-5 | OU4-6 |
| 38LB | | `IH143` | OU3-7 | OU3-8 | OU2-7 |

### C11 — Princess east + balloon (radio 11, packed `11xx`)

Place **OU2** at Switch 39 (40LA), **OU3** at 40LB + balloon. 2035/2036 are separate dwarfs; 2035 takes the leftover trio.

| Board | Rail | Assignment |
|-------|------|------------|
| OU1 | 12V | Switch 67 / 63 / 65 motors (was SW129 / SW127 / SW138); OU1-7/8 spare |
| OU2 | 5V | 40LA T+B, 2035 G (Clear); **OU2-8 block-sensor cal** |
| OU3 | 5V | 40LB, 2036, 2035 R/Y |

| Mast | Disc | Packed | R (Stop) | Y (Approach) | G (Clear) |
|------|------|--------|----------|--------------|-----------|
| 40LA | T | `IH1132` | OU2-1 | OU2-2 | OU2-3 |
| 40LA | B | `IH1135` | OU2-4 | OU2-5 | OU2-6 |
| 40LB | | `IH1136` | OU3-1 | OU3-2 | OU3-3 |
| 2036 | | `IH1133` | OU3-4 | OU3-5 | OU3-6 |
| 2035 | | `IH1134` | OU3-7 | OU3-8 | OU2-7 |

`signals_split_v8.xlsx` is archived (2026-11-25); the signals come from the generated mast plan and signal rule.

### LCOS Signal Manager (Unheld)

Each disc is one object. Stock sentence:

```text
CLEAR if aligned MAIN|DIVERGED  or  set aspect STOP|APPROACH
```

Occupied blocks still force **STOP**. Packed MQTT IDs are unchanged; this is wiring/config only (`tables.xml` not patched).

| Mast | Head | Aligned | OR | Plant |
|------|------|---------|----|-------|
| 6LB | T | Main | Stop | Switch 5 |
| 6LB | B | Diverged | Stop | Switch 5 |
| 6LA | | Diverged | Stop | Switch 5 Scale dwarf |
| 2L | T | Main | Stop | Switch 1 |
| 2L | B | Diverged | Stop | Switch 1 |
| 4RA | | Main | Stop | Switch 3 W-1 |
| 4RB | | Diverged | Stop | Switch 3 W-2 |
| 8RA | T | Main | Stop | Switch 7 |
| 8RA | B | Diverged | Stop | Switch 7 |
| 8RB | T | Main | Stop | Switch 7 |
| 8RB | B | Diverged | Stop | Switch 7 |
| 8LA | T | Main | Stop | Switch 7 |
| 8LA | B | Diverged | Stop | Switch 7 |
| 8LB | | Diverged | Stop | Switch 7 Barn dwarf |
| 24RA | T | Main | Stop | Switch 23 |
| 24RA | B | Diverged | Stop | Switch 23 |
| 24L | T | Main | Stop | Switch 23 |
| 24L | B | Diverged | Stop | Switch 23 |
| 24RB | | Diverged | Stop | Switch 23 S-R |
| 32R | | Diverged | Stop | Switch 31 ladder |
| 34L | T | Main | Stop | Switch 33 |
| 34L | B | Diverged | Stop | Switch 33 |
| 34R | T | Main | Stop | Switch 33 |
| 34R | B | Diverged | Stop | Switch 33 |
| 36RA | T | Main | Stop | Switch 35 |
| 36RA | B | Diverged | Stop | Switch 35 |
| 36RB | T | Main | Stop | Switch 35 |
| 36RB | B | Diverged | Stop | Switch 35 |
| 38LA | T | Main | Stop | Switch 37 |
| 38LA | B | Diverged | Stop | Switch 37 |
| 38LB | | Diverged | Stop | Switch 37 McKeesport |
| 40LA | T | Main | Stop | Switch 39 |
| 40LA | B | Diverged | Stop | Switch 39 |
| 40LB | | Diverged | Stop | Switch 39 McKees Rocks |
| 2035 | | — | Approach | K-1 balloon |
| 2036 | | — | Approach | K-2 balloon |

Two-head **B** is the unused-head marker (red on a lined main). Do not OR Approach on a home or dwarf — that paints yellow when the turnout is against the signal.

Calibration relays (the relay on each node with detectors that resets the DCC power so the detectors calibrate): staging's are the `calibration` rows of [`jmri/layouts/hart/data/wiring.csv`](../../jmri/layouts/hart/data/wiring.csv); main and upper's are pin 8 of each detector node's first 5V board, by the device map's rule.

### Main and upper nodes

The nodes, boards and pins of the main and upper levels are the device map's draft (`tools/schematic/build_device_map.py`, the shaded rows of v86), from the node list in `jmri/layouts/hart/data/schematic/lcos_nodes.csv`. A control point's wiring becomes static once it is wired and frozen (`make wiring-freeze CP="CP 123"`). The August 2026 upper-deck plan (Switches 61 to 91 on C14, C21 to C24 and C32) is gone; it is in v85, frozen history.

## Refresh

```bash
make panels    # runs build_device_map.py (device-map step): the device master's wiring cells, staging's from wiring.csv
python3 tools/wiring/write_inventory.py        # v86 (tools/check.sh fails while it is stale)
python3 www/scripts/build_wiring_json.py       # the website's wiring viewer
# needs python-pptx:
python3 tools/wiring/create_wiring_schematic_ppt.py
```

A wiring change is a row of `jmri/layouts/hart/data/wiring.csv` (`hartlib.wiring`): a staging device moved or added, or a main or upper device once it is wired. When a main or upper control point is wired as the device map has it, freeze it: `make wiring-freeze CP="CP 123"` (`tools/wiring/freeze_wiring.py`) copies its turnouts, feedback, heads and detectors into `wiring.csv` as wired rows, and `build_device_map.py` keeps those values from then on. A control point with a head the board rule could not place cannot be frozen until that head has a place. Refresh only after the JMRI XML is applied, so the workbooks match the live beans. For Signal Manager punching, use `docs/wiring/lcos/lcos_signal_manager_config_plan.xlsx`.

The website's node grid (`www/assets/behind/lcos-node-grid.svg`, on `www/behind/bridge.html`) is drawn from the owner's grid workbook (`media/hart-research/wiring-drafts/lcos-node-grid-2025-10-06c.xlsx`, local media, not in git). Rerun it after the grid changes:

```bash
python3 tools/wiring/node_grid_svg.py
```

## History: what v85 changed vs Desktop v84 (frozen)

v85 and its refresh from the v84 import are history since 2026-11-20: v86 is written from `wiring.csv`, and the v84 snapshots and the refresh code are in `archive/docs/wiring-imported/` and `archive/tools-wiring/`.


- Lower-deck **BlockSensors** names follow the panel: Scale, Barn, S-1…S-5, W-1/W-2, EH-1…EH-3, OS 100… (MQTT `Block n-n` stays in Notes).
- **DNOU8** ports listed in `signal_wiring.csv` are overlayed as searchlight heads (replacing planned RGB on those ports). Previous RGB label is kept in Notes.
- **D1-OU2/OU3** Princess rows were a mistaken overlay (D1 is DCC radio 5, now labeled **D5**). Princess is on C1; do not recreate D5 signal boards.
- Upper-deck RGB is labeled as defined heads on CP4 / CP5 / CP6 using CTC numbers from 62 up (`64R`, `70RB`, …). 66RA+66RB share Switch 65; 70RB is Switch 69 reverse; 74RB is Switch 73 reverse.
- **Node ID = radio Address**. Digicon heads: C4 Brick+Plane, C13 Barn, C12 East End 34, C2 East End west 24, C1 Princess west, C11 Princess east + balloon. v84 sequential C1–C13 IDs live in **Legacy Node ID** and `archive/docs/wiring-imported/`.

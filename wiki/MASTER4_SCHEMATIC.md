# HART Digicon schematic — plant map

Source: `cats/panels/HART_Master4.xml` (Designer save, 63×16, 1920×540).  
Wire: `python3 cats/scripts/wire_hart_master4.py` → `HART_Master4_wired.xml`.  
`--live` copies that onto CATS CTC / CATS ABS. **This is the live Digicon.**

The Designer save is authority for rails, labels, lamps, SWITCHPOINTS, and **occupancy-cut locations**. Recent geometry edits were saved into `HART_Master4_wired.xml`; copy that back to `HART_Master4.xml` before a wire pass. The wire script names those existing `BLOCK` edges, binds turnout IO, and names lamps. Track labels (`FONT_LABEL`) on Y≥5 are lifted `LOWCENT` → `UPCENT`. It does not move lamps, insert rails, or add/remove gaps.

**SHARED wraps (N/X + occupancy):** `(1,6)` LEFT ↔ `(1,8)` LEFT both **OS Main West**; `(63,6)` RIGHT ↔ `(63,7)` RIGHT both **OS McKeesport**.

## Rows (west → east)

| CATS Y | Role |
|--------|------|
| 1 | Title |
| 5 | CP names; OS K-1 east of 115 |
| **6** | **OS Main West** → OS 23a → OS West Main Ext → OS 35b → OS 39 → OS McKees Rocks |
| **7** | OS Scale → OS 7 → OS Barn → OS 13 → OS 15 → OS S-R → OS 23b → OS 31 → OS 33 → OS East Lead → OS 35a → OS 37 → OS McKeesport |
| **8** | Brick 100 / Plane 102 / E Main Ext / OS 7b / OS EH-1 / OS S-1 / OS K-2 |
| 9 | OS W-2 / OS EH-2 / OS S-2 |
| 10 | OS W-1 / OS EH-3 / OS S-3 |
| 11–12 | OS S-4; **OS Main East** under the south-yard ladders |

West rims: `(1,6)` LEFT SHARED to `(1,8)` LEFT (OS Main West). East rims: `(63,6)` RIGHT SHARED to `(63,7)` RIGHT (OS McKeesport). OS W-1/OS W-2 east bumpers at x=9.

## Plants (`wire_hart_master4.py`)

23 frogs. Invert vs JMRI only **100 / 114 / 115**. **112 is not inverted** on this board (Closed LEFT = 110; Thrown BOTTOM = OS Main East).

| Cell | Identity | Notes |
|------|----------|--------|
| (4,8) H+LB | **100** Brick | NORMAL=RIGHT (Thrown = through E Main Ext). Closed BOTTOM = yard. Invert |
| (5,9) H+LB | **101** West Yard | NORMAL=BOTTOM (Closed = OS W-1). Thrown RIGHT = OS W-2 |
| (9,8) H+US | **102** Plane | NORMAL=RIGHT (Closed = E Main Ext). Thrown TOP = OS Scale |
| (15,8) / (15,7) | **117b / 117** | Crossover |
| (24,8) H+LS | **119** | Closed LEFT = OS EH-1. Thrown BOTTOM = OS EH-2 |
| (26,8) H+LS | **118** | Closed LEFT = from 119. Thrown BOTTOM = OS EH-3 |
| (27,7) H+LS | **116** | Thrown BOTTOM is a stub. Occupancy cut `(27,7)` BOTTOM OS 13 \| `(27,8)` TOP OS 11 — no jump |
| (30,7) H+LB | **103** | Thrown BOTTOM geographic into 104 approach `(30,8)` |
| (31,8) / (32,9) / (33,10) | **104 / 105 / 106** | Staggered H+LB; NORMAL=BOTTOM |
| (41,8) / (40,9) / (39,10) | **109 / 108 / 107** | Staggered H+LS; NORMAL=BOTTOM |
| (40,6) / (40,7) | **111a / 111b** | Crossover OS Main West / OS S-R |
| (42,7) H+LS | **110** | Closed LEFT = OS S-R/111. Thrown BOTTOM geographic into 109 `(42,8)` |
| (44,7) H+LS | **112** | Closed LEFT = 110. Thrown BOTTOM = OS Main East. **Not inverted** |
| (52,6) / (52,7) | **113b / 113a** | Crossover OS West Main Ext / OS East Lead |
| (55,6) H+US | **115** | Thrown RIGHT = OS McKees Rocks. Closed TOP = OS K-1. Invert |
| (55,7) H+LB | **114** | Thrown RIGHT = OS McKeesport. Closed BOTTOM = OS K-2. Invert |

OS Brick-Plane is Y=8 between 100 and 102 (`Block 4-6`). E Main Ext is Y=8 between 102 and 117b (`Block 4-7`).

## Signals

23 Designer lamps, named in place. **Mast 6LA** is 1-head (`LAMP1` / `IH434`). **Mast 2035** `(60,6)` RIGHT is `IH141` (was 115R). **Mast 2036** `(61,6)` LEFT is `IH134` (was 114R). **Mast 34R** is `(44,8)` LEFT on OS 33. Occupancy cut OS Main East \| OS 33 is `(43,8)` RIGHT \| `(44,8)` LEFT. **Mast 2L** is `(3,8)` LEFT. **Mast 32R** is `(42,7)` BOTTOM on OS 31 at the OS 31 \| OS 29 cut. **Mast 4RA** is OS W-1 `(6,10)` RIGHT; **Mast 4RB** is OS W-2 `(6,9)` RIGHT. **Mast 8RA** is `LAMP1` on this board; field/JMRI still 2-head. Princess westbounds match LE: **Mast 40LB** / **Mast 38LB** (`LAMP2`) on OS McKees Rocks / OS McKeesport; **Mast 40LA** / **Mast 38LA** (`LAMP1`) on OS K-1 / OS K-2.

## Remaining gaps

- USS CTC is **v76**: lever number plates back (odd SWITCH 1…39, even SIGNAL where a signal lever exists). Brick column 1 is N/R, 101 is L/N, 102 is L/N, 117 is LNR. UniqueIDs for 119/118/104–106 (`IS32/34/36/38/40`) are GUI-only — no CTC Logic columns.
- CATS Princess lamps match LE: **Mast 40LB** OS McKees Rocks and **Mast 38LB** OS McKeesport are 2-head (`LAMP2` / `double`); **Mast 40LA** OS K-1 and **Mast 38LA** OS K-2 are dwarfs (`LAMP1` / `single`). `PHYSIGNAL` is forced from `signal_wiring.csv` on wire so HOLD_ONLY `setAspect` cannot request Clear on an SL-1-low mast.
- SML re-Discovered 2026-08-27 (**33 sources / 93 dests**): **Mast 2035→Mast 40LB/Mast 38LB**, **Mast 2036→Mast 40LB/Mast 38LB**. **Mast 2035→Mast 38LB** is disabled; **Mast 2035→Mast 40LB** extra occupancy is **OS McKees Rocks** / **BS McKees Rocks**. **Mast 40LB** dests stay `Mast 24L`/`Mast 34L`; **Mast 38LB** stays `Mast 34L`. Reload **CATS CTC** or **CATS ABS**.

## Label fixes

Designer captions stay as saved. Wire lifts `FONT_LABEL` on operating rows (`Y≥5`) from `LOWCENT` to `UPCENT` so names sit above the rail. `FONT_CP` station names are unchanged.

## Live launch

```bash
./cats/scripts/launch_hart_master_ctc_hold.sh
# or the CATS CTC / CATS ABS desktop icons
python3 cats/scripts/wire_hart_master4.py --live   # after a Designer save
```

Mac icons **CATS CTC** / **CATS ABS** → live HOLD desks. **CATS Master4** (`/Applications/CATS Master4.app`) → `HART_Master4_wired.xml` for schematic testing. Do not run it with CATS CTC or USS CTC. Designer saves belong in `HART_Master4.xml` (not `_wired.xml`). The wire script `--live` copies the wired board onto `HART_Master.xml` and rebuilds both HOLD copies. Do not save Designer over `_hold.xml`.

**Load rule:** a named `BLOCK` edge must face another `BlkEdge`. Occupancy cuts use **different** names (that is the only intended rail gap). Interior cells stay plain — occupancy flows through turnouts (`PtsEdge.propagateBlock`). Same-name `BlkEdge` pairs still paint a gap; they exist only where a Designer lamp sits mid-block. A `BlkEdge` facing a plain `SecEdge` ClassCasts in `discoverAdvanceVitalLogic` and leaves the Dispatcher Panel blank. Anonymous `<BLOCK />` then NPEs (`MyBlock` is null). Do not put two names on one Track. Do not put BLOCK on the edge facing SWITCHPOINTS.

`<SHARED X="…" Y="…">EDGE</SHARED>` is the documented CATS non-adjacent joint. Both ends must point at each other. Paint stays gapped. N/X routes through. Occupancy merges when both ends share a BLOCK name (OS Main West wrap; Princess OS McKeesport wrap).

`OperationsClient` to `127.0.0.1` is CATS looking for a network ops server that HART does not run. Wired XML sets `<OPERATIONS CONNECT="false" />`. Occupancy-cut WARNs (two names at a joint) are stock CATS — it keeps the first Block.

## Viewing USS CTC (not CATS)

CATS is the Digicon. The USS lever machine is a **separate** JMRI Panel Editor panel, always titled **USS CTC**. LogixNG `IQC:AUTO:0002` **hides** that panel on CATS start.

The USS track diagram is `jmri/layouts/hart/ctc/GUIObjects.xml` (**v73**, 20 packed columns). Lever UniqueIDs and JMRI beans are still the 12-column machine / Switch 1–119; lock toggles on 119/118/104–106 are GUI-only Internal sensors. Production `jmri/layouts/hart/output/tables.xml` embeds this paneleditor.

```bash
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --preview cats/screenshots/master4/uss_ctc_v73_preview.png
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --tables jmri/layouts/hart/output/tables.xml
```

Regen also copies GIFs + `GUIObjects.xml` into local `*.jmri/ctc/` (`preference:ctc/`).

Static preview: `cats/screenshots/master4/uss_ctc_v73_preview.png`. Earlier Master 4 studies are `uss_ctc_v22`–`v72`.

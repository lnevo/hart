# HART Digicon schematic — plant map

Source: `cats/panels/HART_Master4.xml` (Designer save, 63×16, 1920×540).  
Wire: `python3 cats/scripts/wire_hart_master4.py` → `HART_Master4_wired.xml`.  
`--live` copies that onto CATS CTC / CATS ABS. **This is the live Digicon.**

The Designer save is authority for rails, labels, lamps, SWITCHPOINTS, and **occupancy-cut locations**. Recent geometry edits were saved into `HART_Master4_wired.xml`; copy that back to `HART_Master4.xml` before a wire pass. The wire script names those existing `BLOCK` edges, binds turnout IO, and names lamps. Track labels (`FONT_LABEL`) on Y≥5 are lifted `LOWCENT` → `UPCENT`. It does not move lamps, insert rails, or add/remove gaps.

**SHARED wraps (N/X + occupancy):** `(1,6)` LEFT ↔ `(1,8)` LEFT both **Track Main West**; `(63,6)` RIGHT ↔ `(63,7)` RIGHT both **Track McKeesport**.

## Rows (west → east)

| CATS Y | Role |
|--------|------|
| 1 | Title |
| 5 | CP names; Track K-1 east of Switch 39 |
| **6** | **Track Main West** → OS Switch 23a → Track West Main Ext → OS Switch 35b → OS Switch 39 → Track McKees Rocks |
| **7** | Track Scale → OS Switch 7 → Track Barn → OS Switch 13 → OS Switch 15 → Track S-R → OS Switch 23b → OS Switch 31 → OS Switch 33 → Track East Lead → OS Switch 35a → OS Switch 37 → Track McKeesport |
| **8** | Switch 1 Brick / Switch 5 Plane / Track East Main Ext / OS Switch 7b / Track EH-1 / Track S-1 / Track K-2 |
| 9 | Track W-2 / Track EH-2 / Track S-2 |
| 10 | Track W-1 / Track EH-3 / Track S-3 |
| 11–12 | Track S-4; **Track Main East** under the south-yard ladders |

West rims: `(1,6)` LEFT SHARED to `(1,8)` LEFT (Track Main West). East rims: `(63,6)` RIGHT SHARED to `(63,7)` RIGHT (Track McKeesport). Track W-1/Track W-2 east bumpers at x=9.

## Plants (`wire_hart_master4.py`)

23 frogs. Invert vs JMRI only **Switch 1 / Switch 37 / Switch 39**. **Switch 33 is not inverted** on this board (Closed LEFT = Switch 31; Thrown BOTTOM = Track Main East).

| Cell | Identity | Notes |
|------|----------|--------|
| (4,8) H+LB | **Switch 1** Brick | NORMAL=RIGHT (Thrown = through Track East Main Ext). Closed BOTTOM = yard. Invert |
| (5,9) H+LB | **Switch 3** West Yard | NORMAL=BOTTOM (Closed = Track W-1). Thrown RIGHT = Track W-2 |
| (9,8) H+US | **Switch 5** Plane | NORMAL=RIGHT (Closed = Track East Main Ext). Thrown TOP = Track Scale |
| (15,8) / (15,7) | **Switch 7b / Switch 7** | Crossover |
| (24,8) H+LS | **Switch 9** | Closed LEFT = Track EH-1. Thrown BOTTOM = Track EH-2 |
| (26,8) H+LS | **Switch 11** | Closed LEFT = from Switch 9. Thrown BOTTOM = Track EH-3 |
| (27,7) H+LS | **Switch 13** | Thrown BOTTOM is a stub. Occupancy cut `(27,7)` BOTTOM OS Switch 13 \| `(27,8)` TOP OS Switch 11 — no jump |
| (30,7) H+LB | **Switch 15** | Thrown BOTTOM geographic into Switch 17 approach `(30,8)` |
| (31,8) / (32,9) / (33,10) | **Switch 17 / Switch 19 / Switch 21** | Staggered H+LB; NORMAL=BOTTOM |
| (41,8) / (40,9) / (39,10) | **Switch 29 / Switch 27 / Switch 25** | Staggered H+LS; NORMAL=BOTTOM |
| (40,6) / (40,7) | **Switch 23a / Switch 23b** | Crossover Track Main West / Track S-R |
| (42,7) H+LS | **Switch 31** | Closed LEFT = Track S-R/Switch 23. Thrown BOTTOM geographic into Switch 29 `(42,8)` |
| (44,7) H+LS | **Switch 33** | Closed LEFT = Switch 31. Thrown BOTTOM = Track Main East. **Not inverted** |
| (52,6) / (52,7) | **Switch 35b / Switch 35a** | Crossover Track West Main Ext / Track East Lead |
| (55,6) H+US | **Switch 39** | Thrown RIGHT = Track McKees Rocks. Closed TOP = Track K-1. Invert |
| (55,7) H+LB | **Switch 37** | Thrown RIGHT = Track McKeesport. Closed BOTTOM = Track K-2. Invert |

Track Brick-Plane is Y=8 between Switch 1 and Switch 5 (`Block 4-6`). Track East Main Ext is Y=8 between Switch 5 and Switch 7b (`Block 4-7`).

## Signals

23 Designer lamps, named in place. **Mast 6LA** is 1-head (`LAMP1` / `IH434`). **Mast 2035** `(60,6)` RIGHT is `IH141` (was 115R). **Mast 2036** `(61,6)` LEFT is `IH134` (was 114R). **Mast 34R** is `(44,8)` LEFT on OS Switch 33. Occupancy cut Track Main East \| OS Switch 33 is `(43,8)` RIGHT \| `(44,8)` LEFT. **Mast 2L** is `(3,8)` LEFT. **Mast 32R** is `(42,7)` BOTTOM on OS Switch 31 at the OS Switch 31 \| OS Switch 29 cut. **Mast 4RA** is Track W-1 `(6,10)` RIGHT; **Mast 4RB** is Track W-2 `(6,9)` RIGHT. **Mast 8RA** is `LAMP1` on this board; field/JMRI still 2-head. Princess westbounds match LE: **Mast 40LB** / **Mast 38LB** (`LAMP2`) on Track McKees Rocks / Track McKeesport; **Mast 40LA** / **Mast 38LA** (`LAMP1`) on Track K-1 / Track K-2.

## Remaining gaps

- USS CTC is **v77**: every plant has an N/R switch lever. Yard ladders default Local. Brick column 1 is N/R, 101 is L/N, 102 is L/N, 117 is LNR. UniqueIDs 28–35 are the switch-only columns for 119/118/104–109.
- CATS Princess lamps match LE: **Mast 40LB** OS McKees Rocks and **Mast 38LB** OS McKeesport are 2-head (`LAMP2` / `double`); **Mast 40LA** OS K-1 and **Mast 38LA** OS K-2 are dwarfs (`LAMP1` / `single`). `PHYSIGNAL` is forced from `signal_wiring.csv` on wire so HOLD_ONLY `setAspect` cannot request a two-head aspect on a one-searchlight-low mast.
- SML re-Discovered 2026-08-27 (now **38 sources / 98 dests**): **Mast 2035→Mast 40LB/Mast 38LB**, **Mast 2036→Mast 40LB/Mast 38LB**. **Mast 2035→Mast 38LB** is disabled; **Mast 2035→Mast 40LB** extra occupancy is **OS McKees Rocks** / **BS McKees Rocks**. **Mast 40LB** dests stay `Mast 24L`/`Mast 34L`; **Mast 38LB** stays `Mast 34L`. Reload **CATS CTC** or **CATS ABS**.

## Label fixes

Designer captions stay as saved. Wire lifts `FONT_LABEL` on operating rows (`Y≥5`) from `LOWCENT` to `UPCENT` so names sit above the rail. `FONT_CP` station names are unchanged.

## Live launch

```bash
./cats/scripts/launch_hart_master_ctc_hold.sh
# or the CATS CTC / CATS ABS desktop icons
python3 cats/scripts/wire_hart_master4.py --live   # after a Designer save
```

Mac icons **CATS CTC** / **CATS ABS** → live HOLD desks. There is no **CATS Master4** Applications icon. Designer saves belong in `HART_Master4.xml` (not `_wired.xml`). The wire script `--live` copies the wired board onto `HART_Master.xml` and rebuilds both HOLD copies. Do not save Designer over `_hold.xml`.

**Load rule:** a named `BLOCK` edge must face another `BlkEdge`. Occupancy cuts use **different** names (that is the only intended rail gap). Interior cells stay plain — occupancy flows through turnouts (`PtsEdge.propagateBlock`). Same-name `BlkEdge` pairs still paint a gap; they exist only where a Designer lamp sits mid-block. A `BlkEdge` facing a plain `SecEdge` ClassCasts in `discoverAdvanceVitalLogic` and leaves the Dispatcher Panel blank. Anonymous `<BLOCK />` then NPEs (`MyBlock` is null). Do not put two names on one Track. Do not put BLOCK on the edge facing SWITCHPOINTS.

`<SHARED X="…" Y="…">EDGE</SHARED>` is the documented CATS non-adjacent joint. Both ends must point at each other. Paint stays gapped. N/X routes through. Occupancy merges when both ends share a BLOCK name (OS Main West wrap; Princess OS McKeesport wrap).

`OperationsClient` to `127.0.0.1` is CATS looking for a network ops server that HART does not run. Wired XML sets `<OPERATIONS CONNECT="false" />`. Occupancy-cut WARNs (two names at a joint) are stock CATS — it keeps the first Block.

## Viewing USS CTC (not CATS)

CATS is the Digicon. The USS lever machine is a **separate** JMRI Panel Editor panel, always titled **USS CTC**. LogixNG `IQC:AUTO:0002` **hides** that panel on CATS start.

The USS track diagram is `jmri/layouts/hart/ctc/GUIObjects.xml` (**v77**, 20 packed columns). Every plant has an N/R switch lever. Production `jmri/layouts/hart/output/tables.xml` embeds this paneleditor.

```bash
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --preview wiki/assets/uss_ctc_preview.png
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --tables jmri/layouts/hart/output/tables.xml
```

Regen also copies GIFs + `GUIObjects.xml` into local `*.jmri/ctc/` (`preference:ctc/`).

Static preview: `wiki/assets/uss_ctc_preview.png`. Earlier studies are in `media/screenshots/master4/`.

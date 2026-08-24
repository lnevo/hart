# HART Master 4 schematic — plant map

Source: `cats/panels/HART_Master4.xml` (Designer redraw, finished 2026-08-23).  
Live CTC/ABS Masters are unchanged. This board is a **test schematic**.

Master 4 draws **one straight focused main on Y=6** (Brick → 100 → 117b → Main East → 112 → East Lead → 113a → 114 → McKeesport). Main West is on **Y=8**. West yard (W-1 / W-2) sits **above** the main. South yard is two fans off 103 / 110.

**Trust lamp type + block cuts + switch geometry.** Several Designer `SEC_NAME` labels were wrong; `wire_hart_master4.py` fixes captions.

Do **not** add extra rails. Occupancy cuts use named `BLOCK` on existing cells only. 116 / 103 / 110 look like they cross Main West; they are **not** switch points. Only **110** shares a cell with Main West (diamond at `(33,8)`).

## Rows (west → east)

| CATS Y | Role |
|--------|------|
| 1 | Title |
| 4 | W-2 |
| 5 | W-1 |
| **6** | **Focused main:** Brick → OS 101 → OS 100 → Brick-Plane → OS 117b → Main East → OS 112 → East Lead → OS 113a → OS 114 → McKeesport |
| 7 | Scale / OS 117 / Barn / OS 116 / S-1 / OS 103 / OS 111b / OS 110 / K-2 |
| **8** | EH-1 + OS 119 + 116 drop; **gap** at x=21–26; Main West x=27–30; OS 111a; West Main Ext; **110 diamond (33,8)**; OS 113b; OS 115; McKees Rocks |
| 9–12 | S-2 … S-5 (west ladder x=23, east x=33) |

## 116 / 103 / 110 vs Main West

| Plant | Frog | Across Y=8 | Occupancy |
|-------|------|------------|-----------|
| **116** | `(20,7)` H+LS | Lead drops onto Y=8 **west of** Main West (x=19–20). Not a + with MW rails. | OS 116 N–S |
| **103** | `(23,7)` H+LB | `(23,8)` is **VERTICAL only** in the MW-row gap. | OS 103 N–S, **not** Main West |
| **110** | `(33,7)` H+LS | `(33,8)` is VERTICAL+HORIZONTAL **diamond**. H = West Main Ext (E–W); V = OS 110 (N–S). | No SWITCHPOINTS on the diamond |

## South yard ladders (104–109)

Designer could not separate frogs well. Each peel is its own OS with the field sensors:

| OS | Sensor | Frog | Thrown into |
|----|--------|------|-------------|
| 104 | `Block 3-3` | `(23,9)` V+UB | S-2 |
| 105 | `Block 3-5` | `(23,10)` V+UB | S-3 |
| 106 | `Block 3-7` | `(23,11)` V+UB | S-4; Closed continues to S-5 |
| 109 | `Block 12-5` | `(33,9)` V+US | S-2 |
| 108 | `Block 12-3` | `(33,10)` V+US | S-3 |
| 107 | `Block 12-1` | `(33,11)` V+US | S-4; Closed continues to S-5 |

NORMAL = BOTTOM (continue the spine). THROWN = into the body (RIGHT west / LEFT east). 106/107 Closed = S-5.

CATS will not put two occupancy names on one Track, and will not name the edge that faces SWITCHPOINTS. So each OS occupies the **first body cell** (x=24 west, x=32 east); S-2…S-5 start one cell inboard. No extra rails.

## Plants (`wire_hart_master4.py`)

21 frogs with SWITCHPOINTS + MQTT. Omitted (no frog on the drawing): **102** (`TOL42`), **118** (`TO11`). **East Main Ext** is not drawn (Main East is 117b–112).

| Cell | Identity | Notes |
|------|----------|--------|
| (5,6) H+US | **101** | NORMAL=RIGHT (Closed = through to 100) |
| (9,6) H+LB | **100** | NORMAL=BOTTOM (Closed = Scale; Thrown = Y=6 main) |
| (14,6) / (14,7) | **117b / 117** | Crossover |
| (20,7) H+LS | **116** | NORMAL=LEFT |
| (23,7) H+LB | **103** | NORMAL=RIGHT |
| (23,9–11) V+UB | **104 / 105 / 106** | Shared TOP = points |
| (31,7) / (31,8) | **111b / 111a** | Crossover |
| (33,7) H+LS | **110** | NORMAL=LEFT |
| (33,9–11) V+US | **109 / 108 / 107** | Shared TOP = points |
| (36,6) H+LS | **112** | NORMAL=BOTTOM (Closed = OS 110; Thrown = East Lead) |
| (42,6) / (43,8) | **113a / 113b** | Crossover |
| (46,6) H+LB | **114** | NORMAL=BOTTOM (Closed = K-2; Thrown = McKeesport) |
| (46,8) H+LB | **115** | NORMAL=BOTTOM (Closed = K-1; Thrown = McKees Rocks) |
| (17,8) H+LS | **119** | |

## Polarity vs JMRI (100 / 112 / 114 / 115)

These four are **Thrown when set for the mainline**. CATS `NORMAL` is the JMRI **Closed** leg so throw paints the through route. USS CTC uses `swap:` on the same four.

| Switch | Thrown (drawn through / main) | Closed (CATS NORMAL) |
|--------|-------------------------------|----------------------|
| 100 | Y=6 east → Brick-Plane | BOTTOM = Scale |
| 112 | Y=6 through = East Lead | BOTTOM = OS 110 |
| 114 | Y=6 McKeesport (114LA) | BOTTOM = K-2 (114LB) |
| 115 | Y=8 McKees Rocks (115LA) | BOTTOM = K-1 (115LB) |

Do not invert 101–103 / 110 / 116–119 to match these.

## Omitted drawing (occupancy still in the field)

| Omitted | Occupancy |
|---------|-----------|
| Hairpin 100→102 | Joined onto Y=6 as `Brick-Plane` / `Block 4-6` |
| 102 frog | No plant; `OS 102` / `TOL42` not on this board |
| 118 frog | No plant; `OS 118` / `TO11` not on this board |
| East Main Ext stretch | Not drawn; `East Main Ext` / `Block 4-7` not named |
| Balloon east of 114/115 | McKeesport / McKees Rocks continue to the east edge |

## Signals

Designer `SECSIGNAL` text is empty. `wire_hart_master4.py` binds 22 lamps by cell/edge (101RA/RB, 102LA/LB, 117*, 112*, 113*, 114*, 115*, 111*, 110R). **100L is not on this board.** `(4,6)` LEFT 2-head has no field mast — leave unbound.

## Label fixes

| Drawn | Use |
|-------|-----|
| EH-3 on Y=8, EH-1 on Y=10 | EH-1 nearest the 119 lead (Y=8), EH-3 farthest (Y=10) |
| City captions | (49,6) = McKeesport, PA; K-2 stays on Y=7 |

## Test launch

```bash
./cats/scripts/launch_hart_master4.sh
```

Mac icon **CATS Master4** → `HART_Master4_hold.xml` (HOLD_ONLY, wired copy). Does **not** replace CATS CTC / CATS ABS. Do not deploy this as the live desk until the mapping is accepted.

Designer saves belong in `HART_Master4.xml`. The launch script re-wires that file, then rebuilds the HOLD copy. Do not save Designer over `_wired.xml` / `_hold.xml`.

**Load rule:** a named `BLOCK` edge must face another `BlkEdge`. Occupancy cuts use **different** names (that is the only intended rail gap). Interior cells stay plain — occupancy flows through turnouts (`PtsEdge.propagateBlock`). Same-name `BlkEdge` pairs still paint a gap; they exist only where a Designer lamp sits mid-block. A `BlkEdge` facing a plain `SecEdge` ClassCasts in `discoverAdvanceVitalLogic` and leaves the Dispatcher Panel blank. Anonymous `<BLOCK />` then NPEs (`MyBlock` is null). Do not put two names on one Track. Do not put BLOCK on the edge facing SWITCHPOINTS.

`OperationsClient` to `127.0.0.1` is CATS looking for a network ops server that HART does not run. Wired XML sets `<OPERATIONS CONNECT="false" />`. Occupancy-cut WARNs (two names at a joint) are stock CATS — it keeps the first Block.

## Viewing the Master 4 USS CTC (not CATS)

CATS Master4 is the Digicon. The USS lever machine is a **separate** JMRI Panel Editor panel, always titled **USS CTC**. LogixNG `IQC:AUTO:0002` **hides** that panel on CATS start.

The regenerated Master 4 board is `jmri/layouts/hart/ctc/GUIObjects.xml` (also embedded in `tables/new_tables.xml` only). It is **not** what CATS/PanelPro currently load.

Static preview: `cats/screenshots/master4/uss_ctc_v23_preview.png` (v23: focused main on the top USS row, W-1/W-2 above 101, Main West gapped on the bottom row). `uss_ctc_v22_preview.png` is the earlier main-on-M draft.

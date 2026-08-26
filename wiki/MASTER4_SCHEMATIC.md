# HART Digicon schematic — plant map

Source: `cats/panels/HART_Master4.xml` (Designer save).  
Parked on branch **`human/master4`**. Live CATS CTC / CATS ABS desks are the **pre-Master 4** Masters. This map is the Master 4 schematic, not the running board.

Master 4 draws **one straight focused main on Y=6** (Brick 100 → 101 West Yard above → 102 Plane → 117b → Main East → 112 → East Lead → 113a → 114 → McKeesport). Main West is on **Y=8**. West yard (W-1 / W-2) sits **above** the main. South yard is two fans off 103 / 110.

The Designer save is authority for rails, labels, lamps, and SWITCHPOINTS. `wire_hart_master4.py` only adds occupancy/turnout IO and CATS-safe mates. It does not relocate labels, move lamps, insert rails, or strip Designer SWITCHPOINTS. `(6,5)` is Switch 101.

**Main West fold:** Y=8 is a full spine from the west edge `(1,8)` through 111. `(1,8)` LEFT is `SHARED` to Brick `(1,6)` LEFT, both named **Main West**, so the spur west of 100 is the Main West detector (`Block 2-1`). Occupancy cut at 100 is `(3,6)` Main West \| `(4,6)` OS 100 (lamp on the OS). East of 100 is OS 102 through the 102 plant. Westbound N/X from W-1 / W-2 / Scale and from West Main Ext runs MW ↔ Brick when the route is clear.

Do **not** add extra rails in the wire script. Occupancy cuts use named `BLOCK` on existing cells. Designer **staggers** the south-yard ladders (H+slash). **110 Thrown** is geographic into `(36,8)` UPPERSLASH; that LEFT SHARED-jumps to `(35,9)` TOP (109). **OS 111a** SHARED-skips `(34,8)` RIGHT ↔ `(37,8)` LEFT (`(35,8)` has no rail). **116 Thrown** does not jump onto 118. **103 Thrown** SHARED-jumps `(24,7)` BOTTOM → `(25,9)` TOP over MW into 104. No diamond / `CROSSINGEDGE` at 110.

## Rows (west → east)

| CATS Y | Role |
|--------|------|
| 1 | Title |
| 4 | W-2 |
| 5 | W-1 |
| **6** | **Focused main:** Brick → Main West spur → OS 100 → OS 102 → East Main Ext → OS 117b → Main East → OS 112 → East Lead → OS 113a → OS 114 → McKeesport (101 West Yard sits above 100) |
| 7 | Scale / OS 117 / Barn / OS 116 / S-1 / OS 103 / OS 111b / OS 110 / K-2 |
| **8** | **Main West** x=1…111L; wrap to Brick at the west edge; West Main Ext; OS 113b; OS 115; McKees Rocks |
| 9–12 | EH-1/119/118/EH-3; 116 landing `(18,9)`; staggered S-2…S-5 |

## 116 / 103 / 110 vs Main West

| Plant | Frog | Across Y=8 | Occupancy |
|-------|------|------------|-----------|
| **116** | `(21,7)` H+LS | Thrown BOTTOM does **not** jump onto 118. `(20,9)` is the 118 throat (OS 118). | OS 116 |
| **103** | `(24,7)` H+LB | Thrown BOTTOM SHARED-jumps over MW to `(25,9)` TOP (104 approach). | OS 103 \| OS 104 |
| **110** | `(36,7)` H+LS | Thrown BOTTOM is geographic into `(36,8)` UPPERSLASH (110R). That LEFT SHARED-jumps to `(35,9)` TOP (109). `(35,8)` has no rail; OS 111a SHARED-skips `(34,8)` RIGHT ↔ `(37,8)` LEFT. | Closed = S-1/111; Thrown = 109 |

110 Thrown (BOTTOM) → `(36,8)` → SHARED → `(35,9)` TOP (OS 109) → `(34,9)` 109. Occupancy cut OS 110 \| OS 109 stays (named BlkEdges on both SHARED ends). OS 111a occupancy merges through the Y=8 skip (same BLOCK name). There is no `XEdge`. Desk-confirmed diamond lock **removed 2026-08-24** at dispatcher request.

## South yard ladders (104–109)

Designer staggered H+slash frogs (same pattern as live Master / CP 104–109). Spine BOTTOM faces a plain slash cell, not the next SWITCHPOINTS, so each OS binds without inserted VERTICALs.

| OS | Sensor | Frog | Thrown into |
|----|--------|------|-------------|
| 104 | `Block 3-3` | `(26,9)` H+LB | S-2 |
| 105 | `Block 3-5` | `(27,10)` H+LB | S-3 |
| 106 | `Block 3-7` | `(28,11)` H+LB | S-4; Closed continues to S-5 |
| 109 | `Block 12-5` | `(34,9)` H+LS | S-2 |
| 108 | `Block 12-3` | `(33,10)` H+LS | S-3 |
| 107 | `Block 12-1` | `(32,11)` H+LS | S-4; Closed continues to S-5 |

NORMAL = BOTTOM (spine). THROWN = into the body (RIGHT west / LEFT east). 106/107 Closed = S-5.

Visible occupancy cuts: 103\|104, 104\|105, 105\|106\|S-5, 110\|109, 109\|108, 108\|107\|S-5, plus each peel vs S-2…S-4.

## Plants (`wire_hart_master4.py`)

23 frogs with SWITCHPOINTS + MQTT. **Brick-Plane** is the three-cell stretch between 100 and 102 (`Block 4-6`). 102–117b is East Main Ext. `(17,9)` is Switch **119**. `(19,9)` is Switch **118** (throat `(20,9)`). `(6,5)` is Switch **101**. `(10,6)` is Switch **102**.

| Cell | Identity | Notes |
|------|----------|--------|
| (5,6) H+US | **100** Brick | NORMAL=RIGHT (Thrown = through). Closed TOP = West Yard lead. Invert vs JMRI |
| (6,5) H+US | **101** West Yard | NORMAL=TOP (Closed = W-1). Thrown RIGHT = W-2. Not inverted. |
| (10,6) H+LB | **102** Plane | NORMAL=RIGHT (Closed = through to 117b). Thrown BOTTOM = Scale |
| (16,6) / (16,7) | **117b / 117** | Crossover |
| (21,7) H+LS | **116** | NORMAL=LEFT. Thrown does not join 118. |
| (24,7) H+LB | **103** | NORMAL=RIGHT |
| (26,9) / (27,10) / (28,11) | **104 / 105 / 106** | Staggered H+LB; SP LEFT |
| (34,7) / (34,8) | **111b / 111a** | Crossover |
| (36,7) H+LS | **110** | NORMAL=LEFT (Closed = S-1/111; Thrown = `(36,8)` then SHARED to 109) |
| (34,9) / (33,10) / (32,11) | **109 / 108 / 107** | Staggered H+LS; SP RIGHT |
| (39,6) H+LS | **112** | NORMAL=LEFT (Thrown = Y=6 East Lead). Closed BOTTOM = OS 110. Invert vs JMRI |
| (47,6) / (48,8) | **113a / 113b** | Crossover. Occupancy cut is mid-slash `(47,7)` RIGHT OS 113a \| `(48,7)` LEFT OS 113b (Designer gap). 113a frog BOTTOM and 113b frog TOP stay plain so occupancy flows to that cut. 113RA sits on OS 113b at `(46,8)` LEFT. |
| (55,6) H+LB | **114** | NORMAL=RIGHT (Thrown = McKeesport). Closed BOTTOM = K-2. Invert vs JMRI |
| (51,8) H+LB | **115** | NORMAL=RIGHT (Thrown = McKees Rocks). Closed BOTTOM = K-1. Invert vs JMRI |
| (17,9) H+LS | **119** | NORMAL=LEFT (Closed = EH-1). Thrown BOTTOM = EH-2 |
| (19,9) H+LS | **118** | NORMAL=LEFT (Closed = from 119). Thrown BOTTOM = EH-3. Throat `(20,9)` TOP = OS 118. |

## Polarity vs JMRI (100 / 112 / 114 / 115)

These four are **Thrown when set for the drawn through / main**. CATS `NORMAL` is that through route; Designer “differs from JMRI” puts **throw** on NORMAL (close on the other leg). USS CTC uses `swap:` on 112 / 114 / 115 (100 is Thrown-for-main on this board as well).

| Switch | Thrown (CATS NORMAL / drawn through) | Closed (other leg) |
|--------|--------------------------------------|--------------------|
| 100 | RIGHT = through Brick | TOP = West Yard lead |
| 112 | LEFT = Y=6 East Lead | BOTTOM = OS 110 |
| 114 | RIGHT = McKeesport (114LA) | BOTTOM = K-2 (114LB) |
| 115 | RIGHT = McKees Rocks (115LA) | BOTTOM = K-1 (115LB) |

101 Closed = W-1 (TOP); Thrown = W-2 (RIGHT). 102 Closed = through to 117b. Do not invert 101–103 / 110 / 116–119.

## Omitted drawing (occupancy still in the field)

| Omitted | Occupancy |
|---------|-----------|
| Brick-Plane 100→102 | Three cells on Y=6 between 100 and 102 (`Brick-Plane` / `Block 4-6`). Occupancy cuts OS 100 \| Brick-Plane \| OS 102. |
| East Main Ext stretch | Drawn as Y=6 between 102 and 117b (`East Main Ext` / `Block 4-7`). |
| Balloon east of 114/115 | Drawn as two east stubs out to x=62. CATS `SHARED` joins `(62,6)` RIGHT ↔ `(62,8)` RIGHT, both named **McKeesport**, so occupancy merges around the balloon. **114R** `(59,8)` RIGHT (westbound into McKees Rocks) and **115R** `(60,8)` LEFT (eastbound into the wrap) sit on the occupancy cut McKees Rocks \| McKeesport, west of the wrap cells. Click 115R searches through SHARED to 114LA; click 114R searches west to 115LA/115LB. |

## Signals

Designer lamps are bound where you placed them (22 named). **100L is not on this board** — `(4,6)` LEFT 2-head stays unbound. **112R** is on `(33,6)` LEFT so it stacks with **111RB** `(33,7)` and **111RA** `(33,8)`; Main East \| OS 112 is that cut. **110R** is on `(36,8)` LEFT (longer 110 diverge, `SIGLOCATION` LOWRIGHT / `SIGORIENT` TOP). It cannot sit on OS 109 — a CATS `CPEdge` there stops 109→110 N/X at the approach. **114R** is on `(59,8)` RIGHT (`UPCENT`/`LEFT`); **115R** is on `(60,8)` LEFT (`LOWCENT`/`RIGHT`) — opposing intermediates at McKees Rocks \| McKeesport, not on the wrap. **111L** is on `(38,8)` RIGHT (OS 111a, east of 111L is West Main Ext). **102LB/102LA** sit on OS 102’s east cuts. **117LA / 114LA / 115LA** sit on the OS (no frog-side gap); occupancy cuts are the lamp’s east edge. 114 moved to `(53,6)`; 114LA/114LB are on `(54,6)` / `(54,7)`.

## Label fixes

Designer captions are used as saved (EH-1 at `(14,8)`, cities UPCENT at `(53,6)` / `(53,8)`, East Lead / West Main Ext at `(41,6)` / `(41,8)`). The wire script does not relocate labels.

## Live launch

```bash
./cats/scripts/launch_hart_master_ctc_hold.sh
# or the CATS CTC / CATS ABS desktop icons
python3 cats/scripts/wire_hart_master4.py --live   # after a Designer save
```

Mac icons **CATS CTC** / **CATS ABS** → `HART_Master_CTC_hold.xml` / `HART_Master_ABS_hold.xml`. Designer saves belong in `HART_Master4.xml`. The wire script `--live` copies the wired board onto `HART_Master.xml` and rebuilds both HOLD copies. Do not save Designer over `_hold.xml`.

**Load rule:** a named `BLOCK` edge must face another `BlkEdge`. Occupancy cuts use **different** names (that is the only intended rail gap). Interior cells stay plain — occupancy flows through turnouts (`PtsEdge.propagateBlock`). Same-name `BlkEdge` pairs still paint a gap; they exist only where a Designer lamp sits mid-block. A `BlkEdge` facing a plain `SecEdge` ClassCasts in `discoverAdvanceVitalLogic` and leaves the Dispatcher Panel blank. Anonymous `<BLOCK />` then NPEs (`MyBlock` is null). Do not put two names on one Track. Do not put BLOCK on the edge facing SWITCHPOINTS.

`<SHARED X="…" Y="…">EDGE</SHARED>` is the documented CATS non-adjacent joint (`SecEdge.bind()`: if `DescribeEdge` is set, locate that Section/edge instead of the geographic neighbor). Both ends must point at each other. Paint does not draw a connecting rail. N/X routes through. Occupancy merges only when both ends use the same `BLOCK` name (Main West fold; Princess balloon McKeesport wrap; OS 111a skip `(34,8)`↔`(37,8)`). Do not put a named `BLOCK` on a SHARED end unless the mate is also a `BlkEdge`.

`OperationsClient` to `127.0.0.1` is CATS looking for a network ops server that HART does not run. Wired XML sets `<OPERATIONS CONNECT="false" />`. Occupancy-cut WARNs (two names at a joint) are stock CATS — it keeps the first Block.

## Viewing USS CTC (not CATS)

CATS is the Digicon. The USS lever machine is a **separate** JMRI Panel Editor panel, always titled **USS CTC**. LogixNG `IQC:AUTO:0002` **hides** that panel on CATS start.

The USS track diagram is `jmri/layouts/hart/ctc/GUIObjects.xml`. That `<paneleditor name="USS CTC">` is also embedded in `tables/new_tables.xml` and the deploy bundle `jmri/layouts/hart/output/tables.xml` (PanelPro loads the host `tables.xml`, not `preference:ctc/GUIObjects.xml` alone). Deploy copies both.

Static preview: `cats/screenshots/master4/uss_ctc_v28_preview.png` (v28: thin icons copied into JMRI `preference:ctc/icons/`; 100 over col 1; W-1/W-2 horizontal; plant dropped 20px; 113b east). `uss_ctc_v27_preview.png` introduced SOUTH YD stubs.

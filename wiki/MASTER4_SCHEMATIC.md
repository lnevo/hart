# HART Digicon schematic — plant map

Source: `cats/panels/HART_Master4.xml` (Designer save, 63×16, 1920×540).  
Wire: `python3 cats/scripts/wire_hart_master4.py` → `HART_Master4_wired.xml`.  
`--live` copies that onto CATS CTC / CATS ABS. **This is the live Digicon.**

The Designer save is authority for rails, labels, lamps, SWITCHPOINTS, and **occupancy-cut locations**. Recent geometry edits were saved into `HART_Master4_wired.xml`; copy that back to `HART_Master4.xml` before a wire pass. The wire script names those existing `BLOCK` edges, binds turnout IO, and names lamps. Track labels (`FONT_LABEL`) on Y≥5 are lifted `LOWCENT` → `UPCENT`. It does not move lamps, insert rails, or add/remove gaps.

**SHARED wraps (N/X + occupancy):** `(1,6)` LEFT ↔ `(1,8)` LEFT both **Main West**; `(63,6)` RIGHT ↔ `(63,7)` RIGHT both **McKeesport**.

## Rows (west → east)

| CATS Y | Role |
|--------|------|
| 1 | Title |
| 5 | CP names; K-1 east of 115 |
| **6** | **Main West** → OS 111a → West Main Ext → OS 113b → OS 115 → McKees Rocks |
| **7** | Scale → OS 117 → Barn → OS 116 → OS 103 → S-1 → OS 111b → OS 110 → OS 112 → East Lead → OS 113a → OS 114 → McKeesport |
| **8** | Brick 100 / Plane 102 / E Main Ext / OS 117b / EH-1 / S-2 / K-2 |
| 9 | W-2 / EH-2 / S-3 |
| 10 | W-1 / EH-3 / S-4 |
| 11–12 | S-5; **Main East** under the south-yard ladders |

West rims: `(1,6)` LEFT SHARED to `(1,8)` LEFT (Main West). East rims: `(63,6)` RIGHT SHARED to `(63,7)` RIGHT (McKeesport). W-1/W-2 east bumpers at x=9.

## Plants (`wire_hart_master4.py`)

23 frogs. Invert vs JMRI only **100 / 114 / 115**. **112 is not inverted** on this board (Closed LEFT = 110; Thrown BOTTOM = Main East).

| Cell | Identity | Notes |
|------|----------|--------|
| (4,8) H+LB | **100** Brick | NORMAL=RIGHT (Thrown = through E Main Ext). Closed BOTTOM = yard. Invert |
| (5,9) H+LB | **101** West Yard | NORMAL=BOTTOM (Closed = W-1). Thrown RIGHT = W-2 |
| (9,8) H+US | **102** Plane | NORMAL=RIGHT (Closed = E Main Ext). Thrown TOP = Scale |
| (15,8) / (15,7) | **117b / 117** | Crossover |
| (24,8) H+LS | **119** | Closed LEFT = EH-1. Thrown BOTTOM = EH-2 |
| (26,8) H+LS | **118** | Closed LEFT = from 119. Thrown BOTTOM = EH-3 |
| (27,7) H+LS | **116** | Thrown BOTTOM is a stub. Occupancy cut `(27,7)` BOTTOM OS 116 \| `(27,8)` TOP OS 118 — no jump |
| (30,7) H+LB | **103** | Thrown BOTTOM geographic into 104 approach `(30,8)` |
| (31,8) / (32,9) / (33,10) | **104 / 105 / 106** | Staggered H+LB; NORMAL=BOTTOM |
| (41,8) / (40,9) / (39,10) | **109 / 108 / 107** | Staggered H+LS; NORMAL=BOTTOM |
| (40,6) / (40,7) | **111a / 111b** | Crossover Main West / S-1 |
| (42,7) H+LS | **110** | Closed LEFT = S-1/111. Thrown BOTTOM geographic into 109 `(42,8)` |
| (44,7) H+LS | **112** | Closed LEFT = 110. Thrown BOTTOM = Main East. **Not inverted** |
| (52,6) / (52,7) | **113b / 113a** | Crossover West Main Ext / East Lead |
| (55,6) H+US | **115** | Thrown RIGHT = McKees Rocks. Closed TOP = K-1. Invert |
| (55,7) H+LB | **114** | Thrown RIGHT = McKeesport. Closed BOTTOM = K-2. Invert |

Brick-Plane is Y=8 between 100 and 102 (`Block 4-6`). E Main Ext is Y=8 between 102 and 117b (`Block 4-7`).

## Signals

23 Designer lamps, named in place. **102LA** is 1-head (`LAMP1` / `IH434`). **120L** `(60,6)` RIGHT is `IH141` (was 115R). **120R** `(61,6)` LEFT is `IH134` (was 114R). **112R** is `(44,8)` LEFT on OS 112. Occupancy cut Main East \| OS 112 is `(43,8)` RIGHT \| `(44,8)` LEFT. **100L** is `(3,8)` LEFT. **110R** is `(42,7)` BOTTOM on OS 110 at the OS 110 \| OS 109 cut. **101RA** is W-1 `(6,10)` RIGHT; **101RB** is W-2 `(6,9)` RIGHT. **117RA** is `LAMP1` on this board; field/JMRI still 2-head. Princess westbounds match LE: **115LB** / **114LB** (`LAMP2`) on McKees Rocks / McKeesport; **115LA** / **114LA** (`LAMP1`) on K-1 / K-2.

## Remaining gaps

- USS CTC `GUIObjects.xml` is **v69**: Brick column 1 is N/R, 101 is L/N, 102 is L/N, 117 is LNR. **120R** east on McKees Rocks and **120L** westbound on McKeesport. New UniqueIDs for 119/118/104–106 (IS32/34/36/38/40) are GUI-only. Local default still not applied. Production `output/tables.xml` embeds this paneleditor.
- **117RA** / **117LA** are `LAMP1` on Master 4 and USS (top head only); JMRI/field still 2-head.
- CATS Princess lamps match LE: **115LB** McKees Rocks and **114LB** McKeesport are 2-head (`LAMP2` / `double`); **115LA** K-1 and **114LA** K-2 are dwarfs (`LAMP1` / `single`). `PHYSIGNAL` is forced from `signal_wiring.csv` on wire so HOLD_ONLY `setAspect` cannot request Clear on an SL-1-low mast.
- **112R** CATS lamp at `(44,8)` vs existing field 2-head mast (`IH1240`/`IH1241`).
- SML re-Discovered after 120L facing west: **120L→115LB/114LB**, **120R→115LB/114LB**. **115LB** dests stay `111L`/`112L`; **114LB** stays `112L`. Reload **CATS CTC** or **CATS ABS**.
- Sheets push stays human-gated.

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

`<SHARED X="…" Y="…">EDGE</SHARED>` is the documented CATS non-adjacent joint. Both ends must point at each other. Paint stays gapped. N/X routes through. Occupancy merges when both ends share a BLOCK name (Main West wrap; Princess McKeesport wrap).

`OperationsClient` to `127.0.0.1` is CATS looking for a network ops server that HART does not run. Wired XML sets `<OPERATIONS CONNECT="false" />`. Occupancy-cut WARNs (two names at a joint) are stock CATS — it keeps the first Block.

## Viewing USS CTC (not CATS)

CATS is the Digicon. The USS lever machine is a **separate** JMRI Panel Editor panel, always titled **USS CTC**. LogixNG `IQC:AUTO:0002` **hides** that panel on CATS start.

The USS track diagram is `jmri/layouts/hart/ctc/GUIObjects.xml` (**v69**, 20 packed columns). Lever UniqueIDs and JMRI beans are still the 12-column machine / Switch 100–119; lock toggles on 119/118/104–106 are GUI-only Internal sensors. Production `jmri/layouts/hart/output/tables.xml` embeds this paneleditor.

```bash
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --preview cats/screenshots/master4/uss_ctc_v69_preview.png
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --tables jmri/layouts/hart/output/tables.xml
```

Regen also copies GIFs + `GUIObjects.xml` into local `*.jmri/ctc/` (`preference:ctc/`).

Static preview: `cats/screenshots/master4/uss_ctc_v69_preview.png`. Earlier Master 4 studies are `uss_ctc_v22`–`v68`.

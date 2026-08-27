# Live status — HART Digicon

Updated: 2026-08-26 — USS CTC **v57** cell/pts/occ icons installed into this Mac's JMRI profiles (`preference:ctc/icons/`). Reload **USS CTC**. `tables.xml` still pre-Master 4. Not deployed to Pi.

Updated: 2026-08-26 — USS CTC **v57** cleans the Master 4 diagram: one transparent 18×18 tile per CATS cell (no overlapping USS line gifs / 40px frogs). Points are small yellow dots. `tables.xml` unchanged. Preview `cats/screenshots/master4/uss_ctc_v57_preview.png`. Not deployed.

Updated: 2026-08-26 — USS CTC track diagram **v56** starts over from live CATS Master 4 (`HART_Master4.xml`): same row order (Main West / Scale-Barn-S-1 / Brick-Plane / W-1-W-2 / south yard / Main East), W-1/W-2 east of 101, EH-1/2/3, S-1…S-5, 104–109 frogs drawn. Regen `gen_ctc_track_plan.py`. `tables.xml` unchanged — PanelPro still loads the pre-Master 4 board. Preview `cats/screenshots/master4/uss_ctc_v56_preview.png`. Not deployed.

Updated: 2026-08-26 — CATS ABS Screen.init crash: **115LA** was `PHYSIGNAL double` on a 1-head dwarf, so CATS `setAspect("Clear")` aborted load. Princess LA/LB now match field heads; wire forces PHYSIGNAL from `signal_wiring.csv`. Reload **CATS ABS** or **CATS CTC**. Deploy `--all`.

Updated: 2026-08-26 — USS CTC `GUIObjects.xml` restored to the Master 4 schematic (**v55**, `human/master4` / `de8e727`). `tables.xml` unchanged — PanelPro still loads the pre-Master 4 board until that paneleditor is replaced. Not deployed.

Updated: 2026-08-26 — Post-Discover CATS ABS MQTT QA: **120R/120L** now Approach at rest (Yellow). **115LB/114LB** and dwarfs **115LA/114LA** stay Stop when lined — same pattern as CATS Hold, JSON `held` not readable on this desk. Brick/Plane/110/117 still match. Retained MQTT restored.

Updated: 2026-08-26 — Native SML re-Discovered: **93 dests**. **120L** now dests **115LB** (and 114LB via the balloon); **120R** dests **115LB** and **114LB**. **115LB/114LB** homes unchanged (`111L`/`112L`). Reload **CATS CTC** or **CATS ABS**. Deploy `--all`.

Updated: 2026-08-26 — MQTT mimic QA vs live CATS ABS: SML aspects and MQTT heads stay in lockstep. Princess **120R/120L** stay Stop (SML dests after the rename; re-Discover still due). CATS ABS Hold keeps **114LA/115LA** Stop. Retained MQTT restored.

Updated: 2026-08-26 — Public-name map synced to live for the next rename pass: `current` is live (`W-1`, `S-1…S-5`, `120R`/`120L`, hidden throats, Dispatcher virtuals). Historical aliases kept. Baselines recaptured. Docs-only.

Updated: 2026-08-26 — Digicon turnout IO lives in `cats/scripts/cats_turnout_io.py`. Master 4 no longer imports the West Yard sheet wire. Docs-only.

Updated: 2026-08-26 — USS CTC signal lamps match live CATS: **120L** west-facing (`IH141`), **117RA** / **117LA** 1-lamp dwarfs (top heads). Track schematic unchanged. Reload **USS CTC**. Do not run it with CATS CTC. Deploy `--all`.

Updated: 2026-08-26 — Master 4 is **live CATS CTC / CATS ABS**. **114R→120R** (`IH134`) and **115R→120L** (`IH141`). Unused head **IH435** removed; MQTT `track/signalhead/IH435` cleared. West Yard sheets archived. Reload **CATS CTC** or **CATS ABS**. Do not run with USS CTC. Deploy `--all`. Re-Discover SML after reload.

Updated: 2026-08-26 — **102LA** is a 1-head dwarf (`IH434` / C4-OU2-3, `SL-1-low`). Mast userName `102LA` unchanged.

Updated: 2026-08-26 — Master 4: 110R is on OS 110 BOTTOM (`(42,7)`), the 110\|109 cut. Designer cosmetics kept. Reload **CATS Master4**.

Updated: 2026-08-26 — **CATS Master4** icon in `/Applications` launches `HART_Master4_wired.xml`. Live CATS CTC/ABS unchanged. Do not run it with CATS CTC or USS CTC.

Updated: 2026-08-26 — Master 4 routing: SHARED `(1,6)`↔`(1,8)` Main West and `(63,6)`↔`(63,7)` McKeesport. Main East cut at `(43,8)|(44,8)` with CATS `112R`. Princess intermediates are **120L** `(60,6)` / **120R** `(61,6)`. Not live.

Updated: 2026-08-25 — USS CTC restored to the **pre-Master 4** board (`a99b04f`, v8 yard ladders), not the Aug 23+ Master 4 redraw. CATS desks remain pre-Master 4. EH-1/EH-3 occupancy swap kept. Reload **USS CTC**. Do not run it with CATS CTC. Deploy `--all`.

Updated: 2026-08-25 — USS CTC restored to pre-Master 4 cutover (**v54**). CATS desks remain pre-Master 4. EH-1/EH-3 occupancy swap kept. Reload **USS CTC** and **CATS CTC** or **CATS ABS**. Deploy `--all`.

Updated: 2026-08-25 — Live CATS CTC/ABS restored to **pre-Master 4**. Master 4 schematic parked on **`human/master4`**. EH-1/EH-3 occupancy swap kept (`Block 13-7` / `Block 13-5`). Reload **CATS CTC** or **CATS ABS**. Deploy `--all`.

Updated: 2026-08-25 — LCOS BlockSensors C5-B3/B4 names match the EH-1/EH-3 occupancy swap (`Block 13-5` = EH-3, `Block 13-7` = EH-1). MQTT Notes unchanged. Docs-only.

Updated: 2026-08-25 — EH-1 occupancy is `Block 13-7` / M2S1306; EH-3 is `Block 13-5` / M2S1304 (swapped). CATS CTC/ABS, sheets, and LE. Reload **CATS CTC** or **CATS ABS**. Deploy `--all`.

Updated: 2026-08-25 — USS CTC **v55**: Brick-Plane occupancy centered between 100 and 102; W-1/W-2 lamps stacked on that column. Reload **USS CTC**. Deploy `--all`.

Updated: 2026-08-25 — USS CTC Panel Editor is now the `GUIObjects.xml` board (SOUTH YD). Old `Panel ` paneleditor removed from `tables/new_tables.xml`, deploy bundle `jmri/layouts/hart/output/tables.xml`, and the Mac profile. Deploy `--all`. Reload **USS CTC** (Panels menu). Do not run it with CATS CTC.

Updated: 2026-08-25 — **Live cutover:** Master 4 schematic is CATS CTC / CATS ABS / USS CTC. CATS Master4 icon removed. Deploy `--all`. Reload **CATS CTC** or **CATS ABS** (not both with USS).

Updated: 2026-08-25 — Master 4: 112R gap moved to `(32,6)|(33,6)` to stack with 111. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-25 — Master 4: 110R alignment is LOWRIGHT (still faces TOP). Reload **CATS Master4**. Not deployed.

Updated: 2026-08-25 — Master 4: `(35,8)` rail removed; OS 111a skip is `(34,8)` RIGHT ↔ `(37,8)` LEFT. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-25 — Master 4 default window is 1920×540. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-25 — Master 4: 110 diverge is `(36,8)` with 110R; SHARED to 109. OS 111a skips that cell `(35,8)`↔`(37,8)`. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-25 — Master 4: W-1 is 101 NORMAL (TOP, not inverted); W-2 is Thrown RIGHT. Brick-Plane is three cells between 100 and 102 (`Block 4-6`). Reload **CATS Master4**. Not deployed.

Updated: 2026-08-25 — Master 4 Princess: wrap is `(62,6)`↔`(62,8)` McKeesport occupancy; 120R/120L are opposing intermediates on Y=8 at McKees Rocks \| McKeesport. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-25 — USS CTC **v54**: East Lead filled 113a→114; 110R dropped a few pixels under SOUTH YD. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — USS CTC **v53**: 114 in its column; K-1/K-2 bumpers off; W-1/W-2 shortened off East Main Ext; West Main Ext labeled. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — USS CTC **v52**: 111 crossover flipped to os-l-sc; McKees Rocks lined up with McKeesport; K-1/K-2 are short spurs with on-track labels. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — Master 4 Princess: east bumper of McKeesport is McKees Rocks occupancy (`Block 1-1`), and vice versa, so 120R/120L do not share the body to the west. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-24 — USS CTC **v51**: 115 in the 114/115 gutter; McKeesport / McKees Rocks lamps follow; K-2 on the second track; `swap:` on 100/112/114/115 like CATS. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — USS CTC **v50**: Brick-Plane lamp on the 2/3 column line; East Main Ext stacked on Scale; Main West body lamp in column 5 (west of Scale); Barn 117 crossover is `\\`. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — Master 4: MW spine to the west edge, wrap `(1,8)`↔`(1,6)` (no gap at 2,6); 116 SHARED to `(18,9)` over MW; 118 at `(17,9)`; 111RB cell is OS (no gap at 31,7 RIGHT). Reload **CATS Master4**. Not deployed.

Updated: 2026-08-24 — USS CTC **v49**: Main West west of 111 is one continuous circuit (line1 tiles overlap so they don’t leave 14px holes); East Main Ext lamp (`Block 4-7`) between 102 and 117; rail cuts only at OS frogs. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — Master 4: 119 at `(16,8)`, 118 at `(18,8)`; OS cells through 117LA / 111L / 114LA / 115LA and S-5 body (no mid-block gaps). Reload **CATS Master4**. Not deployed.

Updated: 2026-08-24 — Master 4: EH-1/EH-3 frog `(16,8)` is Switch **118**; invert-vs-JMRI only on 100/112/114/115 (101/102 Closed = through). Reload **CATS Master4**. Not deployed.

Updated: 2026-08-24 — USS CTC **v48**: OS cut after 111L (east of 111), matching Main East after 112; Main West runs from the South Yard OS lamp to the west frame. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — USS CTC **v47**: 111–West Main Ext rail filled; Brick west and Princess east stubs run to the frame; short Main West stub west of 111. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — Master 4 turnout MQTT left→right: 100 Brick `(5,6)`, 101 West Yard `(6,5)`, 102 Plane `(9,6)`, then 117…116…103…111…109…110…112…113, with 114/115 stacked. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-24 — USS CTC **v46**: East Lead occupancy stacked on West Main Ext (x=806); MAIN WEST centered under its lamp; EAST LEAD label added. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — Princess McKeesport (`Block 1-2`) and McKees Rocks (`Block 1-1`) occupancy fire independently. Balloon SHARED is N/X wrap only; occupancy does not merge. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-24 — USS CTC **v45**: Main West occupancy (`Block 2-1`) repeats at the west end of the focused main (Brick), so a westbound through 111 shows on the west side of the board. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — Master 4 Princess balloon: 120R/120L moved to LEFT of the east cells so CATS N/X walks through the SHARED wrap (eastbound McKeesport → westbound McKees Rocks, and vice versa). Reload **CATS Master4**. Not deployed.

Updated: 2026-08-24 — USS CTC **v44**: Princess McKees Rocks gets eastbound 120L (`IH141`, 1-lamp) stacked with McKeesport 120R. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — USS CTC **v43**: Princess westbounds match CATS (McKeesport, K-2, McKees Rocks, K-1): 2-lamp 114LB/115LB on the mains, 1-lamp 114LA/115LA on K-2/K-1. 114 shifted west for signal room; east occupancy at x=1072. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — Master 4 Princess balloon: McKeesport `(55,6)` RIGHT `SHARED` to McKees Rocks `(55,8)` RIGHT so 120R/120L wrap eastbound into the other stub westbound. Occupancy stays separate (Block 1-2 / 1-1). Reload **CATS Master4**. Not deployed.

Updated: 2026-08-24 — Master 4 Main West west stub is CATS `SHARED` to Brick west `(1,6)` LEFT so N/X continues around the schematic fold (occupancy cut Main West | OS 101). 110×Main West diamond stays a real `XEdge` (no SHARED skip). Reload **CATS Master4**. Not deployed.

Updated: 2026-08-24 — USS CTC **v42**: Princess McKees Rocks uses 115LB CTC 2-lamp (120L dwarf gone); K-2 gets the same 2-lamp; east occupancy lamps share x=1044. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — USS CTC **v41**: W-1/W-2 dwarfs restored and rails/labels cleared of the bumpers; 110R on the South Yd lead (extra OS 110 occupancy removed); 115LA 2-head on McKees Rocks and 115LB on K-1; MW ink lined into 111. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — USS CTC **v40**: W-1/W-2 in-track lamps on USS bars; MAIN WEST below the rails and extended so its lamp stacks with Main East / S-1; South Yd→110 lamp on the U; 111 unobstructed; Princess McKeesport / K-2 / McKees Rocks / K-1 with 2-head homes on McKeesport and McKees Rocks. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — USS CTC **v39**: W-1/W-2 use in-track occupancy (no dwarf heads); 100L west of Brick facing east; Princess labels K-1 / McKees Rocks swapped and 120L on McKees Rocks (east intermediate with McKeesport). Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — USS CTC **v38**: 101 back in the 2/3 gap on 100’s `/` (centering in col 3 read as 3/4). W-1/W-2 labels on the east end of the spurs; occupancy lamps stay at x=196. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — USS CTC **v37**: 100 over col 2, 101 over col 3, 102 over col 4; Brick–Plane occupancy lamp stacked on the same x as W-1/W-2. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — USS CTC **v36**: schematic dropped 40px below the gold header / CP names; OS lamp row dropped 84px so SOUTH YD and the lamps have air between them. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — USS CTC **v35**: Princess stub labels (McKeesport, K-2, McKees Rocks, K-1) right-aligned to the east rail (x=1105). Regen `gen_ctc_track_plan.py`. Reload **USS CTC**. Not deployed.

Updated: 2026-08-24 — Master 4 110R eastbound: lamp was on OS 109 `(33,9)` TOP facing RIGHT (wrong side of the 110|109 cut). Moved to OS 110 frog BOTTOM like live Master (`SIGORIENT` TOP). MQTT: `track/sensor/1206` (OS 110 / Block 12-7) is **ACTIVE**; 109/111a/111b/112 and Main West are INACTIVE; Switch 110 is THROWN, 109/111/112 CLOSED. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-24 — Master 4 paint crash was empty SPUR SWITCHPOINTS at `(6,5)` / `(18,8)` (CATS 3.1 `PtsVitalLogic.setPoints` AIOOB, no NORMAL). Wire pass now writes ROUTENAME NORMAL on those drawing splits (no MQTT). Reload **CATS Master4**. Not deployed.

Updated: 2026-08-24 — Master 4 rewired from Designer save 00:06. Geometry/labels/lamps/SWITCHPOINTS kept as drawn (`(6,5)` and `(18,8)` SPUR splits stay). `(33,8)`/`(34,8)` are Main West through HORIZONTAL (no diamond). **110 Thrown BOTTOM has no neighbor** — 109 is not rail-connected. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-23 — Master 4 rewired from the cleaned Designer save (23:34). Ladders are staggered H+slash (104–109 each have their own OS; no inserted spacers). 110×Main West is a crossing (occupancy H=OS 111a, slash=OS 110→109, no SWITCHPOINTS). 103 does not share a cell with Main West. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-23 — USS CTC track diagram **v28**: thin icons installed into local JMRI profiles (`preference:ctc/icons/`, including `os-n-bar-*.gif`). Brick 100 stays on the first lever column; 101 and W-1/W-2 shift west as horizontal spurs; the whole plant drops 20px so those spurs have room. 113b moves east so the two `\\` continue. Regen: `gen_ctc_track_plan.py` (copies icons into `*.jmri/ctc/icons/`). Preview `cats/screenshots/master4/uss_ctc_v28_preview.png`. Reload the USS CTC panel. Not deployed to Pi.

Updated: 2026-08-23 — USS CTC track diagram **v27**: 103 and 110 are SOUTH YD stubs (frog → horizontal → bumper + label), same grammar as Engine House / W-1. 103 stub sits in the Main West gap and stops; 110 stub is below MW after the diamond. No 104–109 frogs, no hanging slashes. Regen: `gen_ctc_track_plan.py` → `ctc/GUIObjects.xml` + `tables/new_tables.xml`. Preview `cats/screenshots/master4/uss_ctc_v27_preview.png`. Not deployed.

Updated: 2026-08-23 — USS CTC track diagram **v26**: no Scale siding between Brick and Plane (100 is main OS only; 102 is a single turnout, both routes to 117). 113a/113b stacked in the same column, both `\\`. Yard leads at 103/110 unchanged (USS-board study in progress). Regen: `gen_ctc_track_plan.py` → `ctc/GUIObjects.xml` + `tables/new_tables.xml`. Preview `cats/screenshots/master4/uss_ctc_v26_preview.png`. Not deployed.

Updated: 2026-08-23 — Master 4: OS 104–109 each get their own occupancy region (plain VERTICAL spacers between stacked ladder frogs; same pattern as live Master’s staggered H+slash plants and the CP 104–109 panels). 111L gap restored to Designer center `(37,8)` RIGHT. 110R moved up onto the 110 frog `(33,7)` BOTTOM UPCENT. McKeesport / McKees Rocks UPCENT above the track. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-23 — USS CTC track diagram **v25**: 113 is one continuous `\\` (113b thin os-r-w shifted east); first plant column is Brick/100 with 101 in the 3/4 column and 102 on the main (`\\` to Scale); Engine House is a single spur under levers 7/9; 103 drops through the Main West gap into a 104 frog (does not join MW); 110 diamond plus a 109 yard frog, no yard body. Regen: `gen_ctc_track_plan.py` → `ctc/GUIObjects.xml` + `tables/new_tables.xml`. Preview `cats/screenshots/master4/uss_ctc_v25_preview.png`. Live CTC UniqueIDs unchanged (lever 1 still codes Switch 101). Not deployed.

Updated: 2026-08-23 — Master 4: McKeesport/McKees Rocks one cell east of K-2/K-1, LOWCET. 102LB/LA cells are OS 100 (gap only on the right, vs Brick-Plane / Scale). West Main Ext caption centered at (38,8). Reload **CATS Master4**. Not deployed.

Updated: 2026-08-23 — USS CTC track diagram **v23** matches Master 4 row order: focused main on the top operating row, W-1/W-2 above 101, Scale/Barn/S-1/K-2 in the middle, Main West gapped on the bottom. Regen: `gen_ctc_track_plan.py` → `ctc/GUIObjects.xml` + `tables/new_tables.xml` only. Preview `cats/screenshots/master4/uss_ctc_v23_preview.png`. Not deployed (not the live PanelPro board).

Updated: 2026-08-23 — Master 4 had a rail gap at almost every cell because Designer `BLOCK`s plus the wire script’s heal pass named both sides of every frog. CATS paints a gap at every `BlkEdge`. Occupancy now named only at block boundaries (plus unavoidable mid-block lamp joints). Reload **CATS Master4**. Not deployed.

Updated: 2026-08-23 — Master 4 paint crash was 112R / 111L on unnamed BLOCK edges (SecEdge ClassCast in discoverAdvanceVitalLogic). Wired occupancy now names those signal joints (OS 112 west of 112, West Main Ext through 111L). Dispatcher Panel Help/Quit chrome removed (CTC Panel bottom strip only). Reload **CATS Master4**. Not deployed.



Updated: 2026-08-23 — Master 4 Digicon loads locally again. Crash was named BLOCK facing a plain SecEdge (`discoverAdvanceVitalLogic` ClassCast), then anonymous BLOCK (`MyBlock` null). Wired copy now names the mate occupancy. Reload **CATS Master4**. Not deployed.

Updated: 2026-08-22 — Live: McKees Rocks → West Main Ext went **forward** after the first-hop facing overlay. Confirms leftover U-turn (not balloon/hairpin wiring). [`DISPATCHER_LAYOUT_HOOPS.md`](DISPATCHER_LAYOUT_HOOPS.md).

Updated: 2026-08-22 — McKees Rocks → West Main Ext allocated Via OS 115 but ran reverse into McKeesport: HART facing overlay had dropped stock’s dialog invert, so the leftover first-move U-turn loaded `*_rvs.xml`. Overlay now keeps registered facing on that first hop. Not a balloon/hairpin wiring bug. [`DISPATCHER_LAYOUT_HOOPS.md`](DISPATCHER_LAYOUT_HOOPS.md).

Updated: 2026-08-22 — Closed [JMRI#15408](https://github.com/JMRI/JMRI/pull/15408) (more live testing required). Overlay stays. One McKeesport → West Main Ext via McKees Rocks dispatch reached the dest (stop nosed into 111 / mast `111L`). [JMRI#15407](https://github.com/JMRI/JMRI/issues/15407) still open. [`DISPATCHER_LAYOUT_HOOPS.md`](DISPATCHER_LAYOUT_HOOPS.md).

Updated: 2026-08-22 — Run Dispatcher System SyntaxError (`print "closed Option"`) was HART `print_function` leaking in JMRI’s shared Jython engine, plus Pi Logix still pointing at stock `Startup.py`. Wrapper compiles stock files with `dont_inherit`; IX:DSLX:1C1 now runs `preference:jython/hart_dispatcher_startup.py`. Restart PanelPro on the Pi to pick it up. [`DISPATCHER_LAYOUT_HOOPS.md`](DISPATCHER_LAYOUT_HOOPS.md).

Updated: 2026-08-22 — Asked JMRI about first-registration facing invert: [JMRI#15407](https://github.com/JMRI/JMRI/issues/15407), PR [JMRI#15408](https://github.com/JMRI/JMRI/pull/15408). HART overlay stays until that lands. CATS Digicon still names body tracks **S-1…S-5** on occupancy `Block 2-4`…`Block 2-8`; throats share those sensors and are not on the Masters. [`DISPATCHER_LAYOUT_HOOPS.md`](DISPATCHER_LAYOUT_HOOPS.md).

Updated: 2026-08-22 — Facing overlay vs stock: invert still in JMRI 5.16 / master; [JMRI#14365](https://github.com/JMRI/JMRI/issues/14365) shipped it as “store last moved.” Filed as [JMRI#15407](https://github.com/JMRI/JMRI/issues/15407). HART 5.15.5 / Pi 5.15.4plus. [`DISPATCHER_LAYOUT_HOOPS.md`](DISPATCHER_LAYOUT_HOOPS.md).

Updated: 2026-08-22 — Documented `patch_dispatcher_facing.py` as an overlay, not a root fix: stock `MoveTrain.set_train_direction` inverts the facing dialog (leftover siding branch). HART stops the invert at runtime. Real fix is stock Dispatcher System. [`DISPATCHER_LAYOUT_HOOPS.md`](DISPATCHER_LAYOUT_HOOPS.md).

Updated: 2026-08-22 — Stage 1 re-run after South Yard throats: **91 sections / 688 transits / 1508 HEAD_AND_TAIL traininfo**. S-1…S-5 are arrival/departure stations (62 inbound traininfo each) via **103** or **East Lead**. Throat comments are “not a station” — CreateGraph matches the substring `stop`. Native SML **86 dests** (84 LE + 2 Princess). Hoops: [`DISPATCHER_LAYOUT_HOOPS.md`](DISPATCHER_LAYOUT_HOOPS.md).

Updated: 2026-08-22 — South Yard S-1…S-5 hidden throat blocks landed (`S-2 West`/`S-2 East`, … sharing body occupancy). Virtuals on the new boundaries (`103L`/`110L`, `104L`–`107R`). Stage 1 after this geometry is the 91/688/1508 graph at the top of this file.

Updated: 2026-08-22 — Earlier all-stations Stage 1 (82/534/1252, S-2/S-4/S-5 origin-only) superseded by the throat Stage 1 at the top of this file. Manual Princess pairs and Stage 2 options from that pass still apply.

Updated: 2026-08-22 — Digicon BUTTON icons on Pi/Windows are absolute files under `JMRI_UserFiles/resources/buttons/` (CATS uses `java.io.File`, not `preference:`). PNGs already deploy there. No CATS jar patch.

Updated: 2026-08-22 — Wiki cleanup: `hart-panel.md` / `cats-integration.md` match the live Masters + SML desk (Gate 1 `HART.xml` is history).

Updated: 2026-08-22 — Yard-ladder LE triangles live at `preference:resources/buttons/` (`triangle_idle.png` / `triangle_active.png`) and deploy copies them into JMRI user files on Mac/Pi/Windows. They are not loaded from the hart clone.

Updated: 2026-08-22 — CTC Panel Help/Quit is the **bottom** Apps button strip only (unwraps the extra top toolbar; File keeps a single Exit, no extra Quit). Dispatcher Panel still has the in-window toolbar. Cleared 20 retained MQTT junk topics. STS is the Home.html link only.

Updated: 2026-08-22 — Mac and Windows now match the Pi for Start Up scripts: copies live in `preference:jython/` (profile `jython/` on Mac/Windows; `JMRI_UserFiles/jython/` on the Pi). PerformScript no longer points at `home:hart/...` or `/Users/lnevo/hart/...`.

Updated: 2026-08-22 — LogixNG window hide is the same on every host: **IQC:AUTO:0002** targets **USS CTC** (not USS CTC Editor). **IQC:AUTO:0004** only hides **HART Railroad**, and only under CATS. WiThrottle / USS CTC / Dispatcher System stay IQC:0001–0003. `hide_cats_desk_windows.py` imports `JmriJFrame` from `jmri.util` (LogixNG ActionScript was failing on `jmri.util.swing`).

Updated: 2026-08-22 — Dispatcher System registration now has the full DecoderPro roster. Setup Train in Section only lists locos with a speed profile; the same synthetic 10-step / 400 mm/s profile 2091 already had is now on every live roster entry. Reopen **Setup Train in Section** (restart Dispatcher System if the list is still only 2091). Measured profiles still belong in [`projects/speedmatching.md`](projects/speedmatching.md).

Updated: 2026-08-22 — LCOS wiring docs in git at [`docs/wiring/`](../docs/wiring/README.md): inventory **v85**, `Wiring_Schematic.pptx`, Digicon as-built **v2**, frozen `signals_split_v8`. Public names + new 114LA/115LA/117* searchlights synced; Desktop `HART/Wiring Documentation` still the bench copy.

Updated: 2026-08-22 — Yard plates: **W-1 / W-2** (was West Yard 1/2), **East Lead** (was South Yard East), **EH-1 / EH-2 / EH-3** (was Engine House 1–3). Every tables.xml bean has a User Name; missing comments filled.

Updated: 2026-08-22 — Stub bumper virtuals **101LA/101LB** (west end) and **115RA/114RA** (east end) use the EH-style bound slot so JMRI can resolve a facing block on END_BUMPER (connect1 only). Stops CATS SML `No facing block found for destination mast`.

Updated: 2026-08-22 — LE **119** plate moved left (x 586→548) so it no longer sits on **118**. LogixNG hides **WiThrottle**, **USS CTC**, and **Dispatcher System** at every start (IQC:AUTO:0001–0003). Under **CATS**, IQC:AUTO:0004 also hides **HART Railroad**. Script: `preference:jython/hide_cats_desk_windows.py`.

Updated: 2026-08-22 — Panel window titles: Layout Editor is **HART Railroad** (was My Layout / HART); Panel Editor USS machine is **USS CTC** (was `Panel `). Entry/Exit `layoutPanel` and Dispatcher `lename` match.

Updated: 2026-08-22 — South Yard body tracks renamed **S-1…S-5** (was South Yard 1–5 / SY-1…SY-5). JMRI block userNames, dispatcher stations/MoveTo, and CATS `BLOCK NAME` match the Digicon plates. Occupancy sensors stay `Block 2-4`…`Block 2-8`.

Updated: 2026-08-22 — NX 117RB lamp moved to y=353, even with NX 102LB on East Main Ext.

Updated: 2026-08-22 — Restored Dispatcher System OS occupancy circuit icons on My Layout (19 plant/OS `Block n-n` dots at Stage 1 positions). Station occupancy dots unchanged.

Updated: 2026-08-22 — Earlier Stage 1 pass (Scale, Barn, S-1 only) superseded by the all-stations run at the top of this file. Manual pairs and Stage 2 options from that pass still apply.

Updated: 2026-08-21 — LE cleanup: MTT100/113/114/115 are TWOSENSOR on the same FB as Switch 100/113–115 (M2T); 114→McKeesport bezier tangent at A62 now matches the frog (0° kink); zero-length K-2 F5-S-0 merged. Hidden stub-end virtual masts added for new dispatcher stations — **Stage 1/2 not re-run yet** (traininfo still 220 / original 8). Run Stage 1 in PanelPro (not CATS), then `fix_traininfo_detection.py` + `reconcile_dispatcher_stations.py`.

Updated: 2026-08-21 — ADR-005 public names applied and deployed `--pi --win`. Discover 36 dests; PanelPro smoke 23/41/102/220; CTC Logic starts (12 columns). Hardware MQTT / `Block n-n` / `Switch n` unchanged. Optional later: node 13 occupancy walk-down.

Updated: 2026-08-20 — Yard ladder (116 / 103) is unsignaled / local; T6 is back on the 117 yard lead. **CATS CTC** / **CATS ABS** still `HOLD_ONLY` and paint SML. System overview: [`cats/docs/HART_DIGICON_SYSTEM.md`](../cats/docs/HART_DIGICON_SYSTEM.md).

## Layout Editor polish contract (2026-08-20)

- Writable full-config source: `tables/new_tables.xml`; deployment bundle:
  `jmri/layouts/hart/output/tables.xml`; `hart_prod.xml` is the standalone
  monitor artifact. Never copy the working file wholesale over the deployment
  bundle because the latter owns USS CTC data.
- The 23 LE signal icons use consistent right-hand trackside placement and
  native 1:1 AAR artwork. Station occupancy dots stay; Dispatcher System
  **OS occupancy** circuit icons (`Block 4-5` / OS 102, etc.) stay on
  **HART Railroad** at Stage 1 positions. Other leftover `Block n-n` dots are omitted
  because track coloring already shows occupancy. Reapply/check with
  `jmri/layouts/hart/scripts/polish_hart_layout_editor.py`.
- Dispatcher graph stations (CreateTransits origins): all **22** — Main West,
  West Main Ext, McKees Rocks, McKeesport, East Lead, Main East,
  East Main Ext, Brick-Plane, Scale, Barn, EH-1…EH-3, S-1…S-5,
  W-1/W-2, K-1/K-2. Deployment is **91 sections / 688 transits /
  1508 HEAD_AND_TAIL traininfo**. S-1…S-5 are arrival/departure
  stations (enter/leave via 103 or East Lead). The change left the A48 stale-file repair in
  place; smoke still verifies every TrainInfo against the live graph.
- **Dispatcher compatibility fixed (2026-08-20):** HART now launches the stock
  Dispatcher System through `hart_dispatcher_startup.py`, so its classes are
  patched in the same Jython namespace. Missing registration speed factors
  default safely to 100%; route-clear checks and allocation highlighting cover
  only the requested start/destination subsection and fail closed on invalid
  mappings. The A48
  change left 40 stale TrainInfo files; all were repaired against the live
  graph and the smoke gate verifies ordered routes (now 1508). Deployed to Pi,
  Mac, and Windows profiles.
- Regression gate:
  `python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict`.

## Signals — native SML live (2026-08-18)

- SML is **native**: 36 dests discovered by Layout Editor, stored `useLayoutEditor=yes` in `tables.xml`; the `apply_sml_cats_pairs.py` hand-pair injector and its startup Jython are retired (PAIRS kept as oracle for `cats/scripts/validate_le_signalling.py`). Re-running Discover is safe.
- Two-head homes retyped to custom **`hart-aar` `SL-2-digicon`** (in `cats/resources/signals/hart-aar/`; deployed by `sync_hart_package.sh`). Stock `SL-2-high-abs` pinned masts at Stop behind an Approach (its mapping only offered undisplayable Advance Approach / Approach Medium) — root cause of the "always red" signals. Dwarfs stay AAR-1946 `SL-1-low`.
- MQTT mimic QA green (30/30): `cats/screenshots/mimic_qa/run_native_sml_qa.py` — covers 100/102, 110, 111a, 114/115, K-1/K-2, A48 balloon occupancy, 117/117b, incl. diverging **Medium Clear** (R/G) and 3-aspect **Clear** chaining. Notes: `cats/screenshots/mimic_qa/native_sml_qa_notes.md`; runtime criteria dump: `jmri/layouts/hart/scripts/dump_sml_criteria.py`.
- **A48 balloon facing corrected (2026-08-20):** because A48 joins the east ends of both loop blocks, the McKeesport mast (`IH134`) protects McKees Rocks / OS 115 and the McKees Rocks mast (`IH141`) protects McKeesport / OS 114. The CATS icon positions and physical IH wiring were already correct; only the Layout Editor directional slots and native SML/section associations were reversed. Live Pi verification after deployment: `IH134` Yellow, `IH141` Green.
- **CATS "blank windows" bug fixed (2026-08-18)**: unpainted System Console / clock / WiThrottle windows were CATS `Screen.init` dying on the Swing EDT at panel load, not LogixNG. Two causes, both fixed: (1) K-1/K-2 boundary sections (43,6)/(43,7) had anonymous `<BLOCK />` edges → `ClassCastException` in `discoverAdvanceVitalLogic`; now named `OS 115 (Princess)`/`OS 114 (Princess)` in all four Masters. (2) drive-mode templates requested `Restricting`, which `hart-aar` masts don't define → `IllegalArgumentException`; `aar_aspect_bridge.py` now maps RES_\*→Stop and R283/R286→Medium Clear/Medium Approach (CATS lamps paint the diverging pair). Verified: CATS ABS loads clean on the Pi, all windows paint.
- **Held ownership (2026-08-18)**: `unhold_signal_masts.py` retired (removed from Mac/Pi profiles, sync, and installers). Masts boot Unheld, so SML runs ABS by default with no script; **Held is CATS CTC's channel**. Verified live on the Pi: CTC load holds all 25 masts at Stop; left-click entrance (`Princess West OS 113b`) → CATS unholds, SML posts Approach, MQTT head goes Yellow; click again → re-held, Stop, Red.

## Yard ladder off CTC signals (2026-08-20)

- Removed virtual masts **`West Yard North OS 116`** and **`South Yard East OS 104`** from LE, SML, CATS, and the USS machine.
- **`West Yard East Yard T6`** is back on **TO117.B** (yard lead into Barn) — CATS `(14,7) RIGHT`, LE icon `(520, 322)`. It is a **117 westbound home** again (SIDI RTL + TRL dest `Plane East OS 102`).
- CTC columns **116 / 103** are **switch-only** (SIDI/SIDL/TRL off; signal levers 10 and 12 stripped). Background tiles are stock `Panel-switch-7` (switch plate + brass blanks, no SIGNAL plate). Switch levers 9 / 11 and lock toggles stay.
- Lock toggles **116, 103, and 110** default **Local** (`IS10/12/22:LOCKTOGGLE` ACTIVE) via `ctc_default_reverse_levers.py` and Logix `IX:CTC:REVDEF`. Dispatcher can still lock a column and code the points.
- Re-apply: `python3 jmri/layouts/hart/scripts/revert_barn_ladder_signals.py` then rebuild CATS hold copies.

## JMRI CTC — full plant, 15 columns with Barn (2026-08-19)

- **Barn interlocking inserted** (cols 4-6, geographic order kept): full rebuild via `jmri/layouts/hart/scripts/build_ctc_full_15col.py` (replaces the incremental brick-plane/east-end scripts; those are kept for history). Columns west→east: 1-3 Brick/Plane (SW101, 100, 102), **4-6 Barn** (SW117 LH xover `Block 13-3`+`13-4`, SW116 `Block 3-1`, SW103 `Block 3-2`), 7-12 East End (SW107, 108, 111 xover, 109, 110, 112), 13-15 Princess (SW113 xover, 114, 115). **Princess levers renumbered 19-24 → 25-30.** 23 masts CTC-held.
- **Dwarf relocated to make Barn a real plant**: `West Yard East Yard T6` moved from the 116-117 boundary (TO117.B) to east of Switch 103 (TOR14.B) — its section now spans SW103 + SW116 + the 117 crossover, mirroring how the East End east home covers 111/112. SML re-discovered; westbound pairs from Yard Track 1 now run through the whole plant to the Plane homes.
- **Two new entrance dwarfs** (virtual masts `IF$vsm:AAR-1946:SL-1-low($1001/$1002)` — no hardware yet, swap to MQTT heads later): **`South Yard East OS 104`** at Switch 104's Yard Track 2 leg (governs up-the-ladder moves west into Barn; also splits the old over-long East Lead→Plane pairs) and **`West Yard North OS 116`** at Switch 116's C leg (governs West Yard ladder moves east into the plant). `East Lead → South Yard East OS 104` had to be added as a **manual fixed pair** (discovery declines it; criteria derived live via `ConnectivityUtil`: SW112 N, SW110 R, SW109 R).
- **Topology can't see north/south entrances**: `Topology.getTrafficLockingRules` only walks east/west neighbors, so the two ladder masts got hand-built TRL rules (col 9/10 right: SW116 R + SW103 N→`East End West Yard Track 1` / SW103 R→`East End South OS 110`; col 11/12 left: SW103 R routes to the Plane homes). Everything else auto-generated — including eastbound Barn routes threading the **uncontrolled** Switch 104 (occupancy-only, correct).
- Verified live on Barn: lever 12 Left + code → `West Yard East Yard T6` unholds to Restricting (Yard Track 1 route), `South Yard East OS 104` unholds but correctly sits at Stop (needs SW103 R); normalize + code re-holds (time locking). Lever 10 Right correctly **rejected** with SW116 Normal; after SW9 lever Reverse + code (Switch 116 is DIRECT feedback, no FB sensors) → accepted, `West Yard North OS 116` clears to Restricting. Switch-lever sensors are `IS<odd>:LEVER`, **ACTIVE = Normal, INACTIVE = Reverse**; a switch won't move while its signal lever is off Normal (correct USS behavior).
- **Panel v21 — CTC-held masts on the USS diagram (2026-08-20)**: Quaker Valley-style proto lollipops (`sig-h-2` / `sig-d-1`, recolored by aspect) sit on the track diagram at each CTC home so it is obvious which lever owns which signal. Two-head homes are live `<signalmasticon>` (`imageset` `ctc` / `ctc-w` on `hart-aar`); dwarfs are `<signalheadicon>` on the IH* head. 116/103 stay blank (switch-only). Regen: `gen_ctc_track_plan.py`; GIFs in `ctc/icons/sig-*.gif`.
- **Panel v20 — Engine House top spur + CTC icons on Mac/Windows (2026-08-20)**: house track 1 shortened to a new 35px `thin035.gif` so it abuts the `thin459` ladder tip at x=428 instead of overlapping it. Custom `preference:ctc/icons/` gifs now install into Mac `*.jmri` profiles and Windows `JMRI_UserFiles` / `*.jmri` via `sync_hart_package.sh`.
- **CTC locking vs JMRI (2026-08-20)**: SW112 Closed is East Lead↔110 (Thrown = Main East) — CTC icon `swap:` removed and the 112 eastbound TRL flipped from Reverse to Normal. Princess **114/115 traffic BOTH** (balloon) with unique LTR masts `Princess East McKeesport` / `Princess East McKees Rocks` — JMRI requires a signal in every enabled direction and forbids sharing a mast across columns (empty lists on 25/26–29/30 threw SignalDirectionIndicators errors). **113 stays RIGHT** (east homes only). SW111 eastbound Main West→West Main Ext was missing (only the Yard Track 1→113a rule existed) — added RIGHT dest `Princess West OS 113b`. SW103 westbound from the South Yard ladder was rejecting because TRL occupancy included **OS 104 (Block 3-3)** — the approach the train is sitting on; dropped from the 103 Reverse rules. Re-apply via `jmri/layouts/hart/scripts/patch_ctc_locking.py`.
- **CTC levers 100/112/114/115 default Reverse (2026-08-20)**: those turnouts rest **Thrown** in JMRI — the machine should start with the selector at **R**, not remap Closed/Thrown. Feedback Different on SW100 and the uid-14 TRL flips were reverted (they made CTC disagree with JMRI). Brick CTC icon `swap:` removed so Thrown shows the thrown graphic. `ctc_default_reverse_levers.py` sets `IS3/23/27/29:LEVER` Inactive after CTC start and after Reload; Logix `IX:CTC:REVDEF` does the same on `IS:RELOADCTC`.
- **Panel v19 — shorter Engine House, 100-102 lamp on the hairpin, one 113-115 gap (2026-08-19)**: Engine House stubs cut back so their west ends line up with T6 (x=393). Block 4-6 lamp moved left to (150, 103) onto the hairpin "\\". 113→115 connector flushed to SW113, leaving a single gap before SW115 (the v17 both-ends gaps are gone).
- **Panel v18 — 100-102 lamp in the hairpin, 117/116-103 gaps (2026-08-19)**: **OS 102's lamp returned to the machine row** at (229, 200) with the other switch OS lamps. The lamp that belongs on the diagram is **Block 4-6 (100-102 / Brick-Plane)**, now at (164, 103) in the hairpin corner on the same plane as T1 / T6 / Yard 1 / East Lead. **Block-boundary gaps** added between SW117 and Yard T6 (and 117's main-east dip) and between SW116 and SW103 (6px empty, SW103 moved +6 with its east ladder; no intervening block).
- **Panel v17 — banner, OS 102 on the curve, block-boundary gaps (2026-08-19)**: **"HART RAILROAD - NEVILLE ISLAND" banner** (16pt black) centered in the gold band at the top. **OS 102's lamp moved off the machine row back onto the diagram** — centered in tile column 3 at (164,119), riding the hairpin's "\\" stroke (the 102 circuit); its "102" number label stays under the lever column. **Block-boundary gaps cut in** (3-4px, matching the K-2|114 look): W-1 and W-2 end short of SW101's bar/leg; Yard T1 now floats between SW102's leg tip and SW117's icon (gaps both ends); East Main Ext gapped off SW102's bar; West Main Ext ends short of SW113; and the v12 bridges at 113↔115 and 115↔K-1 are **reverted** — the 113-115 connector has gaps both ends (separate OS circuits) and K-1 starts 3px east of SW115's icon (rebuilt from two line050s, still flush at x=1106).
- **Panel v16 — Unlocked buttons replaced by the OS lamps (2026-08-19)**: the stock **Unlocked indicators (y200) and their "Unlocked" labels (y230) are stripped** — QV-style, GUI only; the `IS*:UNLOCKEDINDICATOR` sensors and all TUL logic in ctcdata are untouched, and two STRIP patterns in the generator (delete them to bring the buttons back) do the removal on every regen. **The OS lamp row dropped from y176 to y200** into the vacated spots, with the **switch number labelled under each lamp/pair** (y223, white 8pt): 101/100/102, 117/116/103, 111/110/112, 113/114/115.
- **Panel v15 — OS lamps to the machine row, K-track lamps (2026-08-19)**: **all 15 turnout OS lamps slid down into a row at y176, directly above each switch column's Unlocked indicator** (y200) — the track diagram now shows only turnout icons + block lamps, fully uncluttered. Crossover columns carry their two OS lamps side by side centered on the column, upper track's lamp on the left (117: 347/371, 111: 607/631, 113: 867/891). **Duplicate K-track lamps added** on the same sensors (`1-4` on K-1 at y80, `1-3` on K-2 at y103, both x1060) forming an aligned four-lamp column with McKees Rocks/McKeesport. **East Main Ext flattened** (the `line1` at 258 was 1px low — y131→130, bar now 134-138 straight into SW117). **Engine House ladder lip trimmed** with a new 9px `thin459.gif` (top even with house track 1 at row 82, bottom at SW116's leg exit).
- **Panel v14 — lamp row polish (2026-08-19)**: **OS 102's lamp dropped onto the hairpin's lower stroke** at (166,126) — embedded on the curve that IS the 102 circuit, level with the Main West Brick-Plane (`4-6`) and East Main Ext (`4-7`) lamps. **Crossover lower lamps raised to mirror the uppers** (lamp gif is 21x21; uppers at bar top − 14 dip 6px into the bar, so lowers moved to bar bottom − 6: 117b y132, 111b/113a y109); OS 115's below-bar lamp raised to y91 to kiss its bar the same way without covering the McKees Rocks riser.
- **Panel v13 — OS lamps lifted off the turnouts (2026-08-19)**: **turnout OS lamps no longer cover the switch graphics** — single turnouts get the lamp fully above the icon (row N y74, yard row y97), crossovers get the upper-bar lamp above and the lower-bar lamp below the icon (117b at y140, 111b/113a at y117 — 111b clips the top thin yard siding by 2px, acceptable), and **OS 115's lamp goes below its bar** (the McKees Rocks riser fills the icon above). Block lamps stay embedded in their track lines as before. **OS 102's lamp moved into the hairpin pocket** at (163,97) — same x as OS 100's lamp, same row as the yard-row OS lamps — since the "<" hairpin IS the 102 circuit. **W-1/W-2 lamps moved east to x=48** so they clear the W-1/W-2 labels. **Engine House dropped against the yard lead**: track 2 now joins SW116's leg exit itself (y90), track 1 one 9px pitch above (y81), ladder shortened to a single `thin4512`, label down to y68.
- **Panel v12 — block joins, left margin, label moves (2026-08-19)**: **SW116 slid east to abut SW103** (icons touch at x475/476 — they connect directly, no block; the old unnamed segment between them removed and its space absorbed into the **Yard T6 stretch** 117→116, T6/OS116 lamps recentered; Engine House fan moved +25 with the switch, stubs flush x=365). **West Main Ext joined flush to SW113's bar** (the floating `line025` at 840 that read as an extra block replaced by an overlapping `line050` — one continuous line SW111→SW113) and the **113↔115 direct connection closed up** (10px drawn gaps on both sides of the stub bridged; no phantom block). **W-1/W-2 stubs pulled off the left cap** to start at x=23, mirroring the 11px east-edge margin (labels moved to x=24). Labels: **WEST YARD promoted to a 12pt white station name** between the W-* lamps and SW101, **BRICK over SW100**, **BARN over the 117 crossover**, **ENGINE HOUSE moved onto the fan** (where BARN used to sit).
- **Panel v11 — Main West lamp at Plane, Engine House (2026-08-19)**: second **Main West lamp (`2-1`) at the Plane/blank-4 boundary** (x260 on the row-N line east of SW100's throat — same sensor as the blank-column-8 lamp, so the dispatcher sees the around-the-room block lit at both ends). Engine fan renamed **ENGINE HOUSE** and cut to **two stubs** (top y68 spur + its `thin4512` ladder tip removed; ladder is now just the single `thin-45` off SW116's leg), stubs pulled in to flush x=340 and the label dropped to (302,64) so the whole facility tucks tight against the yard row.
- **Panel v10 — Brick hairpin "<" on the Main West level (2026-08-19)**: Brick's main moved UP to the **Main West row (bars 88-92)** — W-1 → SW101 → SW100 with **Main West running east from SW100's throat at the same height as its restart in blank column 9** (west of SW111), so the dispatcher reads Main West as one level across the board. **SW100 drawn `os-l-w` ("-/-", gifs still swapped: closed = throat→leg)** with its diverging leg forming a **"<" hairpin** (CATS-style): leg down-west to (160,115), then a new thick 24px 45° piece (`ctc/icons/thick45-24.gif`, cropped from stock `b-45`) back down-east onto row M = Main West Brick-Plane (`4-6` lamp) into SW102. **SW102 reverted to `os-l-e` on row M, NO gif swap** — its bar IS the continuing route (Brick-Plane ↔ East Main Ext) with the up-east leg = Yard T1, so v9's swap for 102 was wrong and is undone (SW100/112 keep theirs). W-2 stub now on the 111-115 level off SW101's leg; W-1/W-2/WEST YARD labels and lamps moved up with it. **Main East lamp (`2-3`) + MAIN EAST label moved into blank column 8**, stacked under the Main West (`2-1`) and Yard Track 1 (`2-8`) lamps; SOUTH YARD label shifted east to clear it.
- **Panel v9 — Brick topology fixed + state-correct icons (2026-08-19)**: **SW100 redrawn to match the real LE topology** — its straight route is 101 ↔ the **MAIN WEST stub** (gapped, east of SW100 on the main row; the westbound main loops around the room to SW111's approach), and its **diverging leg rises to the yard row**: Main West Brick-Plane (`4-6`, lamp moved to the riser) → **SW102 now sits ON the yard row** (stock `os-r-e`, bar = Brick-Plane ↔ Yard T1) with its **thick leg dropping back to the main row = East Main Ext** (the route that curves back east), into SW117's main bar. **Closed/thrown gifs swapped for SW100/102/112** (new `swap:` kind in the generator): LE continuing sense says closed = Main West→Brick-Plane at 100, Brick-Plane→East Main Ext at 102, and Main East→East Lead at 112 (`continuing=4`) — all three are the drawn LEG, so the swapped gifs make the lit route track the real turnout state. South Yard tracks tucked up under Yard Track 1 (rows 129/138/147, branching off the 45° icon legs themselves; ladder tails are single `thin4512` pieces ending exactly at track 4). WEST YARD/W-1/W-2 labels moved clear of the left cap and OS lamps; SOUTH YARD label slid below the yard; McKEESPORT label down 5px.
- **CTC machine + panel v8 — 17 slots, 45° yard ladders (2026-08-19)**: new **blank column between Plane and Barn** — four interlockings of three lever columns each with blank separators (blank slots 0/4/8/12/16; Brick/Plane 1-3, Barn 5-7, East End 9-11, Princess 13-15). Machine elements x≥260 shifted +65 in both files, `GUIColumnNumber`≥5 bumped +1 (now 2-4, 6-8, 10-12, 14-16); background tile row regenerated for 17 slots (right cap x1117, window 1190 wide). **Connector lamps centered in the blank columns**: East Main Ext `4-7` (main) + **new Yard T1 `4-8` lamp** (the Plane→Barn diverging block, was missing) in slot 4; Main West `2-1` + Yard Track 1 `2-8` in slot 8; **West Main Ext `1-8` moved to the 111→113 siding** (it was wrongly drawn 113→115 — those connect directly, no block, no lamp) + East Lead `1-7` in slot 12. **South Yard redrawn as straight 45° ladders**: the SW103/110 thin icon legs are now 45° (icons regenerated) and continue as straight thin ladder lines parallel to the Main East 45° legs, with **three run-through yard tracks at 9px pitch** connecting the two ladders (SW104-109 hand-throw, not drawn; new 12px `thin4512.gif` ends the ladders exactly at the bottom track). **Engine Terminal redrawn as the same ladder rotated 180°** — up-west off SW116's 45° leg, three stub tracks flush at x=330 (split = hand-throw SW118, treated like 104-109). Branch stubs K-1/K-2/McKees Rocks/McKeesport all **end flush at x=1106 with lamps aligned at x=1060**; W-1/W-2 flush at x=0, lamps aligned x=30, labels aligned. Main East bottom straight rebuilt with overlapping `line25`s (line gifs have big intrinsic end margins — 12px on line25 — which had left false "joint" gaps inside one block).
- **Panel track plan v7 — background retiled, thin turnout legs, Engine Terminal (2026-08-19)**: the "hidden right column" was the **stale 15-column gold background** (left cap + 15 `Panel-sw-sig/switch-7` tiles + right cap at x987) left over from the first CTC build — the generator now owns the background row too: left cap x0, 16 tiles at `12+65*slot` (`Panel-blank-7` for blank slots 0/7/11/15, `Panel-sw-sig-7` for the 12 lever slots), right cap x1052. **SW103/110/116 switched to custom thin-leg turnout icons** `os-{l-w,r-e,r-w}-thin-*` in `ctc/icons/` (stock bar rows copied verbatim so closed keeps the full bar + detached leg and thrown keeps the bar gap + connected leg; unknown/inconsistent are stock copies with glyphs) so the diverging legs into the yards match the thin QV-style fans. The SW116 fan is the **ENGINE TERMINAL** (split = hand-throw SW118, 2 of 3 spurs drawn); **WEST YARD label moved to the W-1/W-2 staging stubs** (blocks West Yard 1/2; W-1 lamp nudged east to make room). **New lamp `Block 1-8` (West Main Ext)** on the 113→115 Main West stretch. Whole diagram shifted down 8px (McKees Rocks label was crowding the header). Regen: `python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py <GUIObjects.xml> [tables.xml]`; icons deployed to Pi `JMRI_UserFiles/ctc/icons/`.
- **Panel track plan v6 — straight rows, thin yard lines, long spurs (2026-08-19)**: run-through row now dead straight SW103 → K-2 panel edge — **SW112 redrawn `os-l-w`** (bar on the row, leg dropping SW into the main's 45° rise; the old bar-level dip + East Lead riser removed). Fixed a 6px jog in the 111→113 Main West line (a `line025` filler was at y72, needed 78). Approach lamps moved into the blank machine columns: **East Lead `Block 1-7`** in slot 11 (between 112 and 113) and **new `Block 2-1` Main West lamp** in slot 7 on a lengthened approach stub west of SW111. **Ladder OS lamps 12-1/12-3/12-5 removed from the board** (hand-throw yard, revisit later). W-1/W-2, K-1/K-2, McKeesport and McKees Rocks are now **long horizontal east/west stubs to the panel edges** with lamps/labels on them (McKeesport bar 131-135 under the K-2 row; McKees Rocks bar 57-61 above K-1). Yard symbols redrawn with **thin 2px lines, QV style** — custom gifs in `jmri/layouts/hart/ctc/icons/` (`thin044/thin085/thin-45`), referenced as `preference:ctc/icons/*.gif`, **deployed to Pi `JMRI_UserFiles/ctc/icons/`** (install there for any other machine running the CTC panel); South Yard fans off 103/110 now mirror-identical, plus a **new small West Yard fan up-west off SW116** with `WEST YARD` label. Panel window geometry normalized to x40/y40 1120×780 so all 16 slots (incl. the right blank) are visible without scrolling.
- **CTC machine v5 — 12 columns + blank spacers; SW107/108/109 now hand-throw (2026-08-19)**: the three East End ladder columns (uid 19/20/22, levers 13/14, 15/16, 19/20) removed from ctcdata — those switches have no CTC control anymore (yard crews throw them; their OS blocks 12-1/3/5 still show as lamps on the South Yard fan, and SML still checks their turnout feedback). New 16-slot machine layout at 65px pitch with **blank slots 0 (left), 7 (Barn|East End), 11 (East End|Princess), 15 (right)**: Brick/Plane slots 1-3, Barn 4-6, East End 8-10 (111/110/112), Princess 12-14. `GUIColumnNumber`s renumbered with gaps (2-7, 9-11, 13-15) and `GUIDesign_NumberOfEmptyColumnsAtEnd`=1 so a future CTC GUI regeneration reproduces the spacing; six TRL `<switch>` entries referencing the removed uids were dropped (rules still require the ladder occupancy sensors; alignment of hand-throw switches is enforced by SML only). Machine GUI elements band-shifted/deleted by x//65 in both `GUIObjects.xml` and the `tables.xml` paneleditor (one-off script, /tmp). Lever numbering keeps its gaps (…11/12, 17/18, 21/22…) — internal sensor names unchanged. Diagram respaced to the new slots; SW110's fan redrawn inverted-mirror of SW103's (step at the switch, line1 spurs west) with the three ladder lamps spread along it. **Princess detection clarified: OS 114 and K-2 are one circuit (`Block 1-3`), OS 115 and K-1 are one circuit (`Block 1-4`)** — single lamp each at the OS position (tooltip says "+ K-n"), while McKeesport (`Block 1-2`) and McKees Rocks (`Block 1-1`) have their own lamps out on the branch stubs.
- **Panel track plan v4 — QV-style yard fans + staging block lamps (2026-08-19)**: SW107/108/109 turnout icons removed from the diagram (levers stay) — the only yard track drawn is Yard Track 1 (run-through) plus the South Yard represented QV-style (like Johnstown/Enola on the Quaker Valley panel): a two-spur fan heading **east off SW103's stub** and the inverse fan heading **west off SW110's stub**, meeting over the dipped Main East, `SOUTH YARD` label between; the ladder OS lamps 12-1/12-3/12-5 sit on the 110-side fan. New staging/approach block lamps (mapping from JMRI blocks → occupancy sensors): **W-1** = West Yard 1 → `Block 4-4` (stub due west of SW101), **W-2** = West Yard 2 → `Block 4-3` (SW101's SW leg), **K-1** → `Block 1-4` and **K-2** → `Block 1-3` (these two lamps were previously mislabeled as OS 115/OS 114 — same sensors, now on the K stubs), **McKees Rocks** → `Block 1-1` (past SW115's riser), **McKeesport** → `Block 1-2` (on SW114's stub). Main East lamp `2-3` moved west to (320,148) clear of the 103 fan.
- **Panel track plan v3 — East End ladder + header clearance (2026-08-19)**: everything shifted ~40px down so the plant labels (now y 52) clear the gold header band. 107/108/109 taken **off** the run-through row and drawn as a real yard ladder: SW110's diverging stub (`os-l-w`, descends to icon row 33) drops onto a **ladder sub-row** (bars y 123-127) holding 109/108/107 inline with yard-track stubs pointing down-west (dead-ending toward the South Yard — SW103's stub descends toward them from the opposite side, `YARD` label between). To make room, **Main East dips under the yard**: 45° down east of SW117's bottom bar (bar 126-130 → bottom straight 156-160, physically true — the main loops around the yard), `line5` under cols 5-10 with the `Block 2-3` lamp, 45° back up into SW112. Rows now: Main West siding 80-84, run-through 103-107, ladder 123-127, main 126-130 (Brick-Barn + SW112 only), Main East bottom 156-160. Ladder lamps (12-1/12-3/12-5) sit on the ladder row; ladder icons raised 4px so yard stubs keep a visible gap above Main East. `McKEES ROCKS` moved right to clear the `PRINCESS` label.
- **Panel track plan v2 — main + sidings, QV style (2026-08-19)** via `jmri/layouts/hart/scripts/gen_ctc_track_plan.py` (declarative; regenerates both `ctc/GUIObjects.xml` **and** the embedded `<paneleditor>` in `tables.xml`; supersedes `redraw_ctc_track_plan.py`). Modeled on the [Quaker Valley CTC panels](https://www.quaker-valley.com/CTC/QV_CTCnew.html). Three track rows (bars y 40-44 / 63-67 / 86-90 — scissor icons span exactly 23px, so each crossover bridges adjacent rows): **main** = Brick 101/100 — Plane 102 — SW117 bottom — Main East (with its own new lamp `Block 2-3`) — SW112 — 45° rise (`b-45.gif`, rotation 1) — SW113; **yard run-through siding** (Plane/Barn→East End) = SW102 diverges up, SW117 scissor top, 116 (WY-ladder stub up), 103 (South-Yard stub down), YT1, ladder switches 107/108/109/110 inline with yard stubs down, rejoining the main at SW112 (`os-r-w`, diverging up-west); **Main West passing siding** (top row) = SW111 scissor ↔ SW113 scissor, Main West stubs + labels at both ends (not drawn continuous to Brick — SW100 diverges up-east to a stub). SW115 sits on the top row (McKees Rocks up, K-1 stub); SW114 on the East Lead row (McKeesport down, K-2 stub). Plant name labels (BRICK/PLANE/BARN/EAST END/PRINCESS) + route labels. Offline preview: PIL compositor against `/Applications/JMRI/resources` icons (no live JMRI needed). Startup "Signals are non red in both directions" warning at CTC reload is benign: SML had cleared the unheld new dwarfs before the runtime took over and held everything.
- **Icon geometry cheat sheet** (all 40×40): horizontal turnouts — `os-l-w`/`os-r-e` bar rows 6-10 (diverging down-W/down-E), `os-r-w`/`os-l-e` bar rows 29-33 (diverging up-W/up-E); scissors bar rows 6-10 + 29-33; lines — `line025` 24px (bar 2-6), `line050` 44px (3-7), `line1` 85px (4-8), `line25` 203px (9-13), `line6` 481px (22-26); `b-45.gif` 30×30 "\" (rotation 1 → "/"). Lamps sit 8px above their bar top.
- **Barn signals synced to LE + CATS (2026-08-19)**: the two new dwarfs' LE icons re-stored with proper scale 1.5 / rotation; second pass moved both onto Switch 103 (matching CATS): `South Yard East OS 104` at (653,303) deg 0 — top of the South Yard ladder, facing up like `East End South OS 110`'s at SW110 — and `West Yard North OS 116` at (610,291) deg 180, west of SW103. Applied to `tables.xml` + `hart_prod.xml` on disk (PanelPro was closed; CATS CTC was running — verify at next PanelPro launch). CATS masters updated by `cats/scripts/update_barn_signals.py`: `West Yard East Yard T6` SECSIGNAL moved from (14,7) to east of Switch 103 at (21,7) RIGHT, `West Yard North OS 116` added at (18,7) TOP, `South Yard East OS 104` added at (21,7) BOTTOM (mirroring `East End South OS 110` at (31,7)); applied to `HART_Master.xml` and `HART_Master_ABS.xml` (with `CATS ` prefix), both hold variants rebuilt + validated, deployed `--all`.
- **Gotcha — LayoutEditor extends PanelEditor**: any `isinstance(ed, PanelEditor)` sweep (dispose/resize/deregister) also hits "My Layout" and "Dispatcher System". A reload sweep disposed both on 2026-08-19; restored by extracting their `<LayoutEditor>` elements from the stored `tables.xml` into a wrapper file and `cm.load()`-ing it. Also: `cm.storeConfig()` writes tables only — panels need `cm.storeUser()`.
- **Gotcha — panel reloads duplicate stored panels**: disposing a Panel Editor does *not* deregister it from ConfigureManager; after two GUI reloads the store wrote 3 copies of "Panel " into `tables.xml`. Fixed by `cm.deregister()` of ghost editors before storing. Check `<paneleditor` count after any store that followed a panel reload.
- Previous 12-column state (Princess lever-24 verification, INCONSISTENT-feedback gotcha, `Switch 1-1/1-2/1-3 FB` naming) — see git history of this section; all still applies with the new lever numbers.

## JMRI CTC pilot — Brick + Plane (2026-08-19)

- **Stock JMRI CTC** (Tools ▸ CTC, [help](https://www.jmri.org/help/en/package/jmri/jmrit/ctc/CTC.shtml)) piloted on the Pi as a possible CATS alternative: 3 O.S. sections — col 1 SW1/SIG2 = Switch 101 (OS 101 Brick, yard exits `Brick West Yard 1/2` govern left-to-right), col 2 SW3/SIG4 = Switch 100 (OS 100 Brick, `Brick East Main West` right-to-left), col 3 SW5/SIG6 = Switch 102 (OS 102 Plane, `Plane East East Main Ext`/`Plane East OS 102` right-to-left). Uni-directional sections (sparse Digicon ABS = homes on one side only).
- Built **programmatically** with `jmri/layouts/hart/scripts/build_ctc_brick_plane.py` (same factory + `Topology` auto-generate the editor uses — no manual editor entry). Traffic locking rules auto-derived from SML: 2 per section, correctly cross-referencing switch alignments (e.g. yard exits need SW100 Normal; westward Main West routes need SW100 Reverse and pick destination by SW102). Config + generated USS panel now live in `tables.xml` (`<ctcdata>` + PanelEditor "Panel "); repo copies: `jmri/layouts/hart/output/tables.xml`, `jmri/layouts/hart/ctc/GUIObjects.xml`.
- **Verified live**: runtime start holds all 5 masts at Stop (signals normal); signal lever Right + code button → traffic locking validates, unholds yard masts, SML clears `Brick West Yard 1` to Slow Clear while `Yard 2` stays at Stop (turnout not lined), R indicator lights, opposing mast stays held; normalize runs **time locking** (indicators out-of-correspondence ~3 s) then re-holds. Switch lever + code commands the turnout and waits for TWOSENSOR field correspondence.
- Gotchas: JMRI's `CreateGUIObjectsXMLFile` writes `Red-on/Red-off.gif` but the files are lowercase → "Icon Not Found" on Linux; fixed in our `GUIObjects.xml`. Code buttons are edge-triggered (set sensor Inactive→Active). Runtime doesn't auto-start: Tools ▸ CTC ▸ Run CTC Logic (or add a Start Up action); `IS:RELOADCTC` Active reloads config in place. FB sensor numbering is offset: Switch 100→`Switch 4-1 FB`, 101→`4-2`, 102→`4-3`.
- **Never run JMRI CTC runtime and CATS CTC at the same time** — both drive Held on the same masts. CATS ABS (unbound viewer) is fine alongside.

## Dispatcher System (2026-08-18) — set up, awaiting live test

- **2026-08-22 graph (yard platforms):** Stage 1 on Pi PanelPro after hidden S-1…S-5 throat blocks — **91 sections / 688 transits / 1508 traininfo**. All 22 stations are origins **and** destinations. Inbound to each S-n is 62 traininfo files (Main West, East Lead, Scale, Princess, …). Throat comments must not contain `stop`. Bumper `IF$vsm` virtuals still use the EH-style far slot. Yard virtuals sit on throat-boundary anchors, not turnout legs. Hoops: [`DISPATCHER_LAYOUT_HOOPS.md`](DISPATCHER_LAYOUT_HOOPS.md).
- **2026-08-22 graph (all stations, superseded):** earlier Stage 1 after bumper facing + turnout-leg virtuals — 82/534/1252. S-2/S-4/S-5 were origins only until the throat re-run above.
- **Stub tracks as stations**: bumper virtuals (`101LA`/`101LB`, `115RA`/`114RA`, `118L`/`119LA`/`119LB`) plus yard turnout-leg virtuals are now in the graph. Do not re-bind 104L–107L onto mid-block anchors — Discover cannot see those.
- **Never run Stage 1 or store panels from inside CATS.** CATS embeds JMRI on the same profile, so a store from a CATS session persists CATS runtime beans into `tables.xml` — 25 `IF$vsm:CATS1/CATS2` virtual masts (which then fail to load in plain JMRI: "Signal definition not found: CATS1") plus `IMDECODER_*` memories. Happened 2026-08-18; file was surgically cleaned and verified under PanelPro. Configure JMRI from PanelPro only.
- **SML survived regeneration**: Stage 1 deletes + re-discovers; result matched our 34 discovered pairs, and the 2 manual K-stub pairs (`113a→K-2`, `113b→K-1`) were re-added — 36 total, verified after restart.
- **Train detection**: DispatcherSystem hardcodes Entire Train (`setResistanceWheels(True)`) into every traininfo it generates — this is why it "kept getting overwritten". Fixed to `TRAINDETECTION_HEADANDTAIL` by `jmri/layouts/hart/scripts/fix_traininfo_detection.py`; **rerun it after any Stage 1 rerun**.
- **Roster speed profiles**: Dispatcher System registration lists only locos with a `<speedprofile>`. The same synthesized linear profile (10 steps, 400 mm/s at full) that 2091 already had is now on every live DecoderPro roster entry (`ensure_dispatcher_roster_profiles.py` / `apply_dispatcher_roster_profiles.py`). Measured profiles (Roster ▸ Speed Profiling) are left alone and should replace the synthetic ones for accurate station stops.
- Dispatcher options: `autoturnouts=yes` + `useturnoutconnectiondelay=yes` added (Stage 2 requirements); rest already correct (`usesignaltype=signalmast`, roster trains, auto-allocate, HO scale).
- Cleanups en route: K-1/K-2 block lengths set (609.6 mm); en-dashes removed from `Yard T6` comment and the `Main West Brick-Plane` block name (DispatcherSystem scripts crash on non-ASCII).
- Operator guide: [`jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md`](../jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md).
- **To test (layout on)**: launch PanelPro (not CATS) on the Pi → Dispatcher System panel ▸ *Run Dispatcher System* ▸ OK → place any roster loco at a station ▸ *Setup Train in Section* (pick block, train, facing) → *Run Dispatch* ▸ click destination station button. *Simulate Dispatched Trains* dry-runs without hardware. If the train list is stale after a roster change, close Setup Train in Section and open it again.
- **Hands off the phone throttle during a dispatch.** Root cause of the 2026-08-18 "train runs backwards" incidents: JMRI shares one throttle per loco address, and `AutoActiveTrain`'s direction is the *live throttle direction bit* — the auto engineer asserts it once at dispatch start, never continuously. Any WiThrottle direction press (or re-acquiring the loco, which re-sends the phone's last direction) flips the shared bit, and the next dispatcher speed command drives the train the wrong way (`runInReverse=yes` + `forward=True` observed live). Registration/facing answers were correct all along. Rule: release 2091 from WiThrottle before dispatching, and never nudge a stalled auto train with the phone — terminate and re-dispatch instead.
- Temporary: `jmri_cmd_watcher.py` is in the TCS_MQTT startup for agent-driven automation; remove with `python3 cats/scripts/patch_jmri_startup.py remove --profile /home/pi/.jmri/TCS_MQTT.jmri/profile/profile.xml --script jmri_cmd_watcher.py` when done testing.

## Repo / remote

- GitHub: https://github.com/lnevo/hart  
- Local workspace folder: `Panel` (same git root)  
- Agent branch pattern: `agent/<id>/<topic>` — see [`AGENTS_GIT.md`](AGENTS_GIT.md)  
- Cloud Agents: link `lnevo/hart` at [Cloud Agents dashboard](https://cursor.com/dashboard/cloud-agents)

## Product decision (stop the abstract chase)

| Deliverable | Role |
|-------------|------|
| **`cats/panels/HART_Master_CTC_hold.xml`** | **CATS CTC** — routes/turnouts on; signals HOLD_ONLY; JMRI SML owns aspects |
| **`cats/panels/HART_Master_ABS_hold.xml`** | **CATS ABS** — signals HOLD_ONLY; turnouts on |
| **`cats/panels/HART_Master.xml`** | CTC geometry source (rebuild CTC hold; no desktop icon) |
| **`cats/panels/HART_Master_ABS.xml`** | ABS geometry source (rebuild ABS hold; no desktop icon) |
| `cats/panels/sheets/HART_sheet_West_Yard2.xml` | Legacy sheet WIP — **do not checkpoint**; Masters are the live copy |
| `cats/panels/HART_ctc.xml` | Earlier CTC schematic experiment |
| `render_ctc_panel.py` PNG | **Review art only** — cannot open in CATS |

See [`cats/docs/HART_DIGICON_SYSTEM.md`](../cats/docs/HART_DIGICON_SYSTEM.md) and [`cats/docs/DIGICON_VS_CTC_PNG.md`](../cats/docs/DIGICON_VS_CTC_PNG.md).

## Collaboration (Mac ↔ Cloud)

| Role | Owns |
|------|------|
| **Mac / local** | Builder cell-role fixes, live CATS load, occupancy path accept, screenshots |
| **Cloud** | Help on builder/verify when asked; do not overwrite Mac ops branch with PNG-only commits |

Active ops board is **CATS CTC** (`HART_Master_CTC_hold.xml`), not Gate 1 `HART.xml` / `HART_le.xml`. See [`cats/docs/HART_DIGICON_SYSTEM.md`](../cats/docs/HART_DIGICON_SYSTEM.md).

## Remaining

- Measured roster speed profiles ([`projects/speedmatching.md`](projects/speedmatching.md))
- Dispatcher stub stations (EH, W-1/W-2, K, S-2…S-5): occupancy icons are on the panel; auto-dispatch still cannot start/stop there
- Node 13 occupancy walk-down (1301=118, 1304–1306=house, 1307=119)

## Manual launch (local Mac only)

```bash
./cats/scripts/launch_cats.sh
# default: cats/panels/HART_Master.xml (CTC); ABS: launch_hart_master_abs.sh
python3 cats/scripts/validate_cats_panel.py cats/panels/HART_Master_CTC_hold.xml
```

Do **not** use `CATS_LAUNCH_VIA=app`. Keep-alive LaunchAgent stays disabled.
Never run CATS CTC and the USS machine at the same time.

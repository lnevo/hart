# Layout Editor / Dispatcher System hoops

SoR for workarounds used so Dispatcher System can start and stop at HART stations. As of **2026-11-12** the live graph is **107 sections / 187 transits / 374 HEAD_AND_TAIL traininfo** (stock Stage 1; 49 masts) for **12 stations**: East Lead, K-1, K-2, McKees Rocks, McKeesport, Scale, Barn, EH-1–3, W-1, W-2. The mains, Brick-Plane and South Yard stopped being stations that day. Revisit the marked hacks; do not silently delete them.

Railroad English first, then the JMRI name. Operator desk: [`jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md`](../jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md). Live notes: [`STATUS.md`](STATUS.md) (Dispatcher System).

Tables: `jmri/layouts/hart/output/tables.xml`. Re-apply LE bindings with `jmri/layouts/hart/scripts/apply_le_cleanup.py`.

---

## Hidden virtual masts (`IF$vsm`)

CreateTransits needs a **mast at both ends of a station block**. Stub tracks and South Yard body tracks have no field LCOS heads there, so we added hidden virtual masts. They exist for the dispatcher graph only — not field signals.

Icons are `hidden="yes"` on **HART Railroad**. System names are `IF$vsm:basic:one-low($1001)` … `($1022)`.

| Station | Mast(s) | Where it sits |
|---------|---------|----------------|
| W-1 / W-2 | `Mast 4LA` / `Mast 4LB` | West-end bumpers `EB70` / `EB73` |
| McKees Rocks / McKeesport | `Mast 40RA` / `Mast 38RA` | East-end bumpers `EB71` / `EB72` |
| K-1 / K-2 boundary | `Mast 2035` / `Mast 2036` | Anchor `A48` at the apex of the drawn K loop (x=1837, y=276) |
| EH-1…EH-3 | `Mast 12L` / `Mast 10LA` / `Mast 10LB` | Engine House buffers `EB1` / `EB2` / `EB3` |
| S-1…S-4 west | `Mast 18L`, `20L`, `22L`, `26L` | Body/throat boundary anchors `A53`/`A46`/`A41`/`A15` |
| S-1…S-4 east | `Mast 18R`, `20R`, `22R`, `26R` | Body/throat boundary anchors `A61`/`A36`/`A39`/`A12` |
| S-R west / east | `Mast 16L` / `Mast 32L` | `A81` (new split east of TOR14) / `A37` |
| Scale / Switch 7 | `Mast 8LC` (`$1018`) | `A45` westbound; `T3` is `OS Switch 7`. `Mast 8RA` stays eastbound on `A45`, not TO117 A. |
| Barn / Switch 13 | `Mast 14R` (`$1019`) | Hidden virtual on TO1 B. Without it Discover jumps **8RA → 26L** through Barn and Stage 1 tries the reverse hop. |
| EH-1 / Switch 11 | `Mast 12R` (`$1020`) | Hidden virtual on TO11 B. Bumper `12L` is arrival-only; without this, EH outbound `get_first` picks **32L** and EH→S-1/S-4/S-R never builds. |
| EH-2 / Switch 9 | `Mast 10RA` (`$1021`) | Hidden virtual on TO10 C (EH-2). |
| EH-3 / Switch 9 | `Mast 10RB` (`$1022`) | Hidden virtual on TO10 B (EH-3). |
| Brick-Plane / Switch 1 | `Mast 2R` (`$1023`) | Hidden virtual on TOL3 C. Brick-Plane had no mast at either end, so it sat inside the 2L→8RA/8RB and 6LA/6LB→24RA sections: runs into it went past it and runs to East Main Ext / Main West reused its transits (added 2026-11-10). |
| Brick-Plane / Switch 5 | `Mast 6R` (`$1024`) | Hidden virtual on TOL42 A. Same fix, east end. |

Tables: `STUB_MASTS` and `YARD_BOUNDARY_MASTS` in `apply_le_cleanup.py`. Throat geometry: `apply_yard_throat_blocks.py`.

---

## END_BUMPER mast slots

A connect1-only `END_BUMPER` resolves a facing block in one slot only, set by which side of the bumper the track is on (`LayoutBlockManager.getFacingBlock`). These are JMRI's normal travel-direction slots, and its own dialog offers only that slot:

| End of railroad | Bumper slot used |
|-----------------|------------------|
| West (W-1/W-2, EH) | `westboundsignalmast` |
| East (McKees Rocks/McKeesport) | `eastboundsignalmast` |

Bindings are on `STUB_MASTS` in `apply_le_cleanup.py`. In any other slot, Discover and CATS SML report **No facing block found for destination mast**. Do not move them.

---

## Mid-block anchors vs throat blocks

Discover only sees a mast at a **block boundary**. Anchors `A53` / `A46` / `A41` / `A12` used to have both connections in the same South Yard body block, so a mast there was invisible. Turnout-leg binds were a temporary workaround.

Each S-R and S-1…S-4 body now has short **hidden throat blocks** (`Track S-1 West` / `Track S-1 East`, …) that **share the body occupancy sensor** (same pattern as McKees Rocks / OS Switch 39). Those anchors are true boundaries. Virtuals sit on the anchors (`YARD_BOUNDARY_MASTS`). Do not put the virtuals back on turnout legs.

CreateGraph treats a block as a station if `"stop"` appears **anywhere** in the comment (`if "stop" in comment.lower()`). Do **not** write “not a stop” on a throat — that substring matches and the throat becomes a MoveTo station. Use “not a station”.

---

## Shared occupancy

McKees Rocks is its own JMRI block but uses the same occupancy sensor as OS Switch 39 (`Block 1-4`). McKeesport shares `Block 1-3` with OS Switch 37. Stage 1 will ask **same sensor?** — answer **Yes**. That is expected.

This is the pattern the South Yard throats use. Stage 1 will ask **same sensor?** for each throat — answer **Yes**.

## CreateTransits / Jython landmines

- Do **not** `from __future__ import print_function` in `preference:jython/` scripts. JMRI’s shared Jython engine keeps that compiler flag. Stock `DispatcherSystem/Startup.py` still has Python-2 `print "closed Option"` (line 41); clicking **Run Dispatcher System** then SyntaxErrors.
- Python `except Exception` does **not** catch Java `JmriException`. Stage 1 / SML helpers that only catch Python `Exception` will hang or look idle after a Java failure.
- CreateTransits talks through **modal `JOptionPane`**. A hidden dialog (behind PanelPro, or on a headless/automation thread) freezes Stage 1. Look for a buried confirm before killing the session.
- `TransitCreationTool.addNamedBean` is **outside** the `try` in stock `CreateTransits.create_transit`. An unreachable pair kills Stage 1. If that happens, **fix `jmri/layouts/hart/output/tables.xml`** (mast bindings / block boundaries) so Discover builds legal hops. Do **not** wrap CreateTransits. **26L → 8RA** is opposite-facing; westbound Scale is 26L → 8LC → 6LA (or 26L → 8LB → 6LA).
- Stage 1 deletes and re-discovers SML and resets several things. Since 2026-11-12 `run_panelpro_stage1.sh` repairs them after every run: it re-adds the two manual Princess pairs (`Mast 36RA→Mast 40LA`, `Mast 36RB→Mast 38LA`, `restore_manual_sml_pairs.py`), sets HEAD_AND_TAIL detection (`fix_traininfo_detection.py`), re-binds station cluster icons (`reconcile_dispatcher_stations.py`), stores Digicon SML disabled, and puts labels and Stage 1 lamps back (`polish_hart_layout_editor.py`). `tools/check.sh` fails if any of those are out of step. A start block needs a mast at its rear for each leaving direction, or Stage 1 takes the first section holding the block by system-name sort (`CreateTransits.get_first_signal_mast`) and the choice flips when mast system names change (the 2026-11-10 Digicon renumbering flipped 84 East Lead and K-1 runs). Since 2026-11-12 East Lead and K-1 have hidden throats at A56 / A1 (`Track East Lead East`, `Track K-1 West`, same detectors) with hidden virtual rear masts 36L (westbound) and 40RB (eastbound); 36RB and 40LB stay on their switch legs. Folding the stub into the switch's OS block instead broke Discover for 36RB and 38LA/38LB, so keep the throat pattern.
- Stage 1 **Store** writes Layout Editor `BlockContentsIcon`s at **level 0** (behind the track). The Mac launcher and **`sync_hart_package.sh`** run `polish_hart_layout_editor.py --block-labels-only`; **`panel_status.py`** also lifts them at PanelPro boot. Audit fails if any label is not level 4.
- **PanelPro only.** Never run Stage 1 or Store tables from CATS. CATS virtuals (`IF$vsm:CATS1/CATS2`) and `IMDECODER_*` memories pollute `tables.xml` and fail to load in plain JMRI.

---

## South Yard as platforms (throats landed)

S-R and S-1…S-4 are a yard with many platforms: enter/leave via **Switch 15** or **East Lead**. Hidden throat blocks (`apply_yard_throat_blocks.py`) give each body a mast *beyond* the stop. Stock Stage 1 2026-09-01 produced **82 / 721 / 1530**. Do not put `104L`–`107L` back on turnout legs.

---

## Do not

- Patch, wrap, skip, or monkey-patch Dispatcher System / JMRI (`CreateTransits`, `CreateIcons`, `Startup.py`, `TransitCreationTool`). Stage 1 failures are panel data. Shared-sensor Yes on Stage 1 is a physical occupancy constraint, so a one-shot Mac launcher may auto-answer that confirm; changing `CreateTransits` is still not allowed.
- Dual-run CATS CTC and the USS machine, or start Dispatcher System from inside CATS.
- Store tables or panels from a CATS session.
- Put `Mast 18L`–`Mast 26L` back on turnout C/B legs. Bind them on the throat-boundary anchors.
- Move the END_BUMPER mast bindings.
- Command field turnouts / publish `track/cmd` from launch or “fix paint” scripts.

# Layout Editor / Dispatcher System hoops

SoR for workarounds used so Dispatcher System can start and stop at HART stations. As of **2026-09-01** the live graph is **103 sections / 746 transits / 1548 HEAD_AND_TAIL traininfo** (stock Stage 1; 45 masts). S-1…S-5 are arrival/departure stations (enter/leave via 103 or East Lead). Revisit the marked hacks; do not silently delete them.

Railroad English first, then the JMRI name. Operator desk: [`jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md`](../jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md). Live notes: [`STATUS.md`](STATUS.md) (Dispatcher System).

Writable tables: `tables/new_tables.xml`. Re-apply LE bindings with `jmri/layouts/hart/scripts/apply_le_cleanup.py`.

---

## Hidden virtual masts (`IF$vsm`)

CreateTransits needs a **mast at both ends of a station block**. Stub tracks and South Yard body tracks have no field LCOS heads there, so we added hidden virtual masts. They exist for the dispatcher graph only — not field signals.

Icons are `hidden="yes"` on **HART Railroad**. System names are `IF$vsm:AAR-1946:SL-1-low($1001)` … `($1022)`.

| Station | Mast(s) | Where it sits |
|---------|---------|----------------|
| W-1 / W-2 | `101LA` / `101LB` | West-end bumpers `EB70` / `EB73` |
| K-1 / K-2 | `115RA` / `114RA` | East-end bumpers `EB71` / `EB72` |
| EH-1…EH-3 | `118L` / `119LA` / `119LB` | Engine House buffers `EB1` / `EB2` / `EB3` |
| S-2…S-5 west | `104L`–`107L` | Body/throat boundary anchors `A53`/`A46`/`A41`/`A15` |
| S-2…S-5 east | `104R`–`107R` | Body/throat boundary anchors `A61`/`A36`/`A39`/`A12` |
| S-1 west / east | `103L` / `110L` | `A81` (new split east of TOR14) / `A37` |
| Scale / Switch 7 | `Mast 8LC` (`$1018`) | `A45` westbound; `T3` is `OS Switch 7`. `Mast 8RA` stays eastbound on `A45`, not TO117 A. |
| Barn / Switch 13 | `Mast 13R` (`$1019`) | Hidden virtual on TO1 B. Without it Discover jumps **8RA → 26L** through Barn and Stage 1 tries the reverse hop. |
| EH-1 / Switch 11 | `Mast 11L` (`$1020`) | Hidden virtual on TO11 B. Bumper `12L` is arrival-only; without this, EH outbound `get_first` picks **32L** and EH→S-1/S-4/S-R never builds. |
| EH-2 / Switch 9 | `Mast 9LA` (`$1021`) | Hidden virtual on TO10 C (EH-2). |
| EH-3 / Switch 9 | `Mast 9LB` (`$1022`) | Hidden virtual on TO10 B (EH-3). |

Tables: `STUB_MASTS` and `YARD_BOUNDARY_MASTS` in `apply_le_cleanup.py`. Throat geometry: `apply_yard_throat_blocks.py`.

---

## END_BUMPER facing-slot hack — **revisit later**

JMRI `getFacingBlock` on a connect1-only `END_BUMPER` looks up `connect2` (null) unless the mast is in the **far** slot. Geography is backwards on purpose:

| End of railroad | Bumper slot used |
|-----------------|------------------|
| West (W-1/W-2, EH) | `westboundsignalmast` |
| East (K-1/K-2) | `eastboundsignalmast` |

Same trick as the Engine House buffers. Comments live on `STUB_MASTS` in `apply_le_cleanup.py`. Without it, Discover and CATS SML report **No facing block found for destination mast**.

**Keep the hack until someone replaces it.** Do not “fix” the slots to match compass direction.

---

## Mid-block anchors vs throat blocks

Discover only sees a mast at a **block boundary**. Anchors `A53` / `A46` / `A41` / `A12` used to have both connections in the same South Yard body block, so a mast there was invisible. Turnout-leg binds were a temporary workaround.

Each S-1…S-5 body now has short **hidden throat blocks** (`S-2 West` / `S-2 East`, …) that **share the body occupancy sensor** (same pattern as K-1 / OS 115). Those anchors are true boundaries. Virtuals sit on the anchors (`YARD_BOUNDARY_MASTS`). Do not put the virtuals back on turnout legs.

CreateGraph treats a block as a station if `"stop"` appears **anywhere** in the comment (`if "stop" in comment.lower()`). Do **not** write “not a stop” on a throat — that substring matches and the throat becomes a MoveTo station. Use “not a station”.

---

## Shared occupancy

K-1 is its own JMRI block but uses the same occupancy sensor as OS 115 (`Block 1-4`). K-2 shares `Block 1-3` with OS 114. Stage 1 will ask **same sensor?** — answer **Yes**. That is expected.

This is the pattern the South Yard throats use. Stage 1 will ask **same sensor?** for each throat — answer **Yes**.

---

## Facing invert is stock — overlay removed 2026-09-01

Logix **IX:DSLX:1C1** (**Run Dispatcher**) runs stock `program:jython/DispatcherSystem/Startup.py`. The HART facing overlay (`hart_dispatcher_startup.py` / `patch_dispatcher_facing.py`) is gone; it did not fix polarity.

Stock `MoveTrain.set_train_direction` still inverts the facing dialog ([JMRI#15407](https://github.com/JMRI/JMRI/issues/15407)). If a through-station loco runs the wrong way, use **Modify Dispatcher System → Change Dir** (PDF “Change the Direction of the Train”). Do not re-add an overlay. Do not “fix” mast slots for this.

Stock `MoveTrain` inverts the facing dialog ([JMRI#14365](https://github.com/JMRI/JMRI/issues/14365), still in v5.16+). Stored `"reverse"` loads `*_rvs.xml` while the transit stays Forward. Release WiThrottle before dispatch.


## CreateTransits / Jython landmines

- Do **not** `from __future__ import print_function` in `preference:jython/` scripts. JMRI’s shared Jython engine keeps that compiler flag. Stock `DispatcherSystem/Startup.py` still has Python-2 `print "closed Option"` (line 41); clicking **Run Dispatcher System** then SyntaxErrors.
- Python `except Exception` does **not** catch Java `JmriException`. Stage 1 / SML helpers that only catch Python `Exception` will hang or look idle after a Java failure.
- CreateTransits talks through **modal `JOptionPane`**. A hidden dialog (behind PanelPro, or on a headless/automation thread) freezes Stage 1. Look for a buried confirm before killing the session.
- `TransitCreationTool.addNamedBean` is **outside** the `try` in stock `CreateTransits.create_transit`. An unreachable pair kills Stage 1. If that happens, **fix `tables/new_tables.xml`** (mast bindings / block boundaries) so Discover builds legal hops. Do **not** wrap CreateTransits. **26L → 8RA** is opposite-facing; westbound Scale is 26L → 8LC → 6LA (or 26L → 8LB → 6LA).
- Stage 1 deletes and re-discovers SML. Re-add the two manual Princess pairs (`113RA→115LA`, `113RB→114LA`) after every run. Then `fix_traininfo_detection.py` (HEAD_AND_TAIL) and `reconcile_dispatcher_stations.py`.
- Stage 1 **Store** writes Layout Editor `BlockContentsIcon`s at **level 0** (behind the track). The Mac launcher and **`sync_hart_package.sh`** run `polish_hart_layout_editor.py --block-labels-only`; **`sync_layout_button.py`** also lifts them at PanelPro boot. Audit fails if any label is not level 4.
- **PanelPro only.** Never run Stage 1 or Store tables from CATS. CATS virtuals (`IF$vsm:CATS1/CATS2`) and `IMDECODER_*` memories pollute `tables.xml` and fail to load in plain JMRI.

---

## South Yard as platforms (throats landed)

S-1…S-5 are a yard with many platforms: enter/leave via **103** or **East Lead**. Hidden throat blocks (`apply_yard_throat_blocks.py`) give each body a mast *beyond* the stop. Stock Stage 1 2026-09-01 produced **82 / 721 / 1530**. Do not put `104L`–`107L` back on turnout legs.

---

## Do not

- Patch, wrap, skip, or monkey-patch Dispatcher System / JMRI (`CreateTransits`, `CreateIcons`, `Startup.py`, `TransitCreationTool`). Stage 1 failures are panel data. See `.cursor/rules/dispatcher-stock-tables.mdc`.
- Dual-run CATS CTC and the USS machine, or start Dispatcher System from inside CATS.
- Store tables or panels from a CATS session.
- Put `104L`–`107L` back on turnout C/B legs. Bind them on the throat-boundary anchors.
- Remove the END_BUMPER far-slot bindings without a replacement.
- Command field turnouts / publish `track/cmd` from launch or “fix paint” scripts.

# Layout Editor / Dispatcher System hoops

SoR for workarounds used so Dispatcher System can start and stop at HART stations. As of **2026-08-22** the live graph is **91 sections / 688 transits / 1508 HEAD_AND_TAIL traininfo**. S-1…S-5 are arrival/departure stations (enter/leave via 103 or East Lead). Revisit the marked hacks; do not silently delete them.

Railroad English first, then the JMRI name. Operator desk: [`jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md`](../jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md). Live notes: [`STATUS.md`](STATUS.md) (Dispatcher System).

Writable tables: `tables/new_tables.xml`. Re-apply LE bindings with `jmri/layouts/hart/scripts/apply_le_cleanup.py`.

---

## Hidden virtual masts (`IF$vsm`)

CreateTransits needs a **mast at both ends of a station block**. Stub tracks and South Yard body tracks have no field LCOS heads there, so we added hidden virtual masts. They exist for the dispatcher graph only — not field signals.

Icons are `hidden="yes"` on **HART Railroad**. System names are `IF$vsm:AAR-1946:SL-1-low($1001)` … `($1017)`.

| Station | Mast(s) | Where it sits |
|---------|---------|----------------|
| W-1 / W-2 | `101LA` / `101LB` | West-end bumpers `EB70` / `EB73` |
| K-1 / K-2 | `115RA` / `114RA` | East-end bumpers `EB71` / `EB72` |
| EH-1…EH-3 | `118L` / `119LA` / `119LB` | Engine House buffers `EB1` / `EB2` / `EB3` |
| S-2…S-5 west | `104L`–`107L` | Body/throat boundary anchors `A53`/`A46`/`A41`/`A15` |
| S-2…S-5 east | `104R`–`107R` | Body/throat boundary anchors `A61`/`A36`/`A39`/`A12` |
| S-1 west / east | `103L` / `110L` | `A81` (new split east of TOR14) / `A37` |

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

## `patch_dispatcher_facing.py` — **revisit later**

Loaded by `jmri/layouts/hart/scripts/hart_dispatcher_startup.py` into the same Jython namespace as Dispatcher System (stock Startup.py cannot be patched from a second interpreter).

What the patch does today:

- Facing dialog: stock `MoveTrain` maps “forward” to train_direction `reverse` (and the reverse), so a through-station registration loads `*_rvs.xml` and the loco backs while the transit stays Forward.
- Null-safe Operations speed-factor cells (empty / `-1` → 100%).
- Route-clear and allocation highlight only the requested start→destination subsection, not the whole shared transit.

Related, not the same file: **hands off the phone throttle**. JMRI shares one throttle per address. `AutoActiveTrain` sets the direction bit once at dispatch start. A WiThrottle press (or re-acquire) flips that bit; the next speed command runs the train the wrong way. Release the phone before dispatch; terminate and re-dispatch instead of nudging.

**Revisit the patch.** It is a compatibility overlay, not a JMRI fix.

---

## CreateTransits / Jython landmines

- Python `except Exception` does **not** catch Java `JmriException`. Stage 1 / SML helpers that only catch Python `Exception` will hang or look idle after a Java failure.
- CreateTransits talks through **modal `JOptionPane`**. A hidden dialog (behind PanelPro, or on a headless/automation thread) freezes Stage 1. Look for a buried confirm before killing the session.
- Stage 1 deletes and re-discovers SML. Re-add the two manual Princess pairs (`113RA→115LA`, `113RB→114LA`) after every run. Then `fix_traininfo_detection.py` (HEAD_AND_TAIL) and `reconcile_dispatcher_stations.py`.
- **PanelPro only.** Never run Stage 1 or Store tables from CATS. CATS virtuals (`IF$vsm:CATS1/CATS2`) and `IMDECODER_*` memories pollute `tables.xml` and fail to load in plain JMRI.

---

## South Yard as platforms (throats landed)

S-1…S-5 are a yard with many platforms: enter/leave via **103** or **East Lead**. Hidden throat blocks (`apply_yard_throat_blocks.py`) give each body a mast *beyond* the stop. Stage 1 re-run 2026-08-22 produced **91 / 688 / 1508** with inbound transits to every body track. Do not put `104L`–`107L` back on turnout legs.

---

## Do not

- Dual-run CATS CTC and the USS machine, or start Dispatcher System from inside CATS.
- Store tables or panels from a CATS session.
- Put `104L`–`107L` back on turnout C/B legs. Bind them on the throat-boundary anchors.
- Remove the END_BUMPER far-slot bindings or the facing patch without a replacement.
- Command field turnouts / publish `track/cmd` from launch or “fix paint” scripts.

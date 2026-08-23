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

## `patch_dispatcher_facing.py` — overlay, **not a root fix** — **revisit later**

This is a HART monkey-patch of Bill Fitch’s Dispatcher System. It does **not** change `/Applications/JMRI/jython/DispatcherSystem/MoveTrain.py`. Logix **IX:DSLX:1C1** (**Run Dispatcher**) must run `preference:jython/hart_dispatcher_startup.py`, not stock `program:jython/DispatcherSystem/Startup.py`. The wrapper loads stock Startup + RunDispatchMaster into **one** Jython namespace, then applies `preference:jython/patch_dispatcher_facing.py` there (a second script eval cannot patch classes loaded in another globals dict). A daemon thread re-applies if Dispatcher System is reloaded.

### Symptom

Register a through-station train, answer **forward** (facing the highlighted neighbor), dispatch. The allocated transit stays **Forward**, but the loco **backs**. Traininfo `*_rvs.xml` was loaded instead of `*_fwd.xml`.

### Root cause (stock)

`MoveTrain.set_train_direction` asks “What way is train facing towards highlighted block?” then **inverts** the answer:

```
click "forward"  →  train["direction"] = "reverse"
click "reverse"  →  train["direction"] = "forward"
```

That invert is **not** a leftover we invented. Before 2025-08, `in_siding` was hardcoded `False`, so the through-station **else** already inverted; [JMRI#14365](https://github.com/JMRI/JMRI/issues/14365) (`b0b1627`, 2025-08-13) flattened that to always invert and described it as *store direction last moved, instead of the direction to move next*. The same invert is still in **v5.16**, **v5.17.2**, and `master` `MoveTrain.py` (checked 2026-08-22). HART is on **5.15.5** (Mac) / **5.15.4plus** (Pi). Upgrading JMRI will not remove it.

`createandshowGUI.save_action` and `MyTableModel.populate_existing` invert **again** so the Setup Train table shows what you clicked while storage holds the opposite.

Dispatcher then picks traininfo from the **stored** direction. Stage 1 writes two files per graph edge, same transit:

| File | `runInReverse` |
|------|----------------|
| `*_fwd.xml` | no |
| `*_rvs.xml` | yes |

Stored `"reverse"` → `*_rvs.xml` → throttle direction bit reverse, while the transit section list is still Forward. On HART that made the engine back along a forward route — which is why we overlay. That is **Dispatcher System (jython)**, not Java Dispatcher, and not a HART panel / mast / throat problem. Layout Editor facing slots are a **different** issue (END_BUMPER section above).

Filed as a question, not a silent revert of 14365: [JMRI#15407](https://github.com/JMRI/JMRI/issues/15407). Patch [JMRI#15408](https://github.com/JMRI/JMRI/pull/15408) was **closed 2026-08-22** pending more live testing. Keep the HART overlay. Dispatcher System has a small user base compared with Java Dispatcher; people who see a loco back often hit the other dialog button or blame decoder polarity.

### What the overlay does

`NewTrainMaster.set_train_direction` returns `[result, result]` — dialog **forward** stays stored **forward**. `save_action` and `populate_existing` no longer swap. Same file also null-safes Operations speed-factor cells (`""` / `-1` → 100%) and limits route-clear / allocation paint to the TrainInfo start→destination **subsection** (stock scans the whole shared transit).

### First dispatch after Setup Train (HART overlay, 2026-08-22)

This is **not** a balloon / hairpin wiring bug. McKees Rocks really has two neighbors (McKeesport and OS 115). The allocated transit McKees Rocks → West Main Ext via OS 115 is the short plant move.

Stock Dispatcher System does **two** inverts that cancel when you leave toward the highlighted neighbor:

1. Facing dialog: click **forward** → store `"reverse"` (JMRI#14365).
2. First `set_direction`: registration borrowed an incoming graph edge whose penultimate block **is** that highlight. Leaving toward it looks like a U-turn (`previous_block == next_block`), so it flips storage back to `"forward"` and loads `*_fwd.xml`.

HART’s overlay removed (1) so the click matches storage. (2) still ran. Net: the desk showed **forward**, allocated Via OS 115, then loaded `*_rvs.xml`. DCC reverse with the loco facing OS 115 is McKeesport — the next balloon block.

The overlay now keeps registered facing for that **first** move (`hart_honor_facing`). After the hop succeeds, stock U-turn logic is left alone for later true reversals. No Layout Editor or transit change; this is the rest of the HART overlay we already owned. Do not “fix” A48 / Brick to stop the layout being a loop.

### Why this is still a hack

We compensate at runtime instead of deleting the invert in stock `MoveTrain.py`. A JMRI update that rewrites those methods can silently restore the swap. The overlay is not a JMRI contribution and is not covered by Dispatcher System’s own tests.

**If we revisit:** [JMRI#15407](https://github.com/JMRI/JMRI/issues/15407) is the question to Bill. Do not reopen [JMRI#15408](https://github.com/JMRI/JMRI/pull/15408) until first-registration polarity is proven on more than one station pair. Do not drop the overlay. For HART, first dispatch needs stored direction to mean **throttle polarity for this move**.

### Not this patch: phone throttle

JMRI allows **one throttle per DCC address**. `AutoActiveTrain` sets the direction bit at dispatch start. A WiThrottle press (or re-acquire) flips that bit; the next speed command runs the wrong way. Release the phone before dispatch; terminate and re-dispatch instead of nudging. That is JMRI throttle ownership, not the facing dialog.

---

## CreateTransits / Jython landmines

- Do **not** `from __future__ import print_function` in `preference:jython/` scripts. JMRI’s shared Jython engine keeps that compiler flag. Stock `DispatcherSystem/Startup.py` still has Python-2 `print "closed Option"` (line 41); clicking **Run Dispatcher System** then SyntaxErrors. `hart_dispatcher_startup.py` compiles stock files with `dont_inherit=True`.
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
- Remove the END_BUMPER far-slot bindings or the facing overlay without a replacement (the overlay only undoes stock `MoveTrain`’s invert).
- Command field turnouts / publish `track/cmd` from launch or “fix paint” scripts.

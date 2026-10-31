# HART Railroad — Neville Island Helix Handoff ADDENDUM (2026-09-30)

**Read this together with:**
1. `helix_construction_plan_FINAL_31p75_18p75_2026-09-23.pdf` (fabrication source of truth)
2. `HART_Neville_Helix_Agent_Handoff_FINAL_31p75_18p75_2026-09-23.md` (design rationale)
3. This file — **field-verified as-built facts, STL fixture inventory, and shop-process detail generated after the FINAL handoff was written.** The FINAL handoff's entry-easement numbers (12 in straight) are now stale; this addendum documents what has actually changed and what is still open.

---

## 0. Read this first — three different "straight length" numbers exist

Do not conflate these:

| Value | What it is | Status |
|---|---|---|
| **12 in** | Original design assumption | Superseded — benchwork seam wouldn't allow it |
| **6 in** | Revised design target; what is CURRENTLY written into PDF pages 2/3/8 | **Stale** — superseded by actual field cut, PDF not yet updated |
| **5-3/8 in (5.375 in)** | Actual, physically-cut, field-measured straight — **confirmed uniform on both inner and outer tracks** | **Current / authoritative.** Used for the current riser STL offset. NOT yet reflected in the PDF. |

**Open action:** the PDF's Page 2/3/8 entry-easement numbers (6.000 in tangent, 0.631 in rise to 6:00, -14.369 in railhead, etc.) need to be regenerated using 5.375 in before the document is trustworthy again. The general recalculation method is below (§2) so this can be redone for any length without re-deriving from scratch.

---

## 1. As-built entry status — what is physically true on the bench right now

- Curve start (cookie-cut boundary) is at the **4:30** clock position, on the 26 in roadbed radius.
- The tongue was cut in stages; the **final, confirmed measurement is 5-3/8 in of straight remaining, the same length on both the inner and outer track** (this superseded an earlier working assumption of 10 in inner / 12 in outer taken from a non-square cut line).
- **Post 1 (the first new-helix bracket / start of the structural datum) is already physically advanced past nominal 6:00** — this is a *built fact*, not a proposal. It was located by a real field measurement of the straight-line chord from 6:00 on the 26 in radius. **Field-corrected 2026-09-30:** the cut mark was re-measured and sits **3/16 in shy of the original 10 in chord → actual chord = 9-13/16 in (9.8125 in)**, which resolves to:
  `sin(θ/2) = 9.8125 / (2×26) = 0.18870 → θ ≈ 21.75°`  (arc length along the 26 in radius ≈ 9.872 in)
  So **Post 1 sits at 6:00 + 21.75°** — not the 22.2° previously recorded from the nominal 10 in chord, and not the earlier-discussed 6:23.4 (11.7°) figure, which was a design-stage proposal that was never built (see §2 history below — it's now moot).

### Current deck-height chain (benchwork datum, -15.000 in baseline), using the final 5.375 in straight:
```
GRADE = 0.02176   (29.25" planning-radius grade, unchanged)

rise_straight        = 5.375 × 0.02176         = 0.117 in
deck @ nominal 6:00  = -15.000 + 0.117 + 0.500  = -14.383 in
deck @ Post 1 (+21.75°, fixed +0.242 in advance) = -14.141 in
deck @ end of last curved helix section (+14.333 in for the 1290° sweep) = +0.192 in
```
This +0.192 in figure is the railhead-normalized elevation at the top of the curved helix given everything that's actually been cut and built to date. It has **not** been re-run through the exit-straight table in the PDF (which still uses the stale 6 in-straight numbers, giving +0.420 in there) — that update is still open.

### Where the "0.242 in" constant comes from
It is the extra rise picked up at the fixed 4 in/360° pitch across Post 1's 21.75° advance past nominal 6:00: `21.754° × (4/360) = 0.242 in`. It is now a fixed constant tied to Post 1's already-built location, independent of the straight length.

*(Superseded: the previous value was 0.247 in, from a 22.2° advance derived from the nominal 10 in chord. The corrected 9-13/16 in chord lowers Post 1 and everything downstream by ~0.005 in.)*

---

## 2. Entry easement recalculation — generalized method + history (so this never needs re-deriving from scratch)

### General formula (works for any straight length `L`, any post advance angle `θ_adv` past nominal 6:00)
```
rise_to_nominal_6  = L × GRADE + 0.500                (GRADE = 0.02176 @ 29.25" planning radius)
deck_at_nominal_6  = -15.000 + rise_to_nominal_6
advance_rise       = θ_adv × (4/360)
deck_at_Post1      = deck_at_nominal_6 + advance_rise
deck_at_helix_top  = deck_at_Post1 + 14.333            (fixed rise of the 1290° regular sweep)
```
The **0.500 in** term (45° curve's rise) and the **14.333 in** term (1290° sweep) are both locked by the fixed 4 in/360° pitch and cannot be changed without touching the pitch itself (which is locked design-wide).

### History / dead end — do not repeat this
An earlier "Option C" idea proposed extending the eased (pre-bracket-grid) zone ~11.7° past nominal 6:00 to recover a rise deficit caused by the shortened straight, while claiming the *fixed 45°-interval bracket grid* downstream would still land on the *original* (12 in-straight) absolute heights. **This does not work as originally framed**: because rise vs. angle is linear at fixed pitch, recovering the deficit at one point does not "stick" — every post after it is low by the same fixed amount, i.e. Option C as first described is mathematically identical to just accepting a uniform height shift (Option A). This was walked back explicitly.

What **does** work, and is what actually got built: physically **relocating where Post 1 itself sits** (not just easing the transition zone) by a real angular advance. Because deck height is a linear function of angle at fixed pitch, shifting the post grid's own starting angle by `Δθ` shifts every subsequent post's height by the same constant, which genuinely reproduces an arbitrary target height at Post 1 and keeps that match at every post after it. That's the mechanism behind the as-built 21.75° advance in §1 — it's a real fix, not the same dead end as the original "Option C" framing (the difference: physically moving the post locations, vs. only extending an eased zone while keeping the grid pinned to nominal 6:00).

**Caution for a future agent:** advancing the post grid further than necessary is always safe (just a longer unsupported span before Post 1); *not* advancing it far enough is not recoverable once built (the tongue can only be trimmed shorter, never extended). This asymmetry drove the decision to over-advance rather than cut it close.

---

## 3. Exit-side status — still open

- The exit-side rise numbers currently in the PDF (Page 3: end-of-1290° = -0.036 in below target, end of 20-15/16 in exit straight if run at full grade = +0.420 in / +0.550 in relative) were computed **using the 6 in entry-straight figure**, not the final 5.375 in. They need to be recomputed once the entry numbers are reconciled (§0).
- There is **no vertical-clearance reason to delay easing the exit grade** — the loop below is fixed (not climbing), so clearance can only stay equal or grow the further along the exit straight you go; easing sooner never reduces clearance.
- **Still unresolved / needs field input:** whether the exit straight's plan-view direction actually keeps it over the lower loop's footprint (a horizontal question, not a height one) was never answered — the PDF only specifies the exit straight's *length* (20-15/16 in), not its compass direction relative to the spiral center. A future agent cannot derive this from existing numbers; it needs to be read off the actual layout, the same way "clear the loop below" was flagged as field-verified rather than pre-computed in the original plan (PDF page 6/8, step 11).

---

## 4. Diagonal bracing — now in the PDF (Page 12), not yet in the FINAL.md

This is fully documented in the PDF's Page 12 (added this session) but the FINAL handoff .md doesn't mention it at all. Key facts, exactly as printed there:

- **Braced bays (4 of 8):** A-B, C-D, E-F, G-H. **Open bays:** B-C, D-E, F-G, H-A.
- Each braced bay = **two half-height diagonals**, split at the middle ring (herringbone — upper/lower half-braces lean opposite directions).
- Stock: nominal 1x3 (actual 0.750 × 2.500 in), same as frame ties.
- **8 pieces total** (4 bays × 2 half-braces). Cut length **20.606 in (20-5/8 in)** point-to-point on centerline. Rise/run: 9.375 in half-height rise / 18.349 in post-to-post run. **Angle: 27° from horizontal, both ends.**
- Blanks: cut ~22 in oversize, dry-fit first piece, trim to fit, then batch-cut the rest.
- Lumber: 2 additional 12 ft 1x3 boards (beyond tie-ring stock).
- Fastening: 2 in coarse-thread star-drive (T-25) screws, 2 per end per half-brace = **32 screws total**. Predrill angled ends; glue + screws.
- Optional alternative documented (not required): solid plywood shear panel per bay instead of a stick diagonal, split at the middle ring the same way — more stiffness, blocks reach-through.

### Shop process — cutting the compound angle on a non-compound chop saw
This diagonal cut is genuinely compound: a **twist/miter component** (~22.5°-ish, same family as the tie's mirrored end cuts, from the post-to-post rotation) plus a **slope/bevel component** (~27°, from the brace's rise) applied simultaneously at each end. A basic chop saw only gives the miter function (rotate the fence, board flat); it cannot tilt the blade for the bevel half.

Process to fake the bevel on a non-tilting saw:
1. Set the saw's miter angle to the twist component.
2. Build a simple wedge/cradle that props the board up at the slope angle; clamp the board onto it so it sits tilted on the table instead of flat.
3. Cut through in one pass — tilted board + miter angle together give the combined compound face.
4. Repeat with a mirror-image wedge for the other end (opposite sense).

Given how light this connection's actual load is, two legitimate shortcuts were also offered and are acceptable if the wedge jig isn't worth building for 8 small pieces:
- **Miter only, skip the tilt** — leaves a small cosmetic gap, fill with glue or knock down with a rasp.
- **Square-cut ends entirely**, land the diagonal against a small mounting block/cleat screwed to the post/ring instead of trying to get the diagonal's own end flush.

---

## 5. STL fixture inventory (`/Users/lnevo/Downloads/stl/`)

### Current / authoritative

**`entry_wedge_riser_inside.stl`** and **`entry_wedge_riser_outside.stl`** — the entry tongue transition risers. Geometry (verified directly from the mesh, not from memory):
- Footprint: 1 in (X, radial) × 2.25 in (Y, tangential/length).
- **Low foot**: Z = 0 to 0.375 in (9.525 mm) — sits under the un-lifted original benchwork plywood.
- Thin connecting wall: 0.25 in (6.35 mm) long, full height.
- **Step offset (the number that matters): 0.864 in (21.94 mm) as currently baked into the STLs** — identical on BOTH inside and outside files, because both tracks share the same 5-3/8 in as-built straight. Formula baked in: `OFFSET_IN = L_STRAIGHT × GRADE + 0.500 + 0.247` = `5.375×0.02176 + 0.500 + 0.247` = **0.864 in**.
  - **⚠ Corrected value after the 2026-09-30 chord re-measure (9-13/16 in → 21.75° → 0.242 in advance): `5.375×0.02176 + 0.500 + 0.242` = 0.859 in (21.81 mm).** The existing STLs are ~0.005 in (0.13 mm) high relative to this — below practical print/cork tolerance, but the files have **not** been regenerated yet. (This is the same "rise to Post 1" quantity derived in §1/§2 — the riser lifts the cut end of the tongue by exactly the rise needed to reach Post 1's grade-correct height, referenced from the original flat -15.000 in baseline.)
- **High foot**, same 0.375 in thickness, with its top face sloped across its length at GRADE = 0.02176 (does not just sit flat on the corner).
- Countersunk holes, **on the BOTTOM face of each foot** (screw driven up from below): shaft 0.156 in, head 0.340 in, **110° included angle**. Screw sizing: **2 in screw on the raised/thicker (high-foot) side, 1-1/4 in screw on the original benchwork-height (low-foot) side**, both assumed #6.
- Engraved (recessed, 1 mm deep) identifying letter on **Face H** (the step wall, facing the high-foot side): **`entry_wedge_riser_inside.stl` = "R"**, **`entry_wedge_riser_outside.stl` = "L"**. Confirmed correctly mirrored/oriented via a straight-on render.
- Since the offset is now numerically identical for both parts, **the only geometric difference between the two files is the engraved letter and its mirroring** — worth knowing so a future agent doesn't assume there's a hidden dimensional difference.

**`cork_to_plywood_transition_shim.stl`** — separate fixed-offset shim for the 6 mm/0.236 in cork-to-bare-plywood step at the 6:00 seam. Footprint 2 in × 3.5 in, 2 countersunk holes per foot at Y = 0.75 in / 2.75 in. Rebuilt natively in mm (see §7 units lesson).

**`bracket_pocket_template.stl`** — router template for the 4x4 steel bracket pocket (3/32 in deep pocket per PDF §9). Not revisited this session; still valid against the PDF's existing bracket spec.

### Superseded — do not use, recommend deleting to avoid confusion
- `entry_transition_shim.stl`, `entry_transition_shim_inside.stl`, `entry_transition_shim_outside.stl`, `entry_wedge_riser.stl` (no suffix). These are early-stage prototypes from before the "floating bodies" fix and before the offset was unified at 5-3/8 in / 0.864 in (now 0.859 in after the chord correction) — direct inspection shows they contain stale, much smaller (~0.05 in) offset values with no relation to the current design. Keep only the two `entry_wedge_riser_inside/outside.stl` files above.

---

## 6. Router baseplate → Sigerio circle-jig adapter plate

Not a track/helix geometry item, but a **shop tool needed to cut the curved 26–31.75 in radius roadbed blanks** (PDF §6, P1–P15) — relevant to this build's fabrication, not documented anywhere else.

**Problem:** the AVID POWER MW104 router's stock baseplate hole pattern doesn't match the Sigerio circle-cutting jig's mounting pattern. An adapter plate is being iterated as a **test plate** (explicitly not final — built to physically check alignment before committing to a finished part).

**Current test-plate spec** (`router_sigerio_test_plate.stl`, watertight, single body):
- Plate: 6 in diameter, 8.32 mm thick (thickened specifically so the countersink has room to form — a thinner plate let the countersink punch through and look like a plain hole; lesson generalized in §7).
- Router-side holes: 4, countersunk (90° included angle, flat-head profile) from the bottom, positioned so the diagonal between opposite holes is **exactly 3.000 in outer-edge-to-outer-edge** (radius solved precisely for this spec, not approximated from an assumed square).
- Sigerio-side holes: 4, **plain/open, no countersink** (explicit instruction — countersinking may be wanted on the final part but not this test plate), at **4.5 in diameter** (2.25 in radius), 0°/90°/180°/270°.

**Open / unconfirmed — needs physical test-fit before finalizing:**
- Router screw hole diameter is an assumed **0.22 in estimate** — recommend verifying with calipers or a drill-bit gauge against the actual router screws.
- Sigerio hole diameter (0.25 in) and radius (2.25 in / 4.5 in diameter) are working estimates from a "4-5 in diameter" range the user gave, not measured directly off the jig — confirm against the actual Sigerio disc's slot pattern.
- Center bore (1.75 in) is an unconfirmed estimate, not yet checked against the router's actual collet/base opening.

---

## 7. Process lessons worth preserving (apply these before repeating past mistakes)

- **STL files carry no unit metadata.** Author coordinates directly in millimeters — inch-valued coordinates get silently misread as mm by slicers ("too small, convert to mm?") even though the file prints correctly.
- **`mesh.is_watertight` is not sufficient** to confirm a single valid part. Also check `len(mesh.split(only_watertight=False))` — floating, individually-watertight bodies can still pass a naive watertight check while being physically disconnected.
- **Countersink depth must be checked against material thickness before trusting a render.** `depth = (head_dia/2) / tan(angle/2)`; if that exceeds the part thickness at that point, the cone punches all the way through and just looks like a plain hole, not a countersink — this happened twice.
- **Countersink orientation depends on which face the screw is driven from** — model it explicitly per-face (cone at the entry face, shaft continuing through), don't assume top-seating by default.
- **Visual cross-section verification is required, not optional, before calling hole/countersink geometry correct** — render `mesh.section(plane_origin, plane_normal).to_2D()` through the *actual* hole center (holes at 45°/135°/etc. need a plane through that coordinate, not an axis-aligned default), and confirm the profile shows a real taper-to-shaft transition before reporting success.
- **PDF redaction rects must be tightly bounded.** Padded/oversized redaction rects in tightly-leaded paragraphs will silently delete adjacent lines of text, not just the intended target — verify with `page.get_text()` substring checks after any redaction.

---

## 8. Open items checklist for the next agent

1. **Reconcile the PDF's entry-easement pages (2, 3, 8)** from the stale 6 in straight to the confirmed 5.375 in straight + the as-built 21.75° Post 1 advance (9-13/16 in chord, corrected 2026-09-30), using the formula in §2. This also requires re-running the exit-straight table in §3.
2. **Recompute the exit-side numbers** (currently based on the stale 6 in figure) once #1 is done.
3. **Resolve the exit-straight plan-view direction question** (§3) — needs a field answer, not a calculation, to determine when/whether it's over the lower loop.
4. **Add diagonal bracing (§4) to the FINAL handoff .md** — it currently only exists in the PDF (Page 12); the .md's "Locked" and "Common traps" sections don't mention it at all.
5. **Decide whether to regenerate `entry_wedge_riser_inside/outside.stl` at 0.859 in** (currently 0.864 in; 0.005 in / 0.13 mm difference from the chord correction).
5a. **Delete or clearly quarantine the superseded riser STL prototypes** listed in §5 before they're accidentally printed.
6. **Verify the router/Sigerio adapter plate's estimated hole sizes** (§6) against physical calipers/gauges and the real jig before finalizing (this is explicitly a test plate, not a final part).
7. Update the FINAL handoff's §16 "Recommended context package" to include this addendum as a third file to hand to any future agent.

---

> **2026-10-01:** see `HART_Neville_Helix_Agent_Handoff_ADDENDUM_2026-10-01.md`. The bracket grid is now laid out relative to the entry butt joint (helix structure rotated to suit), which supersedes the "Post 1 at 6:00 + 21.75°" reference above for bracket placement. That file also covers the router template/depth-block STL family, bit selection and roadbed cutting process.

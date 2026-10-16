# HART Railroad — Neville Island Helix Agent Handoff

**Purpose:** Give a new agent enough context to continue helix engineering, sourcing, troubleshooting, or documentation without reconstructing the full prior conversation.

**Primary fabrication source of truth:** `helix_construction_plan_FINAL_31p75_18p75_2026-09-23.pdf` (supersedes `..._ENTRY_FLIPPED_CLEAN_2026-09-23.pdf` and `helix_plan_final.pdf`, both archived under `superseded/`; footer revision tags are now unified to "Locked Flat-Frame Rev. 2026-09-23" on every page, and page 1 carries an added DATUM CAUTION note distinguishing the Benchwork datum from the Structural datum.)

Use this handoff for **design rationale, alternatives, calculations, historical decisions, commercial references, and failure modes**. Use the PDF for the current build sequence, dimensions, cut sheets, support elevations, and construction details.

> **Read `HART_Neville_Helix_BUILD_STATUS.md` before trusting anything below.** It is the single living status file: as-built facts (5-3/8 in entry straight, bracket grid from the entry butt joint, 0.72 in plywood, height stack, 0.26/0.46 laps), every fixture STL and script, and open items. It overrides this file where they conflict. The old dated addenda are archived in `superseded/addenda_2026-09-30_to_10-13/`.

---

## 1. Agent operating rules

1. **Do not silently change locked geometry.** The chosen helix pitch is 4.000 in railhead-to-railhead per turn. Track centers are 28.000 and 30.500 in. Roadbed is 26.000–31.750 in radius.
2. **Keep benchwork, track-stack, railhead, and structural datums separate.** The existing approach **plywood/benchwork top** is at -15.000 in. Railhead is higher by the 6 mm cork plus the full track assembly height. The structural helix datum remains the **underside of the new helix plywood at 6:00 = 0.000 in** for relative support/bracket work.
3. **The PDF is authoritative for fabrication.** This file supplements it; it does not replace the cut sheets.
4. **Verify geometry before recommending a new frame or support scheme.** Several earlier iterations failed because post orientation, miter geometry, or rail edge definitions were mixed together.
5. **Distinguish measured layout geometry from theoretical helix geometry.** The actual route includes a 12 in tangent, a 45 deg cookie-cut approach, the new helix, a partial final arc, a 20-15/16 in exit straight, and a downstream curve under D01.
6. **Do not revive obsolete frame dimensions.** Earlier 19-1/2 in on-edge and 18-1/2 in on-edge frame concepts were superseded by the current **flat 1x3 / 18.000 in outside-edge** frame.
7. **Do not infer current commercial availability from this file.** Commercial products/specs below are research references from the design process; re-verify manufacturer data before purchasing.

---

## 2. Current locked build — compact summary

### Track and roadbed
- Scale: HO.
- Track: Atlas Code 83. **0.083 in is rail height only**, not railhead-above-plywood. For absolute elevations and overhead clearance use the actual bottom-of-tie-to-railhead height of the installed track. A published reference gives Atlas Code 83 flex at about **0.160 in overall**; verify the actual stock with calipers before final clearance sign-off.
- Inner track center radius: **28.000 in**.
- Outer track center radius: **30.500 in**.
- Roadbed inside radius: **26.000 in**.
- Roadbed outside radius: **31.750 in**.
- Roadbed width: **5.750 in**.
- Roadbed overall diameter: **63.5 in**.
- Helix roadbed material: **3/4 in plywood**.
- **No cork in the overlapping helix.**
- Existing approach remains **3/4 in plywood + 6 mm / 0.236 in cork**.

### Pitch and support rhythm
- Pitch: **4.000 in / 360 deg**.
- Rise per 45 deg: **0.500 in**.
- Eight support stations at **45 deg** intervals.
- Final roadbed path uses an extra loop compared with the earlier shorter concept.

### Final route geometry
- Existing/cookie-cut entry: **12.000 in straight + 45 deg curve**.
- Originally measured curvature: **975 deg** total from the beginning of the curved approach.
- Added one full loop: **+360 deg**.
- Final curved path from start of curved approach: **1335 deg TOTAL**.
- Angle breakdown: **45 deg existing approach (4:30 -> 6:00) + 1260 deg regular helix/support grid (6:00 -> 12:00 after 3.5 turns) + 30 deg final partial arc = 1335 deg**.
- Therefore the new bare-plywood/bracket-supported helix **after 6:00 is 1290 deg = 1260 + 30**.
- The final 30 deg is already included in both 1290 deg and 1335 deg; do not add it again.
- Exit straight: **20-15/16 in = 20.9375 in**.
- Exit straight then feeds a curve under D01; that region is the vertical-easing / cork-restoration zone.

---

## 3. Grade math and clearance math

### Grades at fixed 4 in pitch
Use:

`grade = rise / circumference = 4 / (2*pi*radius)`

- 28 in inner track: **2.274%**.
- 30.5 in outer track: **2.087%**.
- 29.25 in planning radius: **2.176%**.

The two tracks rise the same **4 in per revolution**, therefore the smaller radius has the steeper percentage grade.

### Normal helix clearance
**Do not use 0.083 in as total track height.** Code 83 specifies the rail alone. Let `T` = actual bottom-of-tie-to-railhead height of the installed track. Then:

`clearance = 4.000 - 0.750 - T`

Using a nominal Atlas Code 83 flex-track overall height of about **0.160 in** gives:

`4.000 - 0.750 - 0.160 = 3.090 in`

This is lower-railhead to underside of the next plywood deck. **Measure the actual track assembly with calipers and substitute that value before final clearance sign-off.**

### Material comparison at 4 in pitch
Useful historical comparison table:

| Upper deck material | Cork? | Railhead-to-underside clearance |
|---|---:|---:|
| 1/2 in plywood | no | **~3.340 in** |
| 5/8 in plywood | no | **~3.215 in** |
| 3/4 in plywood | no | **~3.090 in** |
| 1/2 in plywood | 6 mm | **~3.104 in** |
| 3/4 in plywood | 6 mm | **~2.854 in** |
| ~0.197 in Gatorboard reference | no | **~3.643 in** |

### Double-stack planning context
- Prototype modern double-stack planning height discussed: about **20 ft 2 in**, approximately **2.78 in in HO**.
- Practical planning view used during design:
  - ~3.00 in = minimum-ish.
  - ~3.125–3.25 in = desirable.
- With nominal ~0.160 in overall track height, the selected build is about **3.090 in** lower-railhead-to-plywood-underside clearance. This still exceeds the ~2.78 in HO double-stack planning height by about 0.31 in, but final sign-off should use the measured track height.

---

## 4. Entry / easement / cork-to-plywood handoff

This is one of the most important design choices.

### Why the entry is special
The existing peninsula/tabletop is already **3/4 in plywood** with track, cork, wiring, and joists. A bracket cannot simply be placed below the original zero-height plywood. The entry therefore uses the existing roadbed as a **cookie-cut rising tongue** until the new helix clears the tabletop.

### Locked entry method
- Cookie-cut the existing **12 in straight plus the following 45 deg curved approach**.
- Keep the existing track and **full 6 mm / 0.236 in cork** intact on that tongue.
- Support the tongue with adjustable risers.
- At the **6:00 seam**, the new helix begins on **bare 3/4 in plywood**.
- Align **railheads**, not plywood tops.
- Because the approach still has 0.236 in cork, its plywood top is **0.236 in lower** than the new helix plywood top at the seam.
- This is a stepped plywood handoff with continuous railhead elevation.

### Entry rise and absolute datum correction
At the 29.25 in planning radius:
- 12 in straight rise at 2.176%: **0.261 in**.
- 45 deg curve rise at fixed pitch: **0.500 in**.
- Total rise to 6:00: **0.761 in**.
- Entry path length: about **34.973 in**.

The **-15.000 in value is the existing plywood/benchwork top**, not the railhead. Let `T` = actual bottom-of-tie-to-railhead track height. Then:
- start railhead = `-15.000 + 0.236 + T`.
- nominally with `T = 0.160`, start railhead is about **-14.604 in**.
- at 6:00, approach plywood top is **-14.239 in**; approach railhead is `-14.239 + 0.236 + T` (nominally **-13.843 in**).
- the bare helix plywood top at the seam is **-14.003 in**, exactly 0.236 in above the approach plywood, so the railhead remains continuous.
- the bare helix plywood underside at 6:00 is therefore about **-14.753 in** in the same absolute benchwork coordinate system.

The relative 0.761 in rise and the cork-to-bare-plywood seam geometry were already correct; only the absolute surface labels needed clarification.

### P1 / first support exception
- Standard curved roadbed pieces have a backward overlap extension; **P1 does not** at the entry.
- Trim P1 to the exact 6:00 seam.
- The entry seam is a **butt/handoff**, not a normal half-lap.
- The first 0.600 in-wide bracket strap must stay **entirely on the helix side** of the 0.236 in plywood step.

### Commercial easement option that was considered
A Woodland Scenics **2% Incline Starter** was investigated as a way to raise the approach and taper cork:
- approximately **24 in long**, rising **0 to 1/2 in**.
- It would nearly match 3/4 in plywood when stacked over 6 mm cork.
- It was ultimately superseded by the cleaner cookie-cut approach with adjustable risers.
- Keep it in mind as a troubleshooting/retrofit option, not the selected primary method.

---

## 5. Exit / return to cork

Do **not** change helix pitch to force the exit to exact zero.

### Fixed curved geometry
- Entry rise to 6:00: **+0.761 in**.
- New helix after 6:00: **1290 deg = 1260 + final 30 deg**, at 4 in/turn = **+14.333 in**.
- Total rise from entry start through curved helix: **15.095 in**.

Absolute railhead elevations must include cork + full track height at the starting benchwork. With nominal `T = 0.160`, the curved helix railhead is about **+0.491 in** in the benchwork coordinate system. However, if downstream **0.000 in** is also a plywood/benchwork datum carrying the same 6 mm cork + track stack, its railhead target is about **+0.396 in**. Therefore the curved helix still finishes only about **+0.095 in above the downstream railhead target**. This is why the prior vertical-design conclusion remains valid even though the absolute railhead labels shift.

### Exit straight
If the 20-15/16 in straight continued at the full planning grade, it would add about **0.456 in**. Relative to the downstream corked-track railhead target, that would put the reference case about **+0.550 in high**. In absolute benchwork coordinates using nominal `T = 0.160`, that railhead would be about **+0.946 in**. The relative +0.550 in figure is the useful design comparison.

Actual design intent:
- Use the **20-15/16 in exit straight plus the following curve under D01** to ease the vertical profile.
- Reintroduce **6 mm cork gradually** in that zone.
- Cork changes the plywood support elevation relative to railhead by 0.236 in; it does not by itself determine the final railhead elevation.
- Downstream risers set the final D02 geometry.
- D01 / surrounding upper level eventually reaches about **+4.25 in**, so there is room to continue climbing downstream if needed.

---

## 6. Curved roadbed fabrication and joining

### Selected method
Curved annular plywood sections, not trapezoids.

- Material: **3/4 in plywood**.
- Ri/Ro: **26/31.75 in**.
- Standard physical blank: **93.75 deg**.
- Installed advance: **90 deg**.
- Physical extension past each nominal end: **1.875 deg**.
- Adjacent physical overlap: **3.75 deg**.
- Overlap arc at the 28.875 in roadbed mean radius: **1.890 in**.
- Final build uses **15 standard blanks**; P1 and P15 are trimmed after routing/dry fit.

### Half-lap joint
Within a normal overlap:
- lower/end member: remove **1/4 in from TOP**, leaving 1/2 in.
- mating/upper member: remove **1/2 in from BOTTOM**, leaving 1/4 in.
- assembled thickness returns to 3/4 in.

At a bracketed lap:
- route the brace pocket into the underside of the **1/2 in lower member**.
- 3/32 in pocket leaves **0.40625 in** wood at that local lap area.

### Verified cut nesting
The PDF contains the authoritative routing sheets.
Context only:
- Sheet 1: P1–P10.
- Sheet 2: P11–P15.
- 0.750 in minimum clear waste strip between finished profiles.
- 48x96 in, 3/4 in plywood sheets.
- With the 31.750 in outside radius, exact adjacent-piece center advance is **8.611136 in**.
- Sheet 1 10-piece group span is **91.476821 in**, centered with **2.261590 in** side margins.
- Sheet 2 is intentionally left-justified with a **0.750 in** left margin, leaving about **46.828858 in** of contiguous full-height sheet at the right for reuse.

Older PDFs may contain a hidden legacy “2.75 turns / 3.75 turns” Sheet 2 sentence. The current clean PDF removes that stale extraction text. **This build cuts P11–P15.**

---

## 7. Final support frame concept

### Uprights
- 8 x 2x4 uprights.
- Height: **18.750 in**.
- Orientation: **3.5 in RADIAL x 1.5 in TANGENTIAL**.
- 45 deg station spacing.
- With post bottoms at the -15.000 in benchwork datum, the 18.750 in posts place the underside of D01 at +3.750 in. A **1/2 in D01 plywood deck** then puts its top at **+4.250 in**.
- The exit/easing zone below D01 is the controlling top-clearance area; dry-fit the D01 deck there before permanent attachment.
- Lumber quantity: **two 8 ft 2x4s** are sufficient for the eight 18.750 in posts and leave two spare post-length pieces.

### Flat 1x3 frame ties
Current frame replaced the earlier on-edge octagon concept.

- Nominal 1x3; actual **0.750 x 2.500 in**.
- Installed **flat**, not on edge.
- Required: lower ring + upper ring = **16 ties**.
- Optional middle ring = +8 ties.
- Outside/long edge: **18.000 in EXACT**; this is the controlling cut dimension.
- Inside/short edge: **15.929 in**; check dimension only.
- End cuts: **22.5 deg mirrored**.
- Long and short edges are parallel; only end faces are angled.
- Each angled end bears about **2.706 in** against the 3.5 in post side.
- Centered on the post side, leaving about **0.397 in reveal** on each radial side.
- Derived post-center radius: **23.9758 in**.

### Frame elevation
- Lower flat frame: **0.000–0.750 in**.
- Upper flat frame: **18.000–18.750 in**.
- Optional middle frame: centered around **9.375 in**.

### Why flat 1x3s were selected
- Top/bottom rings consume only **3/4 in vertical access** instead of 2.5 in.
- Improves reach into the helix if the exterior is later enclosed.
- Broad 2.5 in face makes biscuit alignment easier.
- Optional middle ring adds racking resistance while only consuming another 3/4 in of access height.
- Middle ring can also serve as a light-duty internal shelf/wiring ledge.

### Joinery / fastening
Discussed/acceptable approaches:
- glue + **#0 biscuit** for alignment is recommended.
- screws or pocket screws may supplement the joint.
- predrill when fastening into posts to avoid splitting.
- exact screw pattern is not structurally locked in the handoff; use the PDF/current build judgment.

---

## 8. Field layout without a usable center point

The original center point is unavailable because there is a cutout, but the **26 in radius circle is already marked** and opposite 6:00/12:00 points can be identified.

### Circle checks
- 6:00 to 12:00 diameter: **52.000 in**.
- A true 3:00 or 9:00 point is **36.7696 in from both 6:00 and 12:00**.
- Adjacent 45 deg points on a 26 in radius circle are **19.8995 in apart** by chord.
- A framing square aligned to the known diameter can establish the tangent/perpendicular; 45 deg and 22.5 deg layout lines can then locate intermediate stations.
- Equal-distance checks are useful exactly like squaring a frame.

### Practical post placement
Do not try to locate the hidden post center in the field.

Current easy datum:
- set **both outside corners of each 2x4 about 1/4 in inside the existing 26 in circle**.
- exact calculated outer-corner clearance is **0.263 in**.

At the midpoint of each flat 1x3 tie, measured inward from the existing 26 in circle:
- outer edge: **2-5/16 in**.
- rail centerline: **3-9/16 in**.
- inner edge: **4-13/16 in**.

These are practical shop fractions corresponding closely to the exact geometry.

---

## 9. Steel brackets and router pockets

Selected bracket:
- Wideskall 4x4 in heavy-duty corner brace, ASIN **B07P1XZ4Q1**.
- Zinc-plated steel.
- Thickness: **0.080 in (~2.0 mm)**.
- Strap width: **0.600 in** measured/selected.
- Hole diameter: **0.185 in** listing.
- Pack size referenced: **20**.

Mounting:
- bracket remains **square to the post**.
- horizontal leg runs **radially** under the roadbed.
- do **not** cock the bracket to match helix grade.

Why no bracket angle is needed:
- helix grade is tangential.
- each radial cross-section of the helical surface is essentially level.
- across a 0.600 in bracket strap, 2.176% grade changes elevation only about **0.013 in**.

Router pocket:
- depth: **3/32 in = 0.09375 in**.
- bracket thickness 0.080 in leaves **0.01375 in** nominal extra depth.
- route about **1/32 in wider on each side** for alignment tolerance.
- do not gain tolerance by unnecessarily routing deeper.

Current frame/bracket reach:
- post center radius: **23.9758 in**.
- outside bracket face radius: **25.7258 in**.
- post corner radius: **25.7367 in**.
- clearance to 26 in roadbed opening: **0.2633 in**.
- 4 in bracket tip radius: **29.7258 in**.
- outer roadbed edge extends **2.0242 in** beyond bracket tip.

Bench-test one real bracket/plywood assembly before batch-routing because the product listing did not provide a structural load rating.

---

## 10. Commercial helix / riser options reviewed

These were researched as benchmarks/alternatives, not selected for the final build.

### Trackside Scenery / Gatorboard helix system
Discussed reference values:
- HO Standard pitch around **3.564 in**.
- HO Extended pitch around **3.702 in**.
- Standard system benchmark discussed at roughly **3.17 in railhead-to-ceiling**.
- Gatorboard/deck thickness discussed around **0.197 in**.
- A Trackside CDECK-HO-D-29.5 family option was discussed as roughly appropriate to ~28–31 in track radii, about 8 in wide, with modular segments/supports.

Why it was not selected:
- final build already had 3/4 in plywood construction and custom geometry.
- plywood provides more material for half-laps, bracket recesses, and robust woodworking.
- 4 in pitch provides about **3.09 in nominal** lower-railhead-to-plywood-underside clearance with 3/4 in plywood and ~0.160 in overall Atlas track height if cork is omitted; verify actual track height.
- modular/commercial systems would add cost and/or require more supports.

**Re-verify current catalog dimensions before any purchase.**

### Woodland Scenics 2% foam incline
- 24 in starter rising 0 to ~1/2 in was considered for the entry transition.
- useful as a general easement tool.
- final plan uses cookie-cut existing plywood on adjustable risers instead.

---

## 11. Other structural approaches considered and why they were not selected

### 1/2 in curved plywood
Pros:
- more clearance.
Cons:
- less material for joints/recesses.
- would benefit from ~12 posts / 30 deg support spacing.
Result: rejected in favor of 3/4 in plywood + 8 posts.

### 5/8 in plywood
Intermediate clearance option; not chosen because the 3/4 in build remains acceptable after using full track height (~3.09 in nominal clearance) and improves stiffness/joinery.

### Trapezoid roadbed method
Original calculator concept:
- blanks roughly **37.2 x 9.5 in**.
- diagonal cut creates two trapezoids.
- 6 pieces per turn / 60 deg.
- structural inner radius around **22.7 in**.
- outer corner radius around **37.2 in**.
Problems:
- outer corners conflict badly with the nearby **33 in outside-track centerline**.
- more seams and larger footprint.
Result: superseded by curved 26–31.75 in annular roadbed.

### Earlier on-edge 1x3 octagon frames
Many variants were explored (19-1/2, 19-3/4, 18-1/2 in rails, rotated posts, spacers). They are **obsolete** for the current build. The final flat-frame design solved both access and fabrication issues more cleanly.

---

## 12. Material / geometry decisions that matter most

If a future agent needs to understand *why* this design works, these are the highest-value relationships:

1. **4 in pitch is fixed.** Do not solve other problems by changing it.
2. **No cork in the overlapping helix** is what keeps clearance around **3.09 in nominal** with 3/4 in plywood and ~0.160 in overall track height.
3. **Cork exists on the approach and returns at the exit**, so the plywood surface steps relative to continuous railhead.
4. **Curved 3/4 in plywood + 8 posts at 45 deg** is the selected stiffness/support compromise.
5. **Brackets remain square and radial**; helix slope is tangential.
6. **Half-lap roadbed joints** create continuous 3/4 in thickness while allowing strong curved sections.
7. **Flat 1x3 frames** preserve maintenance access and give good joint area.
8. **Existing 26 in circle is the field datum.** The final frame was intentionally made easy to lay out from that circle without finding the missing center.

---

## 13. Common traps / mistakes from the design process

A new agent should explicitly avoid these:

- Do not confuse **975 deg original curvature** with the final **1335 deg** after adding a loop.
- Angle accounting: **45 deg entry + 1260 deg regular helix + 30 deg final arc = 1335 deg total**. The new helix after 6:00 is **1290 deg = 1260 + 30**. The final 30 deg is not extra beyond 1335.
- Do not confuse **railhead elevation** with **plywood underside/support elevation**.
- Do not assume cork can continue through the overlapping helix; with nominal 0.160 in overall track height it would reduce clearance to about **2.854 in** with 3/4 in plywood.
- Do not cock/cant the bracket because the track grade is ~2%; the bracket runs radially, while grade is tangential.
- Do not reuse obsolete 19-1/2 / 18-1/2 on-edge frame dimensions.
- Do not interpret the flat 1x3 tie as a wedge: its **18.000 and 15.929 in edges are parallel**; only the ends are angled.
- Do not use the hidden/legacy “2.75/3.75 turns” Sheet 2 text if surfaced by PDF extraction. Final build uses **P11–P15**.
- Do not force the exit straight to exact zero by altering helix pitch; use it as the easing/cork-restoration zone.
- When giving shop dimensions, prefer simple physical datums (26 in circle, post corners, long edge) over hidden centers or awkward decimal offsets.

---

## 14. Useful formulas for future recalculation

### Grade at radius r
`grade_percent = 100 * pitch / (2*pi*r)`

### Rise after angle theta
`rise = pitch * theta / 360`

### Chord between two points theta apart on radius r
`chord = 2*r*sin(theta/2)`

For r = 26 in:
- 45 deg chord = **19.8995 in**.
- 90 deg chord = **36.7696 in**.
- 180 deg = **52.000 in**.

### Clearance under upper deck
`clearance = railhead_pitch - upper_deck_thickness - upper_roadbed_thickness - track_overall_height`

For selected helix, nominal Atlas Code 83 flex overall height ~0.160 in:
`4.000 - 0.750 - 0 - 0.160 = 3.090 in`

Use the measured bottom-of-tie-to-railhead dimension for final verification.

---

## 15. What remains optional vs. locked

### Locked
- track radii 28 / 30.5.
- roadbed 26 / 31.75.
- 18.750 in support posts with 1/2 in D01 plywood landing at +4.250 in top surface.
- 3/4 in curved plywood.
- no cork in overlapping helix.
- 4 in pitch.
- 8 posts / 45 deg.
- final flat 1x3 geometry with 18.000 in controlling long edge.
- bracket family/dimensions and 3/32 in pocket.
- cookie-cut 12 in + 45 deg entry method.
- P1/P15 special trims and half-lap scheme.
- 15 roadbed blanks for current extra-loop build.

### Optional / field-fit
- middle flat 1x3 frame ring.
- exact screw/pocket-screw reinforcement pattern around biscuits/glue.
- final support of the last 30 deg / exit straight after it clears the lower loop.
- exact downstream elevation profile through exit straight and D01-underpass curve.
- exact cork restoration length on exit; it should be smooth and field-fit.

---

## 16. Recommended context package for the next agent

Give the next agent **all three**:
1. `helix_construction_plan_FINAL_31p75_18p75_2026-09-23.pdf`
2. `HART_Neville_Helix_Agent_Handoff_FINAL_31p75_18p75_2026-09-23.md`
3. `HART_Neville_Helix_Agent_Handoff_ADDENDUM_2026-09-30.md` — field-verified as-built updates, STL inventory, and shop process detail generated after this file was written; it flags what in this document is now stale.

Suggested instruction to the next agent:

> Treat the PDF as the fabrication source of truth and the Markdown handoff as the design-history/rationale layer. Preserve locked geometry unless explicitly asked to redesign it. If a calculation appears to conflict with the PDF, identify the datum and recompute from the locked constants before proposing changes. Ignore obsolete frame dimensions and the hidden legacy Sheet 2 turn-count text described in the handoff.


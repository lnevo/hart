# HART Railroad — Neville Island Helix Handoff ADDENDUM (2026-10-01)

> **2026-10-03:** the half-lap and bracket-pocket templates were redesigned (lattice + 100% core modifier + screw holes). See `HART_Neville_Helix_Agent_Handoff_ADDENDUM_2026-10-03.md`, which supersedes the template entries in §6 below.

**Read in this order:**
1. `helix_construction_plan_FINAL_31p75_18p75_2026-09-23.pdf` (fabrication source of truth; page 7 got additions in this session, see §8)
2. `HART_Neville_Helix_Agent_Handoff_FINAL_31p75_18p75_2026-09-23.md` (design rationale)
3. `HART_Neville_Helix_Agent_Handoff_ADDENDUM_2026-09-30.md` (as-built entry, earlier STLs, process lessons)
4. **This file**: roadbed-cutting shop process, the router jig/template STL family, bit selection, and decisions that **supersede** parts of the 09-30 addendum (§1).

Nothing in this session has been printed, cut or physically tested yet. Every STL here is verified only in software (watertight, single body, geometry checks, renders).

---

## 1. Decisions made this session (these override earlier docs)

### 1a. Bracket and post grid is now relative to the entry butt joint, not to "Post 1 at 6:00 + 21.75°"
- The user will **rotate the helix post structure** so the bracket grid starts at the first roadbed piece's butt joint. The entry tongue sits proud, so the structure can be positioned to suit. Brackets are **custom-fit**.
- **Bracket n** sits at **n × 45°** past the butt joint and **n × 0.500 in** above bracket 0 (fixed 4.000 in per 360° pitch, unchanged).
- **Even n = under a half-lap joint** (every 90°, +1.000 in). Odd n = mid-piece. The last regular bracket is n = 28 (1260°, +14.000 in). The final 30° (1260→1290°) still needs independent support, and the final piece is trimmed at the exit anyway.
- Measure every bracket height **from bracket 0** (story stick or tape hooked on bracket 0). Don't chain bracket-to-bracket, or errors accumulate.
- Bracket 0 sits under a **butt** joint, not a lap. Per the PDF, keep the whole 0.600 in strap on the helix side of the 0.236 in cork/plywood step.
- **Consequence:** the 09-30 addendum's "Post 1 at 6:00 + 21.75° / +0.242 in advance" is no longer the bracket-layout reference. The user explicitly said not to worry about post positions. The deck-height chain in 09-30 §1 is historical context only for bracket placement.

### 1b. First roadbed piece (P1): butt start, no lap at the entry
- Trim **1.875°** off the entry end:
  - **0.851 in (≈27/32 in)** on the 26 in inside edge
  - 1.039 in on the outside edge if 31.75 in, 1.047 in if 32 in
  - Chord and arc differ by less than 0.001 in at this size.
- The cut is radial: a straight line from the inside-edge mark to the outside-edge mark, pointing at the helix center.
- Result: a 91.875° piece with an inside corner chord of **37.366 in (≈37-3/8 in)**. The far end keeps its normal 1.875° lap extension and starts the next section.

### 1c. Every bracket lands on a joint and is centered on the nominal 90° joint line
That line sits 1.875° in from each blank end, in the middle of the 3.75° overlap.

### 1d. Outer radius may end up 32 in instead of 31.75 in (blank width 6 in)
The inner 26 in radius is unchanged. Every inside-edge check is independent of the outer radius.

---

## 2. Blank verification (tape measure, corner to corner)

| Check | 31.75 in outer | 32 in outer |
|---|---|---|
| Inside chord, 26 in corners (93.75°) | **37.953 in (37-15/16)** | same |
| Outside chord | 46.346 in | 46.711 in |
| Diagonals (inside corner to opposite outside corner), both equal | 42.333 in | 42.530 in |
| Nominal 90° joint mark, in from the end | 0.851 in inside / 1.039 in outside | 0.851 / 1.047 |
| Inside chord between the two nominal 90° marks | 36.770 in | same |

- Sensitivity: 1/32 in on the inside chord ≈ 0.1°.
- Framing-square check: extend the nominal 90° lines with the 48 in level. They should cross 26 in from the inside edge at exactly 90°. Extended end cuts should also cross at 26 in, but open 1-1/16 in past a 16 in square tongue (93.75°).

## 3. Half-lap geometry

- Overlap 3.75° → the lap is a **wedge**, not a rectangle:
  - **1.701 in** along the 26 in edge
  - 1.890 in at the 28.875 in mean radius
  - **2.078 in** along the 31.75 in edge (2.094 in at 32 in)
- The shoulder is a radial line.
- **Lower piece:** cut 1/4 in off the top, leaving 1/2 in. The bracket pocket (3/32 in, 0.6625 in wide) goes in its **underside**, leaving 0.406 in.
- **Upper piece:** cut 1/2 in off the bottom, leaving 1/4 in.
- Terminology trap: the user reads "bottom/top lap" as the lower/upper **piece**, not as the face being cut. Always label by piece (LOWER / UPPER) plus cut depth.

## 4. Cutting the blanks (shop method agreed)

### Nesting on a 48×96 sheet
Blanks are oriented with the chord along the 48 in direction and the pivots on a horizontal centerline 24 in from the long edge.

| Width / outer R | Center advance (0.75 in min gap) | 10-piece span | Side margin | Top/bottom margin | Pieces per sheet |
|---|---|---|---|---|---|
| 5.75 / 31.75 | 8.611 | 91.477 | 2.262 | 0.827 | 10 |
| 6.00 / 32.00 | 8.918 | 94.493 | 0.754 | 0.644 | 10 |
| 6.50 / 32.50 | 9.530 | 100.49 | 2.52 (9 pcs) | 0.279 | 9 |

- **9 in fixed spacing** (user is considering it) fits 10 per sheet at any width up to 6.5 in. Gaps between blanks:
  - 1.066 in at 5.75 in wide
  - 0.816 in at 6 in
  - 0.566 in at 6.25 in
  - 0.316 in at 6.5 in (not recommended)
- The 0.75 in gap holds up to about 6.066 in width.

### Arcs
- Circle jig (Sigerio) with the AVID POWER MW104 router.
- Bit: **1/4 in straight or upcut spiral**, plunge-capable, cut length over 3/4 in. Cut in 3–4 passes over a spoil board.
- Set the jig distance to the correct side of the bit:
  - **26 in arc:** pivot to the **far** edge of the bit (the blank is outside the circle)
  - **Outer arc:** pivot to the **near** edge of the bit

### Radial end cuts
- Mark the inside corners from the pivot: 17.773 in along the centerline and **18.976 in (18-31/32)** perpendicular. If the sheet is exactly 48 in, that's 5-1/32 in from the long edge.
- Strike the end line from the pivot hole through the mark with the 48 in level.
- Outside corner check: 23.173 in from the centerline (31.75) or 23.356 in (32).
- **Do not use a circular saw.** The end line extended past the inside corner runs into the neighboring nested blank.
- Use the router with the same 1/4 in bit against a **zero-offset straightedge guide** (hardboard base trimmed by the router itself). Start in the inner-arc kerf and stop in the outer-arc kerf.
- Keep the same side of the router base against the fence, in case the adapter plate isn't perfectly concentric.

## 5. Router bits

- **User's kit** (photo `IMG_0718.jpeg`): red wood-box set. Shanks look **1/4 in** (visual inference only; confirm with calipers).
  - Contents: straight 1/4, 3/8, 1/2, 3/4; 1/2 in mortising; bottom-bearing flush-trim bits; profile bits.
  - **None are top-bearing pattern bits.**
- **Purchased:** UTRUSTTO 4-piece pattern bit set (Amazon ASIN B0CCFBBVPF), 1/2 in cutting diameter, 1/4 in shank.
  - Listing text says "bottom bearing", but the product photo (`https://m.media-amazon.com/images/I/61iJi3mlQvL._SL1500_.jpg`) clearly shows the **bearing on top** (shank side) with a collar. Treat them as top-bearing.
  - Cutting heights per listings: shortest bit is **1/2 in or 25/64 in (listings conflict; the user must measure it)**, then 3/4, 1, 1-1/2 in.
- **Bearing constraint** used to size the templates: the bearing must ride the template edge at every depth. That requires `0 ≤ L − depth < T − ~1/8`, where L = cutter length and T = template thickness.

| Cut | Bit |
|---|---|
| Pockets (3/32) and lower-piece laps (1/4) | Shortest bit |
| Upper-piece lap (1/2) | Shortest bit if L = 1/2 in. If L = 25/64 in, take the short bit to about 3/8 in, then finish with the 3/4 in bit. |
| 1 in and 1-1/2 in bits | Too long for the current templates |
| Never | Start a 1/4 in-deep lap with the 3/4 in bit (its bearing would sit above the template) |

- Template thickness needed for longer cutters: 3/4 → about 13/16 in; 1 → about 1-1/16 in; 1-1/4 → about 1-5/16 in.
- No plunging is needed for laps or pockets: every template window runs 1/2 in past the inside edge, so the bit starts in air and feeds in sideways.

## 6. STL inventory from this session (`~/Downloads/stl`, all in **mm**, all watertight single bodies)

| File | Generator script | What it is |
|---|---|---|
| `roadbed_halflap_template_A.stl` / `_B.stl` | `make_lap_template.py` | Half-lap router template (details below) |
| `bracket_pocket_template_A.stl` / `_B.stl` | `make_bracket_pocket_template.py` | Bracket pocket router template (details below) |
| `router_depth_block.stl` | `make_router_depth_block.py` | Double-sided plunge-to-bottom depth-setting block (details below) |
| `router_depth_gauge.stl` | `make_router_depth_gauge.py` | Small stepped gauge for **checking** finished cuts |
| (no STL) | `stl_text.py` | Shared engraved-text helpers (`text_polys`, `centered`, `label_cutters`) |

### Half-lap template (`roadbed_halflap_template_A/B.stl`)
- 204 × 184 × 25 mm, 1/2 in plate.
- **Registration:** a lip on the underside hooks the blank's radial end cut; a curved fence hooks the 26 in inside edge.
- **Window:** from the end line to a radial shoulder at exactly 3.75°. It runs from r 25.5 to 32.75, clearing outer edges up to `RO_MAX` = 32.25.
- 2.4 in rails on each side support the router base.
- Engraved label: "HALF-LAP A/B · LOWER 1/4 | UPPER 1/2 · PAIRS W/ POCKET A/B".

### Bracket pocket template (`bracket_pocket_template_A/B.stl`)
- 150 × 168 × 32 mm, **3/4 in plate** (thicker so the bearing rides it at only 3/32 in depth).
- Same lip and fence registration as the lap template.
- **Slot:** 0.6625 in wide (0.600 strap + 1/32 per side), centered on the 1.875° joint line, from r 25.5 (runs off the inside edge) to 29.95. That's bracket tip 29.7258 + 0.22, so a 1/2 in bit's rounded end clears the square strap corners.
- Pocket position measured from the end cut: 0.520–1.182 in at the inside edge, 0.642–1.304 in at the bracket tip. It is fully inside the lap.
- **The bit must be 1/2 in diameter** to fit the slot.

### Depth block (`router_depth_block.stl`)
- 172 × 25 × 104 mm, 1 in thick.
- **Registration:** straight end face for the lip; a straight inner edge **tangent to r = 26 at 5.8°**, which falls inside both the lap fence span (4.1–8.5°) and the pocket fence span (2.9–7.6°).
- **Faces:** flip the block for the other hand.
  - Face 1 (unflipped model) = LAP B / PKT A
  - Face 2 = LAP A / PKT B
- **Wells:** 0.75 in diameter, interleaved between faces so none overlap in plan (at least 0.10 in apart). Each face ascends outward in the **user-specified order**:

| Row | Wells | Used how |
|---|---|---|
| Row 1 (on the joint line) | 3/32, 1/4, 3/8 | Reachable through the template windows (template on the block) |
| Row 2 (y = 2.45 in) | 1/2, 5/8, 3/4 | Router base directly on the block; 1/8 in arc-pass steps and the 3/4 in through-cut |

- The 1/2 in upper lap **with** the 1/2 in template is set by hanging the bit off the block edge and plunging to the bench. Block thickness 1.0 = template 0.5 + cut 0.5.
- The user explicitly chose this order over a layout that kept the 1/2 in well under the template window. Don't "fix" it back.
- 6 mm (cork) step: the user declined it.

### Depth gauge (`router_depth_gauge.stl`)
- Steps are bare cut depths: POCKET 3/32, LOWER 1/4, UPPER 1/2.
- Drop the matching step into a finished cut to check it.

### Hand (A/B) logic. This is easy to get wrong.
- Templates print **plate-down** (lip and fence up) and are flipped for use, so the in-use footprint is the mirror of the modeled frame.
- Each piece gets a top lap on one end and a bottom lap on the other. Flipping the piece lets **one** lap template hand do both.
- The pocket is cut on the opposite face from the lap at that end, so the pocket template is mirrored internally. **Same letter = matching pair** (lap A ↔ pocket A).
- If a template doesn't seat (lip on the end cut **and** fence on the inside edge together), the other letter is needed.

### Printing notes
- Templates and the stepped gauge print as exported.
- The depth block is exported **standing on its end face**, so well floors print as vertical walls (no bridge sag) and the registration face is the bed face. Use a brim.
- 10–15% infill, 3–4 walls.
- Labels on templates are engraved 1.6 mm on the router-ride face (the bed face when printed), mirrored to read correctly in use.
- Same filenames are overwritten on regeneration. The user's slicer needs **Reload from disk**; this caused one "file didn't update" report.

### Obsolete
`bracket_pocket_template.stl` (no suffix) is the old part. It is modeled in **inches**, not watertight, and has no registration. Recommend deleting it; not deleted yet.

## 7. Regenerating

- Run from `~/Downloads/stl`: `python make_lap_template.py`, etc. The pocket and block scripts import from `make_lap_template.py` and `stl_text.py`.
- Python deps (the session used a throwaway venv in the scratchpad that won't persist):
  ```
  numpy trimesh manifold3d shapely mapbox_earcut scipy rtree matplotlib pymupdf pypdf
  ```
- Key knobs:
  - `make_lap_template.py`: `GUIDE_OFFSET` (0 = bearing bit; set `(bushing_OD − bit_dia)/2` for a guide bushing), `RO_MAX`, `PLATE_T`
  - `make_bracket_pocket_template.py`: `PLATE_T`, `STRAP_W`, `SIDE_CLEAR`
  - `make_router_depth_block.py`: `WELLS`, `ROW2`, `BLOCK_T`
- If template thickness changes, the depth block's "hang off the edge" trick for the 1/2 in upper lap needs `BLOCK_T = lap PLATE_T + 0.5`.

## 8. PDF change (page 7)

Added two sections, verified by rendering page 7:
- **"BLANK CHECKS - TAPE MEASURE"**: the §2 table, left column.
- **"WIDER BLANK OPTIONS"**: the §4 nesting table, in the green box.
- Footer note: "Page 7 additions Rev. 2026-09-30".

The original is at `superseded/helix_construction_plan_FINAL_31p75_18p75_2026-09-23_before_chord_add.pdf`. The 9 in spacing option is **not** in the PDF yet; the user hasn't decided.

## 9. Open items

1. **Measure the shortest UTRUSTTO bit's cutting length** (1/2 in vs 25/64 in) and record it. If it's 25/64 in, the upper lap needs the 3/4 in bit for the last pass (see §5).
2. **Measure the plywood thickness** (0.750 vs 0.719 in). At a full 0.750 in, the 3/4 in setting may leave a skin; plunge slightly deeper on the last arc pass. A 25/32 in well was offered but not added.
3. **Screw length for the brackets:** pocket floor to roadbed top is 0.656 in, plus the 0.080 bracket, so screws should be **≤ about 5/8 in under the head** or they'll lift or pierce the surface under the track. A screw-check hole was offered but not built.
4. Decide on 9 in nesting spacing vs 8.611/8.918, then add it to the PDF if chosen.
5. Update the 09-30 addendum / PDF to reflect §1a (bracket grid relative to the butt joint). The PDF's entry pages (2, 3, 8) are still stale per 09-30 §8 #1.
6. First physical tests:
   - Rout one lap and one pocket in scrap. Check 1.701 / 2.078 in and the bracket fit.
   - Confirm the bearing touches the template at each depth with the router off.
   - Check the depth block wells with caliper depth rods.
7. Delete the obsolete `bracket_pocket_template.stl` once the user agrees.

---

## 10. Bracket-height spacer set + P1 height template (added later 2026-10-01)

Generator: `make_height_spacers.py` (mm, watertight single bodies). Not printed or tested yet.

- `height_spacer_1_4in / 1_2in / 3_4in / 1in / 1_1_2in.stl`: 1.5 x 2 in blocks. Sum = 4.000 in, so any 1/4 in step from 0 to 4 in works. **Any subset stacks in any order**: two tapered pegs on the bottom (8 mm dia, 3 mm tall) press into 8.5 mm x 3.6 mm sockets on top, so only the flat faces bear. Three crush ribs per socket (inner face at r 3.95 mm = 0.05 mm grip, knob `RIB_IN`) make them snap together like Lego. Exported upside down (reference face on the bed). `TRIM_MM` adjusts any block that measures off with calipers.
- `p1_height_template.stl`: same 1.5 x 2 in footprint, flat bottom on the -15 in deck, sockets on top. Its top = **top of P1** at Post 1 / bracket 0. **Built at 1-1/32 in (1.03125 in, 26.194 mm)**. The user first set 1-1/16 in after a 1/16-ruler reading of P1, then test-fit it on 2026-10-02 and found it still too high. Both are under the calculated **1.100 in (27.946 mm)** = entry riser step 0.864 in (21.946 mm, measured off the printed `entry_wedge_riser_*.stl`, still the pre-chord-correction value) + 6.000 mm cork-transition shim step. The tongue and P1 are both 3/4 in plywood, so top-to-top needs no thickness term. The user dropped the wide stability foot.
- **No case** (user decision): the collection is stored snapped together as one 5.100 in stack on the template.
- Use: template + 1/2 in per 45° post (post 2 = +1/2 ... post 8 = +3-1/2) marks the **plywood top** at that post. Bracket underside sits about 0.736 in below that (3/4 ply - 3/32 pocket + 0.080 strap). The user chose plywood-top as the reference.
- `height_base_1_4in.stl` (`BASES` in the script): 1/4 in block with a flat bottom and sockets on top, labeled "BASE 1/4"". Starts a stack on any flat surface without the template. Prints as modeled.
- Exit: the user recalls the cork can return about **6 in into the 20-15/16 in exit straight** (from an earlier session; not previously recorded). Helix railhead vs. downstream target there: about +0.26 in at full grade with the 1-1/32 template (+0.13 if the grade is flattened at the end of the curve; railhead-normalized = template - 0.903 + rise along the straight). The plywood steps down 6 mm where the cork returns.

## 11. First-loop piers (added 2026-10-02)

Generator: `make_first_loop_piers.py` (imports helpers from `make_height_spacers.py`). Files `first_loop_pier_post2.stl` ... `post7.stl`; not printed yet.

- Each pier supports the **underside** of the first loop's 3/4 in roadbed from the -15 in deck. Height at the pier center = 1-1/32 - 3/4 + 1/2 x (post - 1): Post 2 = 25/32 in, then +1/2 in per post to Post 7 = 3-9/32 in.
- **Skipped:** Post 1 (P1 already sits on the cork-transition shim; it would be 9/32 in) and Post 8 (falls over the raised entry tongue, not bare deck). Edit `POSTS` to change.
- The top is a plane at the helix grade at r = 28.875 in (2.205%, 0.033 in over the 1.5 in length). Put the center on the post's radial line; the engraved arrow points uphill. Height is angle-based, so the radial position doesn't change it. Grade varies 2.45–2.01% between the 26 in and 31.75 in edges: under 0.004 in over the pier.
- **Trellis** (the hollow-cell version printed slower: the slicer puts perimeters on every modeled wall). Two 2.4 mm webs run along the track, joined by a cross web (H in plan). All three webs have 45° diamond windows (11 mm, 2 mm tip gap). Each long web has a 9 mm top flange flared at 45°; the plywood bears on the flanges. 2 in radial x 1.5 in along the track. No supports anywhere. Model volume 17–31 cm³ each (143 cm³ for all six; solid was 691), about 12 cm³ of that in the screw tabs. Two 3/8 in thick x 3/4 in tabs reach 1 in past the pier, each with a hole countersunk from the top (shaft 0.156, head 0.340, 90°). "P# →" is engraved on the tab tops, arrow uphill. Use **1 in #6 drywall screws** (5/8 in into 3/4 in deck); 1-1/4 in would come through the bottom. Screw piers down before the roadbed goes on. Prints feet-down as modeled; use 3+ walls so the webs are all perimeter.

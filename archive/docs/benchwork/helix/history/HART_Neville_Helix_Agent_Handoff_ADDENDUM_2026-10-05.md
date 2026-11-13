# HART Railroad — Neville Island Helix Handoff ADDENDUM (2026-10-05)

**Read after** `HART_Neville_Helix_Agent_Handoff_ADDENDUM_2026-10-03.md`. Adds a mid-piece bracket-pocket template. Nothing here is printed or tested yet; verified in software only.

> **2026-10-12:** a bracket edge shim (for pre-mounting brackets on the roadbed) was added. See `HART_Neville_Helix_Agent_Handoff_ADDENDUM_2026-10-12.md`.

## 1. Request (user, 2026-10-05)
A pocket template for the **mid-piece** brackets (odd n, 45° past each joint line), with:
- no end stop; it rides the 26 in inside radius only
- countersunk screw holes
- no lattice ("hex framing")

A first build put 3/32, 1/4 and 1/2 in depth wells in a deep fence keel. The user then said **forget the depth gauge, fix the proportions**, so the wells and keel were removed and the plate was brought back to the joint pocket template's proportions.

## 2. Design — `make_mid_pocket_template.py` → `bracket_pocket_template_MID.{stl,_CORE100.stl,3mf}`
- **Slot:** identical to the joint pocket template (imports its constants): 0.6625 in wide, r 25.5 → 29.95, 3/4 in plate, 1/2 in top-bearing bit, 3/32 in deep. Core band 0.25 in at 100% via the modifier, as before.
- **Symmetric about the slot centerline → one template, no A/B hand.**
- **Registration:** a 1/2 × 1/2 in fence on the 26 in arc, one segment each side of the slot, 0.15 in clear of it (contact spans about ±5.8°). No lip. Position along the arc by the centerline:
  - the pencil line shows through both ends of the slot, and a V-notch in the outer edge sits on it
  - regular piece: the line is the piece's exact middle, 46.875° from either end. Inside-corner chord **20.683 in** from each inside corner (outer edge: 25.257 at 31.75, 25.456 at 32)
  - **P1** (butt start): 45° from the butt end. Chord **19.900 in** from the butt-end inside corner (outer 24.300 / 24.492)
- **Screws:** two #6 flat head, countersunk from the router face (same hole as 10-03), r 27.0, 1.33 in each side of the centerline. **#6 × 1-1/4 in** = 1/2 in into the underside, leaving ~1/4 in under the cork side.
- **Solid plate** (no lattice), same proportions as the joint pocket template (all imported from `make_bracket_pocket_template.py`): inner arc r 25.25, outer arc r 30.95, 2.5 in rails each side of the slot, radial side edges.
- **Labels:** underside (wood face), as in 10-03. No text on the router face/first layer.
- Mesh checks: watertight single body (also after STL reload), 148 × 158 × 32 mm, 376 cm³ model volume (34.5 cm³ core).

## 3. Printing
Router face on the bed, fence up, as exported (open the 3MF). No supports. Heavier than the lattice templates because the plate is solid; check the slicer's estimate.

## 4. Open items
1. First scrap test: center on a pencil line, screw down, rout, and check the bracket fit.

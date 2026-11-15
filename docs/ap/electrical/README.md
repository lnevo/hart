# Model Railroad Engineer – Electrical: SOQ draft

Draft Statement of Qualification for the NMRA Achievement Program certificate, prepared 2026-11-14. Checklist and rules: [www/ap/index.html#electrical](../../../www/ap/index.html) (live at hartrailroad.com/ap/#electrical).

| File | What it is |
|------|------------|
| `MRE-Electrical-SOQ-form.pdf` | The NMRA 2025 fillable SOQ form with the chosen items ticked, Region (NER) and Division (Sunrise Trails) filled. Personal fields are blank on purpose: fill them on your own copy, never in the repo. |
| `MRE-Electrical-SOQ-package.pdf` | Form + description + staging track plan + schematics (wiring deck pages 1, 2, 4, 5, 6 and the schematic deck's summary, turnout and staging node pages). |
| `attachment.html` | Source of the description (sections A to C). Print to PDF with headless Chrome and rebuild the package after editing. |
| `drawings/D1`…`D5` (SVG) | Drawings made for this application only: D1 staging level with the reversing sections (Main West, K-1 / K-2), their gaps and the passing siding (West Ext beside East Lead); D2 typical detected section and every section's detector channel; D3 MTB MP4 frog and indication wiring; D4 crossover; D5 reversing section; D6 computer-to-railroad interface. |
| `make_drawings.py` | Writes D1 to D5 from the system schematic (copied, never changed), `block_lengths.csv` and the owner's facts in its docstring. |

These drawings are kept apart from the railroad's own schematics and wiring docs on purpose (owner, 2026-11-14): do not copy them into `docs/wiring/`, `docs/ops/` or the schematic tool until the owner says so.

Items chosen: Requirement 2 turnout, crossover, other (two reversing sections on auto-reversers: Main West, K-1 / K-2); Requirement 3 (a) turnout position indication, (b) track occupancy, (r) CTC system, (k) computer control, (t) computer block detection, (u) stored control program, (v) computer-to-railroad interface (the owner's LCOS-to-MQTT bridge). (n) command control receiver waits on a named hard-wired decoder install.

Facts from the owner (2026-11-14): block gaps are in both rails; switch machines are MTB MP4 with two SPDT contacts, one for the panel LED indication and one for the frog (stock rails to the throws, common to the frog); the mainline passing siding runs between East End and Princess, with Barn and Plane as more passing places.

Owner answers (2026-11-14, later): Main West is on the AR-10 (so K-1 / K-2 is on a PSX-AR); turnouts are Peco; every section has at least one feeder pair, and both feeders of the pair pass through one channel of its DNCT2B (two channels per board, two sections per board); two trains can be shown on loop 1 and loop 2; East Lead or West Ext can serve as the passing siding.

Still open: name, address and signature on the form, then the witness (Region AP Manager or designee) signs. The owner's NMRA number and other personal details go only on a private copy outside the repo (`~/Documents/NMRA AP/` on the Mac), never here.

Rebuild: `python3 docs/ap/electrical/make_drawings.py`, then print `attachment.html` and each drawing to PDF and reassemble the package (form, description, track plan pages 1–2, D1–D5, wiring deck pages).

Sources: `docs/wiring/Layout Documentation.pptx`, `docs/wiring/Wiring_Schematic.pptx` (exported with Keynote), `docs/ops/schematic-system-draft.svg` (REV 7), `www/build/track-plan.html`, form from nmra.org/electrical.

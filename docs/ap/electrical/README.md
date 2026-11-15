# Model Railroad Engineer – Electrical: SOQ package

The Statement of Qualifications for the NMRA Achievement Program certificate, rebuilt 2026-11-15 as one bound PDF for review by the member's evaluator. Checklist and rules: [www/ap/index.html#electrical](../../../www/ap/index.html) (live at hartrailroad.com/ap/#electrical).

| File | What it is |
|------|------------|
| `MRE-Electrical-SOQ.pdf` | The package: ticked NMRA form, title page, contents, six short chapters (introduction, checklist, Requirements 1 to 5), landscape drawing plates D1 to D7, and Appendices A to E (labels, to-scale plan and detected sections, parts list, features not claimed, wiring records). Written in plain first person (owner, 2026-11-15). Tagged PDF with bookmarks. |
| `soq.html`, `soq.css` | Source of the document. Numbers, cross-references, contents and page numbers are filled in by the build. |
| `build_soq.py` | Builds the PDF: drawings, numbering, two Chrome print passes for page numbers, the form ticks, Keynote export of the two wiring decks, footers and bookmarks. `--html-only` writes `build/` without printing. |
| `make_drawings.py` | Writes plan clips P1 to P5 (the staging level copied from the system schematic, its own names removed, generic labels added) and drawings D1 to D7. The build also writes P0, the staging level to scale from `www/build/track-plan.html`. |
| `PHOTO_PUNCH_LIST.md` | Photographs still to take, with file names. Until one exists, the PDF shows a dashed placeholder where it goes. |
| `photos/` | Photographs used, downsized from `media/photos-layout` (IMG_7226, 7471, 7813, 8070, 8414, 8415, 8940, 8947, 8954, 9231, 9288). |
| `MRE-Electrical-SOQ-form.pdf` | The blank NMRA 2025 fillable form. The build ticks the claimed items and fills Region and Division only. |
| `test_build_soq.py` | `python3 -m unittest docs/ap/electrical/test_build_soq.py` |

Build (Mac, with PanelPro not needed): `/Users/lnevo/hart/.venv/bin/python docs/ap/electrical/build_soq.py`. Needs Google Chrome, Keynote and PyMuPDF (in the root `.venv`).

## Claims

- Requirement 1 on the staging level and helix: DCC; 43 gapped and detected sections in six protected districts; reverse loop RS-2 (K-1 / K-2) and RS-1 (Main West); passing siding Scale (Switch 5 to 7, owner-confirmed 2026-11-15; West Ext beside East Lead is named as a second passing place); engine storage EH-1 to EH-3; yard S-R to S-4 with Barn as its lead.
- Requirement 2: Turnout (powered frogs through the MP4 contact), Crossover (7, 23, 35), Other (two reversing sections on auto-reversers).
- Requirement 3: (a) turnout position, (b) track occupancy, (v) the LCOS-to-MQTT bridge (owner's choice, 2026-11-15). CTC, computer control, computerized block detection and computerized operation are listed in Appendix D, not ticked.

The document uses generic labels (RS-1, Y1–Y5, E1–E3 and so on); Appendix A maps them to the layout's names. The drawings are kept apart from the railroad's own schematics and wiring docs (owner, 2026-11-14).

Owner facts (2026-11-15): each auto-reverser's output passes through a DNCT2B before the track; RS-2 is K-1 and K-2, one on each channel of one DNCT2B, and they change polarity together (D5). A crossover's two position contacts are wired in series to one N/R input pair, so the panel shows Inconsistent when the halves disagree (D7, drawn from the owner's description; check against the wiring). The AR-10 is an NCE AR10; one TCS B-106 booster is installed, a second is planned if needed (the wiring deck's power district page shows the planned B2).

## Open before submission

1. Take the photographs in `PHOTO_PUNCH_LIST.md` and rebuild.
2. On a private copy outside the repo (`~/Documents/NMRA AP/`): name, NMRA number, address, date and signature on the form. Never in the repo.
3. Confirm the terminal strip positions in Section 3.2 (1–2 and 3–4 DCC buses, 5 +12 V, 6 +5 V, 7 +3 V, 8 ground). They come from docs/wiring/terminal_blocks.md, which is marked not verified.
4. Check drawing D7 against the wires on one crossover, and note how a crossover's fascia Touch Toggle lights are fed (the text only claims the computer panel waits for both halves).
5. Confirm how the feeders pass through a DNCT2B channel (D2, D5 show both feeders of the pair through one channel).
6. The witness visit and the evaluator's signature.

Sources: `docs/wiring/Layout Documentation.pptx` and `docs/wiring/Wiring_Schematic.pptx` (inventory v86), `docs/ops/schematic-system-draft.svg`, `jmri/layouts/hart/data/block_lengths.csv`, `www/build/track-plan.html`, `external/lcos-bridge` (bridge facts), form from nmra.org/electrical.

# MRE Electrical SOQ: photographs to take

Each row is a photograph the SOQ document has a place for but no existing photo could fill. Until the file exists, the PDF shows a dashed "Photograph pending" box in its place.

Photos are added in one batch once the list is done (owner, 2026-11-15). Until then, each one received is kept in `~/Documents/NMRA AP/SOQ photos incoming/` under its file name and marked "received" below. For the batch: copy them into `docs/ap/electrical/photos/` (JPEG, about 1400 px on the long side), then rebuild:

    python3 docs/ap/electrical/build_soq.py

The build checks this table: every pending photo in the document must have its file name here.

General tips: shoot in good light with the layout lights on; fill the frame with the subject; for wiring, add a small paper label naming the item (for example "RS-2" or "District B") so the photo proves itself; keep people and unrelated clutter out.

| Item | File | Where it goes | What to show | Status |
|------|------|---------------|--------------|--------|
| PL-01 | `photos/two-trains.jpg` | 3.1 Two trains | Two trains moving on the main line at the same time. | received: frame at 17 s of IMG_2185.MOV (2026-11-15) |
| PL-02 | `photos/gap-both-rails.jpg` | 3.2 Gaps | Close-up of one section boundary with the insulated gap visible in **both** rails (a coin or ruler beside it for scale). | to take |
| PL-03 | `photos/return-loop.jpg` | 3.3 Reverse loop | The return loop (RS-2, K-1 / K-2) from above, ideally with small arrows or tape flags at the two gaps. | to take |
| PL-04 | `photos/auto-reversers.jpg` | 3.3 Reverse loop | The AR-10 and PSX-AR as installed, each labelled with its section (RS-1, RS-2). | to take |
| PL-05 | `photos/passing-siding.jpg` | 3.4 Passing siding | A train standing on the passing siding (Scale, Switch 5 to Switch 7) while a second train passes on the main. | to take |
| PL-13 | `photos/yard-lead.jpg` | 3.6 Yard and yard lead | The yard lead (Barn, Switch 7 to Switches 13 and 15) with a switcher on it and the main line beside it, so it is clear the lead is a separate track. | to take |
| PL-06 | `photos/mp4-frog-wiring.jpg` | 4.1 Turnout | Underside of one turnout: the MP4 with the wires from its first contact to the two stock rails and the frog. | to take |
| PL-07 | `photos/crossover-gaps.jpg` | 4.2 Crossover | The crossover at Switch 23 or 35 from above, with the gaps in both rails between the two frogs marked. | to take |
| PL-08 | `photos/indication-normal.jpg` | 5.1 Turnout position | One turnout set normal, with its fascia lamp and the CTC/panel screen in the same frame (or a matching pair of photos). | to take |
| PL-08 | `photos/indication-reverse.jpg` | 5.1 Turnout position | The same turnout set reverse, same framing. | to take |
| PL-09 | `photos/dnct2b-feeders.jpg` | 5.2 Track occupancy | A DNCT2B under the layout with a section's two feeders visibly passing through one channel. | to take |
| PL-10 | `photos/occupancy-panel.png` | 5.2 Track occupancy | Screenshot of the dispatcher panel (or the CTC desk) with a train's sections lit as occupied. A PNG screenshot is best. | to take |
| PL-11 | `photos/bridge-node.jpg` | 5.3 Bridge | The bridge node (Nano + nRF24) with its USB cable to the PC that runs `serial_to_mqtt.py`. | to take |

## Also worth having (not placed in the document)

These strengthen the witness visit rather than the paper:

- A photo of the PSX breaker boards with a small label for each district (A to D). The power-board photo already shows them, but not which district each feeds.
- A photo of the NMRA standards gauge seated on a claimed turnout.

# MRE Electrical SOQ: photographs to take

Each row is a photograph the SOQ document has a place for but no existing photo could fill. Until the file exists, the PDF shows a dashed "Photograph pending" box in its place. To add one, save it under the file name given, in `docs/ap/electrical/photos/` (JPEG, about 1400 px on the long side is plenty), then rebuild:

    python3 docs/ap/electrical/build_soq.py

The build checks this table: every pending photo in the document must have its file name here.

General tips: shoot in good light with the layout lights on; fill the frame with the subject; for wiring, add a small paper label naming the item (for example "RS-2" or "District B") so the photo proves itself; keep people and unrelated clutter out.

| Item | File | Where it goes | What to show |
|------|------|---------------|--------------|
| PL-01 | `photos/two-trains.jpg` | 3.1 Two trains | Two trains moving on the staging main line at the same time, with two throttles in hand or on the fascia in view. |
| PL-02 | `photos/gap-both-rails.jpg` | 3.2 Gaps | Close-up of one section boundary with the insulated gap visible in **both** rails (a coin or ruler beside it for scale). |
| PL-03 | `photos/return-loop.jpg` | 3.3 Reverse loop | The return loop (RS-2, K-1 / K-2) from above, ideally with small arrows or tape flags at the two gaps. |
| PL-04 | `photos/auto-reversers.jpg` | 3.3 Reverse loop | The AR-10 and PSX-AR as installed, each labelled with its section (RS-1, RS-2). Also note the AR-10's maker from its label for Appendix C. |
| PL-05 | `photos/passing-siding.jpg` | 3.4 Passing siding | A train standing on the passing siding (Scale, Switch 5 to Switch 7) while a second train passes on the main. |
| PL-06 | `photos/mp4-frog-wiring.jpg` | 4.1 Turnout | Underside of one turnout: the MP4 with the wires from its first contact to the two stock rails and the frog. |
| PL-07 | `photos/crossover-gaps.jpg` | 4.2 Crossover | The crossover at Switch 23 or 35 from above, with the gaps in both rails between the two frogs marked. |
| PL-08 | `photos/indication-normal.jpg` | 5.2 Turnout position | One turnout set normal, with its fascia lamp and the CTC/panel screen in the same frame (or a matching pair of photos). |
| PL-08 | `photos/indication-reverse.jpg` | 5.2 Turnout position | The same turnout set reverse, same framing. |
| PL-09 | `photos/dnct2b-feeders.jpg` | 5.3 Track occupancy | A DNCT2B under the layout with a section's two feeders visibly passing through one channel. |
| PL-10 | `photos/occupancy-panel.png` | 5.3 Track occupancy | Screenshot of the dispatcher panel (or the CTC desk) with a train's sections lit as occupied. A PNG screenshot is best. |
| PL-11 | `photos/bridge-node.jpg` | 5.4 Bridge | The bridge node (Nano + nRF24) with its USB cable to the PC that runs `serial_to_mqtt.py`. |
| PL-12 | `photos/bridge-console.png` | 5.4 Bridge | Screenshot of the bridge program's console while a turnout is thrown from the computer: the command line out and the turnout report back. Run it with `verbose` so both show. |

## Also worth having (not placed in the document)

These strengthen the witness visit rather than the paper:

- A photo of the PSX breaker boards with a small label for each district (A to D). The power-board photo already shows them, but not which district each feeds.
- A photo of the NMRA standards gauge seated on a claimed turnout (W13 in the demonstration plan).
- A note of which booster(s) are installed today (the record shows two; the power-board photo shows one B-106).

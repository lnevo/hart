# Car workflow

Add a car once, then feed the cards, STS and Operations Pro from it. Decision: [ADR-013](../decisions/ADR-013-car-repository.md).

Run everything from `external/hart-ops`.

## Add cars

1. **With a photo:** put the photos in `ops/car-cards/incoming/`, then run `bin/cars intake`. It crops the photo, reads what it can with OCR, and asks about the rest. Press Enter to keep a value. Check the cropped image it names.
2. **Without a photo:** run `bin/cars add` and answer the questions. When a photo arrives later, `intake` attaches it to the same car and queues a new card.

`bin/cars status` shows the queue at any time.

## Print cards

1. `bin/cars cards` writes `ops/car-cards/print/HART_New_Car_Cards_<date>.docx` for every queued car.
2. After printing, run `bin/cars cards --mark-printed`.

## Publish

Run `bin/cars publish`. It:

1. Rebuilds the rosters from the repository and copies them to the STS seed inputs.
2. Adds new cars to `hart_seed`, and to the running STS database if it is up. The car joins at South Yard, Empty, with the pools of another car of the same code.
3. Adds new cars to a copy of the Operations Pro roster in `card_pipeline/output/ops_merge/`.

If STS was down, the seed still has the car but the running database does not. A restore from the seed brings it in.

## Install in Operations Pro

The Pi holds live session state, so never replace its roster with the export.

1. Close JMRI on the Pi.
2. `./tools/hosts/sync_roster_ops_from_pi.sh --mac`, then `bin/cars publish` to merge onto the current roster.
3. `./tools/hosts/push_ops_cars_to_pi.sh`, then `bin/cars publish --mark-ops`.

## Compare

`bin/cars compare` lists differences between the repository, the Operations Pro roster and the STS seed. It reports only.

`bin/cars fix-ops` brings a copy of the Operations Pro roster up to the repository: wrong ids listed in `ROSTER_TYPO_IDS` are corrected in place, keeping location and moves, and missing cars are added. It leaves STS and the queue alone. Install the result as in the steps above.

## Do not

- Run `process_car_images.py`. It rewrites the repository from `Images/`.
- Restore or generate with `apply_hart_seed.sh --merge-fleet`. It takes the fleet from a backup and drops added cars.
- Regenerate the seed in the middle of a run of sessions. Ids stay fixed, but home yards rebalance across the fleet.

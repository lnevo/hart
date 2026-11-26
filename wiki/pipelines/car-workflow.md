# Car workflow

Add a car once, then feed the cards, STS and Operations Pro from it. Decision: [ADR-013](../decisions/ADR-013-car-repository.md).

Run everything from `ops/hart-ops`.

For a batch of new photos (cars and locomotives) use the staged flow in [intake-stages.md](intake-stages.md). `bin/cars intake` below is the older one-step path.

## Add cars

1. **With a photo:** put the photos in `ops/car-cards/incoming/`, then run `bin/cars intake`. It crops the photo, reads what it can with OCR, and asks about the rest. Press Enter to keep a value. Check the cropped image it names.
2. **Without a photo:** run `bin/cars add` and answer the questions. When a photo arrives later, `intake` attaches it to the same car and queues a new card.

`bin/cars status` shows the queue at any time.

## Print cards

1. `bin/cars cards` writes `ops/car-cards/print/HART_New_Car_Cards_<date>.docx` for every queued car.
2. After printing, run `bin/cars cards --mark-printed`.

## Publish

Run `bin/cars publish`. It:

1. Rebuilds the rosters from the repository and copies them to the STS seed inputs. `bin/cars seed-copy` refreshes the STS seed copies alone; publish does it as step 1 of its run.
2. Adds new cars to `hart_seed`, and to the running STS database if it is up. The car joins at South Yard, Empty, with the pools of another car of the same code.
3. Writes new cars and out-of-service flags to the Operations Pro roster in `jmri/layouts/hart/operations/` (ADR-015).

If STS was down, the seed still has the car but the running database does not. A restore from the seed brings it in.

## Install in Operations Pro

The repo roster is the master ([ADR-015](../decisions/ADR-015-operations-files-in-repo.md)), and the Pi holds live session state.

1. Before publishing, close JMRI on the Pi and run `make ops-pull`, then commit anything it brings in.
2. `bin/cars publish`, then commit `jmri/layouts/hart/operations/` in the hart repo.
3. Deploy: `./tools/hosts/sync_hart_package.sh --all`, then restart JMRI so it loads the roster.

## Out of service

Change it in the repository, not in STS or JMRI. The next publish overwrites a change made there.

1. `bin/cars service out <id>...` or `bin/cars service in <id>...`.
2. `bin/cars publish`. STS updates at once: seed and running database, with cars in use listed to check by hand.
3. Commit and deploy the Operations Pro roster with the steps above.

## Compare

`bin/cars compare` lists differences between the repository, the Operations Pro roster and the STS seed, including out-of-service flags. It reports only.

`bin/cars sync` sends the repository's identity fields (road, number, length, colour, type, class, notes, as `compare` maps them) for cars both sides hold. It is a dry run by default; `--apply` writes the Operations Pro roster in the repo (refused when the Pi's Operations files differ) and the STS seed copies, which it replaces wholesale as `seed-copy` does (the dry run lists any cars added or removed and out-of-service changes beyond the fields). With `--live-sts --sts-url URL` it also patches the live STS `remarks` (`PATCH /cars/{id}`, one car at a time, each read back) after a backup, and refuses while the operating flag is set. Position, load and destination are never sent (ADR-016).

`bin/cars fix-ops` brings the Operations Pro roster up to the repository: missing cars are added and out-of-service flags set to match. It renames no car: the ten misread ids it once corrected were fixed in the master and every copy (ADR-039 lane L7, 2026-11-25), and a car under an id the repository lacks shows in `compare` under "Not in repository". It leaves STS and the queue alone. Commit and deploy the result as in the steps above.

## Do not

- Run `process_car_images.py`. It rewrites the repository from `Images/`.
- Restore or generate with `apply_hart_seed.sh --merge-fleet`. It takes the fleet from a backup and drops added cars.
- Regenerate the seed in the middle of a run of sessions. Ids stay fixed, but home yards rebalance across the fleet.

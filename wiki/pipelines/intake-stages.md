# Intake stages

Cars and locomotives go in through six stages. Nothing moves to the next stage until the owner approves the one before. Decision: [ADR-018](../decisions/ADR-018-staged-intake-workflow.md). Car commands: [car-workflow.md](car-workflow.md).

Each stage ends with a review sheet and an entry in the batch manifest (`ops/intake/<date>/manifest.csv`, committed).

## 1. Photo intake, validation and adjustment

- Photos go in `ops/car-cards/incoming/`. Each is sorted as car or loco, cropped, straightened and normalised.
- Reporting marks, number, type and railroad are read by OCR.
- Flags: blur, number cut off, duplicate of an existing car or loco, number that disagrees with the repository, name that breaks the public-name rules ([ADR-005](../decisions/ADR-005-public-equipment-names.md)).
- Review sheet: a contact sheet with the crop, the values read, the confidence and the flags. The owner corrects flagged rows only, then approves the rest in bulk.
- Writes nothing outside the working folder.

## 2. Repository records

- Approved cars go in with `bin/cars intake`. Locos go in with `bin/cars locos intake`: road number, DCC address, decoder, sound, length, weight, roster ID in the "Road Number" form (see `docs/jmri/CS105_ROSTER_SYNC.md`).
- Review: the repository diff.

## 3. Cars into STS and Operations Pro

- Back up STS and run `make ops-pull` with JMRI closed.
- `bin/cars publish`, then `bin/cars compare` must report clean.
- Commit `jmri/layouts/hart/operations/` and deploy as in car-workflow.md.
- Cars with no photo and passenger cars stay out of STS by design.

## 4. Locomotives into JMRI

- Back up the roster. Dry run first.
- DecoderPro roster entry with image and icon; Operations Pro engine roster entry.
- On the Pi: `roster_rename_road_ids.py`, then `tools/ops/cs105_roster_sync.sh --apply --rename`.
- New Dispatcher traininfo files for the roster ID, then deploy. `cs105_reboot.sh` only when nothing is moving.

## 5. Cards and public pages

- `bin/cars cards`, print, then `--mark-printed`.
- Public photo pages use public names only.
- Update `wiki/STATUS.md`.

## 6. Programming and speed matching

Per loco, once it is on the bench: program the decoder, then [speed matching](speed-matching.md).

## Models

| Work | Model |
|------|-------|
| Stage 1 image reading and cleanup | Sonnet |
| Counts, duplicate checks, manifest against repository | Haiku |
| Writing records, running import commands | Sonnet |
| Approval gates, deploys, Pi and CS-105 steps | main session |

Status: stages 1, 2 and 4 for locos are planned, not built. Stage 3 and 5 for cars exist as `bin/cars`.

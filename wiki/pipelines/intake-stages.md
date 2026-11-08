# Intake stages

Cars and locomotives go in through six stages. Nothing moves to the next stage until the owner approves the one before. Decision: [ADR-018](../decisions/ADR-018-staged-intake-workflow.md). Car commands: [car-workflow.md](car-workflow.md).

Each stage ends with a review sheet and an entry in the batch manifest (`ops/intake/<date>/manifest.csv`, committed).

## 1. Photo intake, validation and adjustment

Run from `external/hart-ops`.

- Put photos in `ops/car-cards/incoming/`. A file name starting `loco_` or `engine_` is a locomotive; anything else is a car.
- `bin/cars review` crops, straightens and reads each new photo, then writes `ops/intake/<date>/review.csv` and a contact sheet `review.html` (open it in a browser). `--batch NAME` names the batch.
- Flags: `crop-*` (crop fell back), `blurry`, `no-marks`, `no-number`, `road-not-in-fleet`, `duplicate-has-photo` (the repository car already has a photo), `same-id-as-<photo>` (twice in one batch), `private-name`, `process-failed` (one bad file does not stop the batch).
- `bin/cars approve <batch>` approves every unflagged row. For a flagged row, correct its fields in `review.csv` and set `status` to `approved` or `rejected`.
- The blur threshold (`BLUR_THRESHOLD` in `intake_stages.py`) is a first guess. Check it against the first real batch.
- Writes the derived images and the batch folder only. The repository, STS and JMRI are untouched.

## 2. Repository records

- `bin/cars records <batch> --dry-run` shows what would be written; without `--dry-run` it writes approved cars into `data/image_metadata.csv` and the car queue, and approved locos into `data/locos.csv`. It refuses while rows are still `pending` (`--allow-pending` records the approved ones anyway).
- It writes `ops/intake/<batch>/manifest.csv`, one line per recorded photo. Commit the manifest with the repository changes.
- Loco details come next: `bin/cars locos set "NW 1776" dcc_address=1776 model=SW1200 loco_type=Diesel length_ft=45` (also `weight_tons`, `hp`, `mfg`, `decoder`, `sound`, `long_address`). `bin/cars locos add` asks the questions for a loco with no photo. `bin/cars locos status` shows what each one still needs.
- Review: the repository diff.

## 3. Cars into STS and Operations Pro

- Back up STS and run `make ops-pull` with JMRI closed.
- `bin/cars publish`, then `bin/cars compare` must report clean.
- Commit `jmri/layouts/hart/operations/` and deploy as in car-workflow.md.
- Cars with no photo and passenger cars stay out of STS by design.

## 4. Locomotives into JMRI

1. `bin/cars locos publish` (refuses a loco with missing fields). It adds the engine to `jmri/layouts/hart/operations/OperationsEngineRoster.xml`, keeping session state, writes the photo to `jmri/resources/roster/<number>.jpg`, and adds the loco to `jmri/layouts/hart/data/new_locos.json`.
2. Commit and deploy: `./cats/scripts/sync_hart_package.sh --all` (installs the photo and engine roster).
3. With JMRI up on the Pi: `tools/ops/loco_roster_import.sh` shows the plan, `--apply` creates the DecoderPro entries (ID is road plus number, so the rename script is not needed).
4. `ensure_dispatcher_roster_profiles.py` for the speed profile, then `tools/ops/cs105_roster_sync.sh --apply`. `cs105_reboot.sh` only when nothing is moving.
5. The Dispatcher traininfo files for the new roster ID are not generated yet; see "Not built" below.

The Pi-side import is untested against live JMRI. Run the plan first and watch the first `--apply`.

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

## Not built

- Dispatcher traininfo generation for a new loco (1,548 files exist, keyed by roster ID). Stage 4 step 5 is by hand until this exists.
- Program the decoder and set the real decoder type in the roster entry (stage 6).
- Reading a loco's details from the photo. Locos get road name and number from OCR only.

Status: stages 1 to 4 are built (hart-ops PR 12). None has run on a real batch; the Pi import has never run live.

# Intake stages

Cars and locomotives go in through six stages. Nothing moves to the next stage until the owner approves the one before. Decision: [ADR-018](../decisions/ADR-018-staged-intake-workflow.md). Car commands: [car-workflow.md](car-workflow.md).

Each stage ends with a review sheet and an entry in the batch manifest (`ops/intake/<date>/manifest.csv`, committed).

## 1. Photo intake, validation and adjustment

Run from `external/hart-ops`.

- Put photos in `ops/car-cards/incoming/`; phone names (IMG_1234) are fine. Every photo starts as a car, and you decide on the sheet which are locomotives. A file name starting `loco_` or `engine_` starts as a locomotive.
- `bin/cars review` crops, straightens and reads each new photo, then writes `ops/intake/<date>/review.csv` and a contact sheet `review.html` (open it in a browser). `--batch NAME` names the batch.
- Flags: `crop-*` (crop fell back), `blurry`, `no-marks`, `no-number`, `road-not-in-fleet`, `duplicate-has-photo` (the repository car already has a photo), `same-id-as-<photo>` (twice in one batch), `private-name`, `maybe-loco`, `ai-says-loco`, `ai-says-car`, `ai-disagrees`, `process-failed` (one bad file does not stop the batch).
- **AI review (manual step).** Ask Claude to review the batch. It reads each image in the `image` column next to the OCR values, in groups of about ten per Sonnet agent, and writes a JSON file `{photo: {marks, number, type, note}}`. `bin/cars ai-notes <batch> <file>` merges it into the sheet. The AI only suggests: it never changes the OCR fields or the status, and a reading that differs from the OCR adds the `ai-disagrees` flag.
- **Car or locomotive.** The flags `maybe-loco` (loco words in the OCR text), `ai-says-loco` and `ai-says-car` (the AI review's type disagrees with the kind) mark candidates. The OCR hint is weak: it matched none of the 10 existing loco photos, so the AI review is the real detector. Switch photos with `bin/cars kind <batch> loco IMG_1.png IMG_2.png` (or `car`); it recomputes the roster id and clears the kind flags.
- `bin/cars approve <batch>` refuses until every pending row has an AI note (`--no-ai` overrides), then approves every unflagged row. For a flagged row, correct its fields in `review.csv` and set `status` to `approved` or `rejected`.
- The blur threshold (`BLUR_THRESHOLD` in `intake_stages.py`) is a first guess. Check it against the first real batch.
- Writes the derived images and the batch folder only. The repository, STS and JMRI are untouched.

## 2. Repository records

- `bin/cars records <batch> --dry-run` shows what would be written; without `--dry-run` it writes approved cars into `data/image_metadata.csv` and the car queue, and approved locos into `data/locos.csv`. It refuses while rows are still `pending` (`--allow-pending` records the approved ones anyway).
- It writes `ops/intake/<batch>/manifest.csv`, one line per recorded photo. Commit the manifest with the repository changes.
- Loco details come next: `bin/cars locos set "NW 1776" dcc_address=1776 model=SW1200 loco_type=Diesel length_ft=45` (also `weight_tons`, `hp`, `mfg`, `decoder`, `sound`, `long_address`). `bin/cars locos add` asks the questions for a loco with no photo. `bin/cars locos status` shows what each one still needs.
- Review: the repository diff.

## 3. Cars into STS and Operations Pro

`bin/cars publish` stops before it changes anything unless these pass:

| Check | Passes when |
|-------|-------------|
| `batches` | every photo in every `ops/intake/*/review.csv` is `recorded` or `rejected` |
| `committed` | `data/image_metadata.csv` and `data/car_queue.csv` have no uncommitted changes |
| `pi` | the Pi's Operations files equal the repo copy (run `make ops-pull` first, JMRI closed, and commit what it brings in) |
| `backup` | something in the STS backups folder is under 12 hours old (take one in the STS web app or with the `sts_backup` tool) |

- **One car at a time:** `bin/cars publish --only NW32800` skips the `batches` and `committed` checks and sends just that car. The rest of the queue is left alone.
- `--skip-check NAME` skips one check and says so. Use it only when you know why.
- After publish: `bin/cars compare` must be clean (baseline checked 2026-11-08: no drift; HART1776 is a known exception and the 70 vs 99 count is by design).
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

- `bin/cars cards` builds one print file for cars and locomotives; print, then `bin/cars cards --mark-printed`. Loco cards come from `data/locos.csv` (road, number, model, length, maker), so they can be built before stage 4 publishes the engine.
- `bin/cars site` shows the new photographed cars and locos missing from the public gallery (`www/data/fleet-gallery.json`); `--apply` adds them, with captions from the card text. It never adds an entry containing the private name. It finds nothing missing today, so a clean run means the gallery is up to date.
- Commit the gallery, then `./www/scripts/deploy_hartrailroad.sh`. The site build needs the photo mirrors described in `www/README.md`.
- Update `wiki/STATUS.md`.

## 6. Programming and speed matching

Per loco, once it is on the bench: program the decoder, then [speed matching](speed-matching.md).

## Running a batch (start here in a new session)

State on 2026-11-08: stages 1 to 5 are built and merged (hart-ops PRs 12, 13, 14; hart PRs 175 to 177). Nothing has run on a real batch. The first real batch is the test: watch every step and fix what breaks.

**Before the first batch**
- Run from `external/hart-ops` (`bin/cars ...`). It needs `.venv`, tesseract and the hart checkout on `main`; use a worktree for any hart repo change (other sessions share the checkout).
- Photos go in `ops/car-cards/incoming/` (gitignored). Phone names are fine.
- Baseline already checked: `bin/cars compare` shows no drift (99 Operations Pro cars, 70 in STS by design, HART1776 a known exception).

**Steps**
1. `bin/cars review`. Open `ops/intake/<date>/review.html`. Look at flagged crops.
2. **AI review** (the owner asks for it). Read `review.csv`; for each row Read the image in the `image` column and compare with the OCR columns. Use Sonnet agents, about ten photos each, read-only. Each returns `{photo: {marks, number, type, note}}`: the reporting marks and number as printed, the type (Boxcar, Hopper, Locomotive...), and a note on anything unreadable. Merge the answers into one JSON file in the scratchpad, then `bin/cars ai-notes <batch> <file>`. The AI suggests only; do not edit `review.csv` fields from it.
3. Show the owner the flagged rows (`ai-disagrees`, `ai-says-loco`, `maybe-loco`, blurry, no-number, duplicate). Apply their corrections in `review.csv`, switch locos with `bin/cars kind <batch> loco <photos>`, set `status` to `approved` or `rejected` for flagged rows.
4. `bin/cars approve <batch>`, then `bin/cars records <batch> --dry-run`, then without `--dry-run`. Commit the repository files and the manifest in a branch.
5. Locos: `bin/cars locos set "<ROAD NUMBER>" dcc_address=... model=... loco_type=Diesel length_ft=...` until `locos status` shows nothing missing, then `bin/cars locos publish`.
6. Stage 3 only when every photo is recorded or rejected: take an STS backup, close JMRI on the Pi, `make ops-pull`, commit, then `bin/cars publish`. Test one car first with `--only`. The first live STS insert and Pi push have never run, so watch them. Then `bin/cars compare`, commit `jmri/layouts/hart/operations/`, deploy with `sync_hart_package.sh --all`.
7. Stage 4: `tools/ops/loco_roster_import.sh` (plan), then `--apply`; `ensure_dispatcher_roster_profiles.py`; `tools/ops/cs105_roster_sync.sh --apply`. Traininfo files for new locos by hand.
8. Stage 5: `bin/cars cards`, print, `--mark-printed`; `bin/cars site`, `--apply`, commit, `./www/scripts/deploy_hartrailroad.sh`.

**Known soft spots**
- `BLUR_THRESHOLD` (600) is a guess; adjust in `intake_stages.py` after the first batch.
- The gate's STS backup check accepts any file under 12 hours old in `external/sts-docker-data/backups`; confirm the real backup file name and tighten.
- Loco photos use the car crop code and may crop badly.
- The Pi-side DecoderPro import is unit-tested only; plan before `--apply`.
- Locos need hand-entered details (DCC address, model, length); the photo gives road and number only.
- A stray remote branch `agent/claude/hart-ops-pointer` exists on GitHub with no commits; delete it when convenient.

## Models

| Work | Model |
|------|-------|
| Stage 1 image reading and cleanup | Sonnet |
| Counts, duplicate checks, manifest against repository | Haiku |
| Writing records, running import commands | Sonnet |
| Approval gates, deploys, Pi and CS-105 steps | main session |

## Not built

- Dispatcher traininfo generation for a new loco (1,548 files exist, keyed by roster ID). Stage 4 step 5 stays manual.
- Program the decoder and set the real decoder type in the roster entry (stage 6).
- Reading a loco's details from the photo. Locos get road name and number from OCR and the AI review only.

Status: stages 1 to 5 are built (hart-ops PRs 12 and 13). None has run on a real batch; the Pi import has never run live.

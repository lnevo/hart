# Intake stages

Cars and locomotives go in through six stages. Nothing moves to the next stage until the owner approves the one before. Decision: [ADR-018](../decisions/ADR-018-staged-intake-workflow.md). Car commands: [car-workflow.md](car-workflow.md).

Each stage ends with a review sheet and an entry in the batch manifest (`ops/intake/<date>/manifest.csv`, committed).

## 1. Photo intake, validation and adjustment

Run from `ops/hart-ops`.

- Put photos in `ops/car-cards/incoming/` **in the hart repo root** (not inside `ops/hart-ops`); phone names (IMG_1234) are fine. Every photo starts as a car, and you decide on the sheet which are locomotives. A file name starting `loco_` or `engine_` starts as a locomotive.
- `bin/cars review` crops, straightens and reads each new photo, then writes `ops/intake/<date>/review.csv` and a contact sheet `review.html` (open it in a browser). `--batch NAME` names the batch. A batch that already exists is refused, so to redo one (after a crop or OCR fix) use a new name and delete the old batch folder, which is yours and gitignored. The crops are rebuilt every run.
- **How a photo is read.** The crop ends at the track (the dark table strip below the backdrop is ignored). OCR then reads the *finished crop*: stencilled lettering such as gold on silver is picked out by colour (red minus blue), because brightness has almost no contrast. That window and the weights window were tuned on the CSX hoppers; other car types may read nothing, and the AI review and your edits cover them. A misread is common on a blurry photo and on digits like `O`/`0`.
- Flags: `number-length` (road number has a different digit count from most of the batch), `crop-*` (crop fell back), `blurry`, `no-marks`, `no-number`, `road-not-in-fleet`, `duplicate-has-photo` (the repository car already has a photo), `same-id-as-<photo>` (twice in one batch), `private-name`, `maybe-loco`, `ai-says-loco`, `ai-says-car`, `ai-disagrees`, `process-failed` (one bad file does not stop the batch).
- **AI review (manual step).** Ask Claude to review the batch. It reads each image in the `image` column next to the OCR values, in groups of about ten per Sonnet agent, and writes a JSON file `{photo: {marks, number, type, note}}`. `bin/cars ai-notes <batch> <file>` merges it into the sheet. The AI only suggests: it never changes the OCR fields or the status, and a reading that differs from the OCR adds the `ai-disagrees` flag.
- **Car or locomotive.** The flags `maybe-loco` (loco words in the OCR text), `ai-says-loco` and `ai-says-car` (the AI review's type disagrees with the kind) mark candidates. The OCR hint is weak: it matched none of the 10 existing loco photos, so the AI review is the real detector. Switch photos with `bin/cars kind <batch> loco IMG_1.png IMG_2.png` (or `car`); it recomputes the roster id and clears the kind flags.
- **Edit on the page.** `review.html` is editable: every field is an input and status is a dropdown. Edits stay in your browser. Click *Download review.csv*, then `bin/cars sheet-import <batch> ~/Downloads/review.csv`; it reloads the sheet and recomputes roster ids and flags for every row, so approved rows can be edited too.
- **Fix a crop on the page.** Each photo has an *Adjust crop* button: the picker from the site banners. Drag to move, scroll or the slider to zoom, the angle slider to straighten, and *Shape* for a taller or wider image; the frame is the card image's shape. *Use this crop* keeps the box in the `crop` column and previews it on the card; `sheet-import` then re-cuts the card image (and its print copy) for every changed crop. *Copy command* gives `bin/cars crop <batch> <photo> X,Y,W,H[,ANGLE]` to do one photo now. A loco is cut from the photo as taken and cleaned with `loco_backdrop`, and its old print copy is removed. A new crop does not re-read the OCR. A batch made before the picker gets it with `bin/cars crop <batch>`.
- **Same car type batch.** `bin/cars fill <batch> --set reporting_marks=CSX --set car_type=Hopper` sets columns on every row, then fills each row's empty details from the best row (most details, then the sharpest photo) and prints any row whose reading differs. Use `--set col=` to blank a column. The OCR guesses `car_class` from noise (`LO`, `HT`); blank it unless the class is printed on the car.
- **Marks.** Photos show what is printed (CSXT). If the railroad uses other marks (CSX), set them with `fill --set` or the page; the AI notes keep the printed reading, so every row then shows `ai-disagrees` for that one difference.
- `bin/cars approve <batch>` refuses until every pending row has an AI note (`--no-ai` overrides), then approves every unflagged row. For a flagged row, correct its fields in `review.csv` and set `status` to `approved` or `rejected`.
- The blur threshold (`BLUR_THRESHOLD`, 600) held up on the first batch: only the one genuinely soft photo fell under it.
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

- **Order matters.** `make ops-pull` replaces the repo's Operations files with the Pi's, so do it *before* `publish` (JMRI closed), commit it alone, then publish. If cars were merged into the repo copy first, the pull drops them: merge them back in (`merge_ops`) and commit again. Compare the Pi's files with the repo's in a scratch folder before overwriting.
- A superseded batch of the same photos still blocks the `batches` check; delete it (it is yours, gitignored).
- **STS pools.** `add_hart_cars.py` gives a new car the union of the shipment pools of every car with the same STS car code, so a code shared by several kinds of car (HM) brings in pools for other commodities. Review the pools with the owner afterwards. A pool whose shipment is gone from the live database is left out with a printed note (the seed can list shipments that were deleted).
- **STS photos.** The tool writes `{car id}.jpg` to the seed's photo folder and to `external/sts-docker-data/Rolling Stock photos/` (what the container serves); that folder is tracked in the hart repo, so commit the new files. It prints a line when it finds no photo.
- **Car type in Operations Pro.** The Pi's roster separates "Coke Hopper", "Hopper" and "Covered Hopper". New cars take the type you set on the sheet; set the right one in stage 1.
- **One car at a time:** `bin/cars publish --only NW32800` skips the `batches` and `committed` checks and sends just that car. The rest of the queue is left alone.
- `--skip-check NAME` skips one check and says so. Use it only when you know why.
- After publish: `bin/cars compare` must be clean (baseline checked 2026-11-08: no drift; HART1776 is a known exception and the 70 vs 99 count is by design).
- Commit `jmri/layouts/hart/operations/` and deploy as in car-workflow.md (`sync_hart_package.sh --all`, JMRI closed on the Pi). Check afterwards that the Pi's Operations Car Roster equals the repo's.
- Cars with no photo and passenger cars stay out of STS by design.

## 4. Locomotives into JMRI

1. `bin/cars locos publish` (refuses a loco with missing fields). It adds the engine to `jmri/layouts/hart/operations/OperationsEngineRoster.xml`, keeping session state, writes the photo to `jmri/resources/roster/<number>.jpg`, and adds the loco to `jmri/layouts/hart/data/new_locos.json`.
2. Commit and deploy: `./cats/scripts/sync_hart_package.sh --all` (installs the photo and engine roster).
3. With JMRI up on the Pi: `tools/ops/loco_roster_import.sh` shows the plan, `--apply` creates the DecoderPro entries (ID is road plus number, so the rename script is not needed). An entry that already exists is kept as built, and only gets the photo and icon if it has none. Stop PanelPro on the Pi first for `make ops-pull` and the deploy, and start it again before the import.
4. `ensure_dispatcher_roster_profiles.py` for the speed profile, then `tools/ops/cs105_roster_sync.sh --apply`. `cs105_reboot.sh` only when nothing is moving.
5. Dispatcher traininfo needs nothing per loco. The 1,554 files in `jmri/layouts/hart/dispatcher/traininfo` (and on the Pi) are transit templates: every one has `trainname="NWR 06"` and a blank `rosterid`, and you pick the loco from the roster in the Dispatcher dialog. What Dispatcher needs is a speed profile in the roster file, which step 4 adds (`ensure_dispatcher_roster_profiles.py` edits roster files, so it needs JMRI closed; copy the script into a path at least five folders deep on the Pi, because it finds its root with `parents[4]`).

The Pi-side import is untested against live JMRI. Run the plan first and watch the first `--apply`.

## 5. Cards and public pages

- `bin/cars cards` builds one print file for cars and locomotives; print, then `bin/cars cards --mark-printed`. `--trains` appends six train cards (D749, NVL, CK1, Route 23, OCS-1, EXTRA; `card_pipeline/train_cards.py`) to fill the last sheet; they are not in the queue. Loco cards come from `data/locos.csv` (road, number, model, length, maker), so they can be built before stage 4 publishes the engine.
- `bin/cars site` shows the new photographed cars and locos missing from the public gallery (`www/data/fleet-gallery.json`); `--apply` adds them, with captions from the card text. It never adds an entry containing the private name. A clean run means the gallery is up to date. A description that only repeats the car type is left out of the caption (`CSX · Hopper · 40'`).
- Merge the gallery to `main`, update the main checkout, then run `./www/scripts/deploy_hartrailroad.sh` **from the main checkout**: the build needs the photo mirrors (`www/README.md`), which a worktree lacks, and without them the Rolling stock albums drop out. The build prints the fleet item count (83 to 93 for ten cars); check one new image on the live site.
- Update `wiki/STATUS.md`.

## 6. Programming and speed matching

Per loco, once it is on the bench: program the decoder, then [speed matching](speed-matching.md).

## Running a batch (start here in a new session)

State on 2026-11-08: all stages ran once on a real batch (ten CSX hoppers, cars 81 to 90 in STS, merged and deployed). The fixes it needed are in the stages above; locos have still not been through stage 4.

**Before a batch**
- Run from `ops/hart-ops` (`bin/cars ...`). It needs `.venv`, tesseract and the hart checkout on `main`. Other sessions share the checkout: for repository changes use a hart worktree. `bin/cars` finds the hart root from its own path, so in a worktree everything it writes (repository, Operations roster, gallery, STS inputs) lands in that worktree, ready to commit. The worktree lacks the gitignored inputs, so link them in first: `ops/hart-ops/.venv`, `ops/car-cards` and `ops/intake` from the main checkout.
- Photos go in `ops/car-cards/incoming/` in the hart root (gitignored). Phone names are fine.
- `bin/cars compare` should show no drift first (HART1776 is a known exception).

**Steps**
1. `bin/cars review`. Open `ops/intake/<date>/review.html`. Look at the crops first (cut-off, black or border at the bottom, tilt). Fix one bad photo with *Adjust crop*; fix the crop code when a whole batch goes wrong.
2. **AI review** (the owner asks for it). Read `review.csv`; for each row Read the image in the `image` column and compare with the OCR columns. Use Sonnet agents, about ten photos each, read-only. Each returns `{photo: {marks, number, type, note}}`: the reporting marks and number as printed, the type (Boxcar, Hopper, Locomotive...), and a note on anything unreadable. Merge the answers into one JSON file in the scratchpad, then `bin/cars ai-notes <batch> <file>`. The AI suggests only; do not edit `review.csv` fields from it.
3. Show the owner the flagged rows (or let them edit on the page, then `sheet-import`; `fill` for a batch of one car type) (`ai-disagrees`, `ai-says-loco`, `maybe-loco`, blurry, no-number, duplicate). Apply their corrections in `review.csv`, switch locos with `bin/cars kind <batch> loco <photos>`, set `status` to `approved` or `rejected` for flagged rows.
4. `bin/cars approve <batch>`, then `bin/cars records <batch> --dry-run`, then without `--dry-run`. Commit the repository files and the manifest in a branch.
5. Locos: `bin/cars locos set "<ROAD NUMBER>" dcc_address=... model=... loco_type=Diesel length_ft=...` until `locos status` shows nothing missing, then `bin/cars locos publish`.
6. Stage 3 only when every photo is recorded or rejected: take an STS backup, close JMRI on the Pi, `make ops-pull`, commit, then `bin/cars publish`. Test one car first with `--only`. The live STS insert ran clean on the first batch once the pool and photo fixes were in. Then `bin/cars compare`, commit `jmri/layouts/hart/operations/`, deploy with `sync_hart_package.sh --all`.
7. Stage 4: `tools/ops/loco_roster_import.sh` (plan), then `--apply`; `ensure_dispatcher_roster_profiles.py` (JMRI closed); `tools/ops/cs105_roster_sync.sh --apply` only when its plan shows the CS-105's existing trains on the bus (a plan that says "0 train nodes" would try to create every entry again). No traininfo files are needed per loco.
8. Stage 5: `bin/cars cards`, print, `--mark-printed`; `bin/cars site`, `--apply`, merge, then deploy the site from the main checkout.

**Known soft spots**
- The gate's STS backup check accepts any file under 12 hours old in `external/sts-docker-data/backups`; it passed on the first batch, so the name is still untightened.
- Loco photos: do not use the freight-car crop (it tilts and over-exposes them). Pick the box with *Adjust crop* (switch the photo to `loco` first), or run `card_pipeline/loco_backdrop.py PHOTO OUT.png --box x0,y0,x1,y1` in hart-ops on an upright photo (box on the 1400 px wide photo, by eye), and check the result. Put the approved image in `CarImagesFinal/`. Remove any `loco_*` file in `CarImagesCardFillPrint/` first, because the card builder prefers that folder over `CarImagesFinal/` and a stale crop there silently wins. Consist pairs face opposite ways.
- The Pi-side DecoderPro import is unit-tested only; plan before `--apply`.
- Locos need hand-entered details (DCC address, model, length); the photo gives road and number only.
- The pools a new car gets come from the union of its car code's cars; commodity-specific pools (coke) are still set by hand.

## Models

| Work | Model |
|------|-------|
| Stage 1 image reading and cleanup | Sonnet |
| Counts, duplicate checks, manifest against repository | Haiku |
| Writing records, running import commands | Sonnet |
| Approval gates, deploys, Pi and CS-105 steps | main session |

## Not built

- Program the decoder and set the real decoder type in the roster entry (stage 6).
- Reading a loco's details from the photo. Locos get road name and number from OCR and the AI review only.

Status: stages 1 to 5 are built (hart-ops PRs 12 and 13). None has run on a real batch; the Pi import has never run live.

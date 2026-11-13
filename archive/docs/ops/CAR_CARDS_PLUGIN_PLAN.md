# Plan: the car-cards plugin

Give this to a new Claude Code session opened in the hart main checkout. It turns our car-card pipeline into a public plugin in `model-railroad-skills`, then rewrites the reader's sample prompt to use it. Paste everything under the line.

---

## Goal

A reader installs one plugin, points their agent at a folder of phone photos, and gets printed car and locomotive cards. They need nothing from the hart repo.

Ship it as a third plugin, `car-cards`, in `external/model-railroad-skills` (public, MIT), next to `operations-pro`. When it is merged, rewrite [`CAR_CARDS_FROM_PHOTOS_PROMPT.md`](CAR_CARDS_FROM_PHOTOS_PROMPT.md) and the "Make your own" paragraph on `www/ai/operations.html#cards` to use it.

## What the reader gets

- **A skill** (`skills/car-cards/SKILL.md` plus references). It covers the staged workflow, how to take the photos, the review sheet, the AI check, loco pictures, printing, and what to do when OCR or a crop goes wrong.
- **A CLI**, `cards`, run with Python from the plugin folder. Its subcommands mirror ours: `init`, `review`, `ai-notes`, `sheet-import`, `fill`, `kind`, `crop`, `approve`, `records`, `locos set|status`, `print` (with `--mark-printed` and `--all`).
- **An agent**, `photo-reader`: read-only, Sonnet, about ten photos per run. It returns `{photo: {marks, number, type, note}}`, which is the AI check.
- **One config file per railroad**, `cards.toml`, made by `cards init`. It holds the railroad name and logo, the form number, the card size and sheet grid, display names for roads (`NW` → `N&W`), car types, and description rules.
- **Tests** that run with no network and no photos from outside the plugin.

## Hard rules

- **Generic only.** No hart content in the plugin: none of our names, rosters, logos, paths, hosts, STS, JMRI or Operations Pro. The plugin reads and writes its own CSV files only. Never spell out the private name. Run the banned-terms check (as the plugin tests do with `OPS_BANNED_TERMS=hart`), and run `ops/hart-ops/card_pipeline/private_name.py` over every file before each push.
- **Port, don't rewrite.** The hard-won parts are the crop, the levelling, the colour-difference OCR window, the loco backdrop, the crop picker and the card measurements. Port them with their tests. The source is `ops/hart-ops/card_pipeline/` in hart, now MIT like the plugin.
- **Small dependency set:** Pillow, numpy, scipy, opencv-python-headless, pytesseract and python-docx. Leave out EasyOCR and torch. The skill tells the reader to make a `.venv` and to install Tesseract.
- **Build the sheet ourselves.** Don't depend on the Apostrophe Word template, which isn't ours to ship. Draw the 3×3 grid from measurements: the Apostrophe poker-sheet preset comes from the twips in `generate_card_template.py`. Add a `cards print --calibrate` page that prints card outlines on plain paper, to hold up against the reader's own stock.
- **Keep hart's own pipeline as it is.** Moving hart-ops onto the plugin is a later decision for the owner.
- **Repo rules.** Commit only on `agent/claude/car-cards*` branches in the submodule, each in its own `git worktree` under the scratchpad. Never commit on its `main`. Don't move the hart submodule pointer until the plugin PR is merged.

## Sources to read first

- `wiki/pipelines/intake-stages.md`: the runbook, the flags and the known soft spots.
- `ops/hart-ops/card_pipeline/`: `crop_car_image.py`, `process_car_images.py` (OCR), `crop_picker.py`, `loco_backdrop.py`, `intake_stages.py`, `cars.py`, `locos.py`, `generate_card_template.py`, `generate_all_cards.py`, `card_description.py`, `roster_id.py`, and `assets/train_card.prompt` (the design brief).
- `ops/hart-ops/tests/`: the golden card and the crop, picker, intake, fill, stage-gate and loco-backdrop tests.
- In the submodule: `README.md`, `tools/build_portable.py`, `.claude-plugin/marketplace.json`, and `plugins/operations-pro/` (its layout, tests and banned-terms check).
- [`CAR_CARDS_FROM_PHOTOS_PROMPT.md`](CAR_CARDS_FROM_PHOTOS_PROMPT.md): what the reader is promised today.

## Stages and agents

The main session (Opus) runs the stages and keeps a status table. Every agent's brief tells it to append progress lines (step, done/total, ETA) to `scratchpad/car-cards/progress-<agent>.md`, and the main session reports from those. Say in the final report which model did which stage.

| # | Stage | Who | Model | Runs |
|---|-------|-----|-------|------|
| 1 | Extraction map | `Explore` agent, read-only | Sonnet | alone |
| 1b | Hart-specific sweep | `Explore` agent, read-only | Haiku | alongside 1 |
| 2 | Scaffold and interfaces | main session | Opus | after 1 |
| 3a | Image pipeline | `general-purpose` agent in its own worktree | Sonnet | parallel |
| 3b | Batch CLI and review sheet | `general-purpose` agent in its own worktree | Sonnet | parallel |
| 3c | Card layout and print | `general-purpose` agent in its own worktree | Sonnet | parallel |
| 4 | Skill, references, agent, README | main session drafts, a Sonnet agent fills references | Opus + Sonnet | after 3 |
| 5 | Integrate and test | main session | Opus | after 4 |
| 6 | Fresh-reader trial | `general-purpose` agent in an empty scratch folder | Sonnet | after 5 |
| 7 | Review | `/code-review medium` on the plugin branch, then fixes | — | after 6 |
| 8 | Owner checkpoint | owner | — | stop here |
| 9 | Publish the plugin | main session | Opus | after owner OK |
| 10 | Hart side: prompt doc, page, pointer, deploy | main session; `site-builder` for the page text | Opus + Sonnet | after 9 |

### 1. Extraction map (Sonnet) and hart-specific sweep (Haiku)

- **Sonnet:** for every function in the source files listed above, record whether it is generic or ours, what it needs, which tests cover it, and where it should go in the plugin. Write the map to `scratchpad/car-cards/extraction-map.md`.
- **Haiku:** list every hard-coded value tied to hart. That means road codes, `ROAD_DISPLAY`, `IMG_9088_OVERRIDE`, `EXCLUDE_FROM_DOC`, hart paths, form numbers, logo paths, roster XML, STS or JMRI calls, `HART_*` environment variables, and the hopper rules in `card_description.py`. Each becomes a config entry or gets dropped. Write the list to `scratchpad/car-cards/hart-specific.md`.

### 2. Scaffold (main session)

Create `plugins/car-cards/`, laid out the same way as `operations-pro`:

- `.claude-plugin/plugin.json`
- `skills/car-cards/` and `agents/photo-reader.md`
- `cards/`, a Python package: `config`, `paths`, `batch` (the review.csv model and the status gates), `image`, `ocr`, `picker`, `loco`, `layout`, `cli`
- `tests/` and `requirements.txt`

Also add the plugin to `PLUGINS` in `tools/build_portable.py` and to the marketplace. Fix four things before any agent starts, so the three builders don't collide:

- the column list of `review.csv`;
- the config schema;
- the function signatures between the modules;
- the folder layout of a reader's working folder: `photos/incoming/`, `batches/<name>/`, `images/final/`, `data/cars.csv`, `data/locos.csv`, `output/`.

Commit the scaffold to `agent/claude/car-cards` and base each builder's worktree on it.

### 3. Builders (three Sonnet agents in parallel)

Each agent owns only its own modules and tests, and gets the extraction map and the scaffold.

- **3a, image pipeline:** port the crop and levelling from `crop_car_image.py`, the colour-difference OCR and parsing from `process_car_images.py` (Tesseract only), the blur score, `loco_backdrop.py`, and the crop picker's re-cut. Tests: port `test_crop_foreground`, `test_loco_backdrop` and `test_crop_picker`, using fixture photos (see the decisions below).
- **3b, batch CLI and review sheet:** port `review`, `ai-notes`, `sheet-import`, `fill`, `kind`, `crop`, `approve`, `records`, `locos` and the flags from `intake_stages.py`, `cars.py` and `locos.py`. Port the editable `review.html` with its picker, its "Download review.csv" button and the stage gates. Drop every STS, JMRI, roster-XML and publish step. Tests: port `test_intake_stages`, `test_intake_fill` and `test_stage_gate_cards_site`, keeping only the card gates.
- **3c, card layout and print:** port the card from `generate_card_template.py` and `generate_all_cards.py` (header, logo, type box, photo, the three icon rows, footer). The sheet is drawn from measurements, with the Apostrophe preset and `--calibrate`. Descriptions are driven by config. Locomotive cards are included. Ship generic icons; check the source of the current ones, or redraw them. Tests: a golden card made from a fixture photo, and the description rules.

### 4. Skill (main session drafts, a Sonnet agent fills references)

- **`SKILL.md`:** when to use the skill, the stages, and the rule that nothing moves on until the reader approves it. Write it in plain words and lead with what the reader gets.
- **References:** `photos.md` (the backdrop, the angle, a consist facing opposite ways), `review-sheet.md`, `ai-check.md`, `locos.md`, `printing.md` (stock, calibration, mark printed), and `troubleshooting.md` (misread `O` and `0`, a blank OCR on new car types, crop fallback, a stale print copy winning). Each rule must come from our runbook or from a test, not from memory.
- **README:** add a section to the submodule `README.md` beside Operations Pro, with **Can do** and **Can't do** lists in the same style.

### 5. Integrate and test (main session)

- Merge 3a, 3b and 3c into `agent/claude/car-cards`.
- Run the plugin tests and `python3 tools/build_portable.py --check`, and run the root tests so nothing else breaks.
- Run an end-to-end pass in an empty scratch folder on about ten owner photos, copied from `ops/car-cards/` (local only, never committed). Go `init` → `review` → AI check → `approve` → `records` → `print`. Then open `review.html` in the browser and render the `.docx` to PDF to look at it.

### 6. Fresh-reader trial (Sonnet)

Install the plugin from the branch in a new scratch project, with no hart repo in reach. Give the agent only five photos and the short prompt drafted for stage 10. It runs to a print file. Report every place it got stuck or had to guess, then fix the skill or the CLI and repeat until it runs clean.

### 7. Review

Run `/code-review medium` on the plugin branch and fix what it confirms. Then run the banned-terms and private-name checks again.

### 8. Owner checkpoint — stop

Show the owner:

- the PDF of one printed sheet, for a test print on real stock;
- the `review.html` from the end-to-end pass, opened in the browser rather than as a screenshot;
- the skill's **Can do** and **Can't do** lists;
- the fresh-reader report.

Wait for approval.

### 9. Publish

- Set the version in `plugins/car-cards/.claude-plugin/plugin.json` to `0.1.0` and run `build_portable.py`.
- Open a PR in the submodule. Merge it once its checks pass.
- Install it from the GitHub marketplace in a scratch project and confirm the skill loads.

### 10. Hart side

In a hart worktree (`make wt TOPIC=car-cards-plugin-docs`):

- Rewrite `docs/ops/CAR_CARDS_FROM_PHOTOS_PROMPT.md` to cover:
  - what you get;
  - what you need (an agent that runs commands, Python, Tesseract, the photo setup, card stock);
  - installing the plugin (Claude Code commands, plus the Cursor and Codex note from the plugin README);
  - a short prompt that uses it, for example "Use the car-cards skill. Set up a card folder here for my railroad, the [name], then run a first batch from `photos/incoming/` and stop at each stage for me to check";
  - the notes from our runs.

  Keep the long build-it-yourself prompt at the bottom, under "No plugin? Build it yourself", for agents that can't install plugins.
- Have `site-builder` update the "Make your own" paragraph on `www/ai/operations.html#cards`: say that the cards come from a plugin anyone can install, and link both the plugin README on GitHub and the prompt document. Add the plugin wherever the site lists `model-railroad-skills` (`behind/index.html#ai` and the AI index; check with grep).
- Move the `external/model-railroad-skills` pointer to the merged commit.
- Run `python3 tools/ops/build_docs_index.py` and `./tools/check.sh`, then commit, push and open a PR. Merge it once the check passes.
- Deploy the site from the main checkout (`./www/scripts/deploy_hartrailroad.sh`), check the Build counts, and confirm the live links.

## Decisions already made

| Question | Decision |
|----------|----------|
| License | MIT for the whole hart repo, done with this plan; the plugin repo is already MIT |
| Plugin name | `car-cards`, in `model-railroad-skills/plugins/` |
| OCR engine | Tesseract only |
| Sticker template | Drawn by the plugin, with the Apostrophe poker preset and a calibration page |
| Hart's own pipeline | Unchanged for now |
| Merge of the plugin PR | Only after the owner checkpoint (stage 8) |

## Defaults to confirm at the checkpoint

These don't block stages 1 to 7.

- **Fixture photos:** three owner photos ship as test fixtures (a freight car, a hopper with stencils, a locomotive), shrunk to about 800 px wide. Check that none shows the private name or anything personal. The alternative is synthetic images drawn by the tests, which are weaker for the OCR tests.
- **Default design:** the default card is our card design without our logo, and the reader's logo goes in through `cards.toml`.
- **Version:** the first release is `0.1.0`, marked "in development" in the README until the owner says it's ready.

## Report at the end

- The plugin PR and merged commit, and the hart PR and commit.
- Test counts.
- The fresh-reader result.
- The site deploy and its Build counts.
- Which model did which stage.
- Anything left open.

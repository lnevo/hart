# Project health: hand-off (2026-11-20)

Status: done (2026-11-21)

Comes from the 2026-11-20 quick review of open fixes, workflow and where facts are kept. The owner made these choices on 2026-11-20:

- Source-data rows 8 and 10 are included, as proposals the owner reviews before anything is built.
- GitHub auto-merge is turned on.
- The large scripts get tests, then a split.
- File moves are proposed first and made after the owner approves.

Row 9 (device facts kept three times) was discussed with the owner on 2026-11-20 and is planned under [Row 9](#row-9-device-facts-tablesxml-as-an-output): `tables.xml` becomes an output built from one device master and a template.

## How to run this

The coordinator is the main session that picks up this file.

- **Parallel agents:** run at most 5 at a time, in the waves below. Start the next item as soon as a slot frees up; don't wait for a whole wave to finish.
- **Worktrees:** every agent that edits files runs with `isolation: "worktree"`. Read-only agents need no worktree.
- **Model and effort:** use the ones set in each item's table. They follow the routing rule: Haiku for sweeps, Sonnet for bounded edits, the default model for logic, data-model and refactor work.
- **Progress:** each agent appends progress lines (step, done/total, ETA) to `<scratchpad>/health/<item>.log`. The coordinator keeps one status table covering every item and updates it whenever an item's state changes.
- **Commits:** subagents cannot commit, because a hook blocks it. Each agent leaves its changes uncommitted and reports the files to stage. The coordinator then does the following for each PR:
  1. Reviews the changes and commits them, staging files by name.
  2. Pushes the branch and opens the PR.
  3. Runs `/code-review medium` on code PRs and fixes the findings it confirms. Findings are triaged, never forwarded wholesale.
  4. Queues `gh pr merge --merge --auto`, never with `--admin`.
- **Briefs for code work** (W3, W4, and W6 builds) carry the five-point checklist. The agent checks its whole diff against it before handing back:
  1. Errors are clear domain errors, never raw exceptions.
  2. No silent fallbacks: no guessing, defaulting or skipping.
  3. Invariants are checked after every change to the data.
  4. Inputs are validated up front.
  5. No duplicated helpers and no per-call rebuilds.

  Tests must cover the error paths too.
- **Owner gates:** W5 and W6 stop after their proposal. The coordinator asks the owner as batched multiple-choice questions, up to 4 at a time with the recommended choice first, and builds only after the answers come back.
- **Live hosts:** none of this needs a Pi or Windows deploy unless an item changes a live artifact. If one does, the deploy stays in the main session and follows AGENTS.md. A site change gets `PORTAL_CHECK=1 ./tools/check.sh`, then `deploy_hartrailroad.sh` once it is merged.
- **Close-out:** finish with what is done, then "nothing left in progress" (or what still is), then the loose ends grouped as waiting on the owner / parked / outside our control.

## W0. Coordinator setup (main session)

1. Turn on auto-merge with `gh repo edit lnevo/hart --enable-auto-merge`. The owner approved this on 2026-11-20. Confirm it with `gh api repos/lnevo/hart --jq .allow_auto_merge`.
2. Create `<scratchpad>/health/` and the status table.
3. Launch Wave 1.

## Wave 1 (5 agents)

### W1a. Hand-off audit (read-only)

| Agent | Model | Effort | Isolation |
|-------|-------|--------|-----------|
| `repo-auditor` | haiku | low | none |

Cover every file in `wiki/projects/`, plus `wiki/DIGICON_SCHEMATIC.md` and `wiki/DISPATCHER_LAYOUT_HOOPS.md`. For each file, list:

- Each open item with its line, and whether it is still open. Check it against git, `make deploy-status`, `gh pr list` and the live site.
- Each claim that is no longer true. Two are known:
  - `anyrail-5-3c-handoff.md` "Also open" says Windows never got #689.
  - `source-data-exceptions-handoff.md` says the repository guide and JMRI additions pages are out of date, which #756 and #758 probably fixed.
- A verdict: **live** (keep), **finished** (its record moves to `STATUS_LOG.md` or `archive/`), or **merge into another hand-off**.

Output: a table in `<scratchpad>/health/W1a-audit.md`.

### W3. deploy-status names live changes

| Agent | Model | Effort | Isolation |
|-------|-------|--------|-----------|
| `general-purpose` | sonnet | medium | worktree |

`make deploy-status` reports "N commits ahead" even when none of them changes anything shipped. On 2026-11-20 the Pi was 26 commits behind with no live change, which reads as a loose end that isn't one.

The change: report how many of those commits touch a live artifact, and list the paths. Take the list of shipped paths from the same place `sync_hart_package.sh` reads it, so the two cannot drift; if no such place exists, make one and have both read it. Add tests that cover no live change, a live change, and an unknown deployed commit. No MQTT, and no ssh in the tests.

### W4a. Tests: `tools/wiring/refresh_wiring_docs.py` (1.8k lines)

| Agent | Model | Effort | Isolation |
|-------|-------|--------|-----------|
| `general-purpose` | sonnet | high | worktree |

Add behaviour tests for what the script does now: a golden comparison of its outputs against the committed files, plus unit tests on the parsing and on its error paths. Change no behaviour.

Stop with the tests green and report them. The split is W4s.

### W5. File-move proposal (read-only)

| Agent | Model | Effort | Isolation |
|-------|-------|--------|-----------|
| `repo-auditor` | sonnet | low | none |

Propose new homes for:

- the generated CSVs in `docs/ops/opspro-build/`;
- `docs/jmri/speedmatching/profile-*`;
- `wiki/DISPATCHER_LAYOUT_HOOPS.md` (next to `jmri/layouts/hart/parked/`?);
- `wiki/DIGICON_SCHEMATIC.md`.

For each move, list every path that names the file: scripts, Makefile, `check.sh`, the site build, AGENTS.md, the skills and the wiki. Also say whether the website build reads it. Then propose any other generated output found under `docs/`.

Output: a table in `<scratchpad>/health/W5-moves.md`. The coordinator asks the owner, then launches W5b.

### W6. Source-data proposals: rows 8 and 10, plus the smaller items (read-only)

| Agent | Model | Effort | Isolation |
|-------|-------|--------|-----------|
| `Plan` | default (opus) | high | none |

Read rows 8 and 10 and "Also open, smaller" in [`source-data-exceptions-handoff.md`](source-data-exceptions-handoff.md). Leave row 9 out.

For each item, give:

- what reads the fact today;
- the proposed single source;
- the files and builders that change;
- the risk to approved panels and desks (the approval fingerprints);
- the effort.

The items are:

- **Row 8:** kind and level read from the name prefixes (`Track `, `OS Switch `, `BS `, `Mast `), the crossover half read from A or B, a balloon loop read from a name ending " Loop", and the level read from a band title.
- **Row 10:** the drawing workarounds in the preferences files: `level_leg`, `le_tight_crossovers`/`le_split_crossovers`, `le_shift`, `le_labels`. Say for each one whether it can become a plugin rule.
- **`le_signal_boundaries.csv`:** is it still needed now that staging masts come from the rule?
- **Screen sizes:** decided 2026-11-21: one committed `host_screen` setting (the Pi's and the Windows box's shared 1920 x 1080 monitor, less a 48 px taskbar) that `le_window` and `cats_window` are derived from (`tools/schematic/host_screen.py`).
- **Band names and the 5 cm cut:** these sit in `plan_overrides.json` (main_upper section) `levels` "until B2". What is B2, and can they go now?

Output: `<scratchpad>/health/W6-proposals.md`, with decisions phrased so they can be asked as multiple choice. The coordinator reviews the proposals with the owner. Build only after the owner answers: the design stays in the main session, and the mechanical parts go to Sonnet worktree agents as W6b.

## Wave 2 (start as slots free)

### W1b. Hand-off consolidation (after W1a)

| Agent | Model | Effort | Isolation |
|-------|-------|--------|-----------|
| `general-purpose` | sonnet | medium | worktree |

Act on the W1a verdicts:

- Fix the claims that are no longer true.
- Move finished hand-offs to `archive/wiki/projects/`, or move their record to the top of `STATUS_LOG.md` word for word.
- Merge overlapping hand-offs so each project has one live hand-off.
- Update the links: `wiki/home.md`, `STATUS.md`, AGENTS.md and the skills.
- Run `python3 tools/ops/build_docs_index.py` and `./tools/check.sh`.

This is docs only, so there is no code review.

### W4b. Tests: `jmri/layouts/hart/scripts/gen_ctc_track_plan.py` (1.4k lines)

| Agent | Model | Effort | Isolation |
|-------|-------|--------|-----------|
| `general-purpose` | sonnet | high | worktree |

First check whether anything live still uses it. `layout_facts.py` and `refresh_bean_comments.py` import from it, and the USS CTC machine is parked. If only parked work and those imports use it, test just the parts the importers call, and say so in the report. The split is then the owner's call. Otherwise the job is the same as W4a.

### W4c. Tests: the hart-ops generators

| Agent | Model | Effort | Isolation |
|-------|-------|--------|-----------|
| `general-purpose` | sonnet | high | worktree |

The scripts are `ops/hart-ops/card_pipeline/generate_card_template.py` (1.5k), `generate_waybill_cards.py` (1.3k) and `ops/hart-ops/publications/rebuild_local_station_maps.py` (1.3k). Other card_pipeline scripts import them, so cover what those importers call. Golden outputs must leave out the private template files and photos, which are not in git. Use small fixtures instead.

### W2. Split `STATUS_LOG.md` (after W1b merges, since W1b writes to it)

| Agent | Model | Effort | Isolation |
|-------|-------|--------|-----------|
| `general-purpose` | haiku | low | worktree |

`STATUS_LOG.md` is 724 lines. Move the entries before 2026-11-01 word for word to `archive/wiki/STATUS_LOG-2026-10-and-earlier.md`, and keep a link at the foot of `STATUS_LOG.md`. Then check that every link to a moved anchor still resolves (`git grep "STATUS_LOG.md#"`). Docs only.

### W4s. Splits (each after its test PR merges)

| Agent | Model | Effort | Isolation |
|-------|-------|--------|-----------|
| `general-purpose` | default (opus) | high | worktree |

There is one split per script, in a commit that changes no behaviour. Leave out `gen_ctc_track_plan.py` if W4b found it serves only parked work.

The golden outputs and tests from W4a–c must stay byte-identical before and after the split. Keep the old entry points and command-line flags, since the Makefile, other scripts and the docs call them.

### W5b. File moves (after the owner approves W5)

| Agent | Model | Effort | Isolation |
|-------|-------|--------|-----------|
| `general-purpose` | sonnet | medium | worktree |

Make the approved moves in one PR and update every reference W5 listed. Then:

1. Run `./tools/check.sh` with `PORTAL_CHECK=1` if the site reads any moved file.
2. Rebuild the docs index.
3. After the merge, the coordinator deploys the site if it changed.

### W6b. Source-data builds (after the owner answers W6)

These are built the way the owner decides. Any change that touches panels or desks goes through `make panels CHECK=1`, the approval fingerprints rule and `make panelpro-test`. Any panel approval needs the exact file installed in the Mac's `~/JMRI_UserFiles` first. A deploy with `--pi --win` follows only when a live artifact changed.

## Row 9: device facts, `tables.xml` as an output

Background: row 9 in [`source-data-exceptions-handoff.md`](source-data-exceptions-handoff.md). The owner decided this on 2026-11-20:

- **`tables.xml` is an output.** It is the panel PanelPro and CATS load. Devices and everything else are defined in other files, and nothing reads `tables.xml` as a source.
- **The template.** Anything JMRI owns, or that the owner saves in PanelPro and the build does not generate, lives in a hand-kept template. The build merges the template with the generated parts to write `tables.xml`. Examples: LogixNG, memories, settings changed in a PanelPro session.
- **Pulls from the live copy are the one exception.** A Store pulled from the Pi or the Mac (`make tables-pull-pi`, `make tables-pull`) is split back into the sources: device facts into the device master, everything else into the template. Then `tables.xml` is regenerated.
- **One device master for all three levels.** `public_name_map.csv`, `device_map_staging.csv` and `device_map_main_upper.csv` are joined into one source, with a description for every column and every row. Staging, main and upper are treated the same way and share one structure. Staging is more complete; the main and upper levels hold temporary (virtual) assignments under ADR-028. That difference is a value in a column, such as an assignment status, never a different layout or a separate file.

The current `AGENTS.md` rule "fix the data in `jmri/layouts/hart/output/tables.xml` instead" changes to "fix the source data or the template".

Row 9 starts after W6's proposals are approved, because rows 8 and 9 touch the same readers (hartlib `names.py`, `le_tables.py`). R9a is read-only and can start in Wave 1 if a slot is free.

### R9a. Inventory and design proposal (read-only)

| Agent | Model | Effort | Isolation |
|-------|-------|--------|-----------|
| `Plan` | default (opus) | high | none |

1. **Sort every element type in `tables.xml`** (turnouts, sensors, lights, memories, reporters, blocks, masts and heads, SML, LogixNG, routes, audio, ID tags and the rest) into one of:
   - generated from the device master;
   - generated from other build data, such as blocks from the schematic or SML from discovery;
   - owner-saved in PanelPro, so it goes in the template;
   - written by JMRI on every Store, which the pull drops.

   Give a count for each group, and examples of anything that is hard to place.
2. **List every reader and writer** of `public_name_map.csv`, `device_map_staging.csv`, `device_map_main_upper.csv` and `tables.xml` (27 non-test scripts read the first two today), plus the site build, `check.sh`, the hooks (`check_after_edit.py`) and the skills (`tables-pull`, `panelpro`).
3. **Propose the master's schema.**
   - Give the file name, and a dictionary of every column with a description of each.
   - Say how alias rows for old names are kept, how the public names under ADR-005 are kept, where the DCC group lives (a column, never read from comments), and how items the build owns are marked (an explicit column, never found by comment or name).
   - Show how a temporary main or upper assignment is marked (one column value), and how swapping in a physical device later (ADR-028) changes only that row.
4. **Propose the template's format and the merge.** Cover the template's file (or files) and format, the merge order, and the stable sort, so that a Store and a rebuild produce the same bytes.
5. **Propose the pull split.** Cover how a live Store is compared with the generated output, where each kind of change goes, and that the pull **fails and names the elements** it cannot sort, rather than guessing.
6. **Propose the cut-over gate.** The first generated `tables.xml` must match the committed one, either byte for byte or as the same set of elements and attributes after a defined normalisation. Every difference is listed and explained before the switch.

Output: `<scratchpad>/health/R9a-proposal.md`, with the owner's decisions phrased as multiple choice. The coordinator reviews it with the owner, then writes the ADR. The ADR follows ADR-008, ADR-014 and ADR-027 and records that `tables.xml` is an output.

### R9b–R9e. Build (after the owner approves R9a)

The design stays in the main session. Each step is its own PR, carries the five-point checklist, and gets `/code-review medium`.

| Step | Job | Agent | Model | Effort |
|------|-----|-------|-------|--------|
| R9b | Build the device master from the three CSVs. Generate all three old files from it and check them byte-identical in `check.sh`, then move the readers over one group at a time | `general-purpose` | sonnet | high |
| R9c | The template, plus a generator that writes `tables.xml` from the master, the other build data and the template. It must pass the R9a cut-over gate | `general-purpose` | default (opus) | high |
| R9d | Change `tables-pull` (Pi and Mac) to split a Store into the master and the template, failing on anything it cannot sort. Add tests built from real pulled Stores, with private data removed | `general-purpose` | default (opus) | high |
| R9e | Retire the old files (or keep them only as generated copies), and update AGENTS.md, the `tables-pull` and `panelpro` skills, `check_after_edit.py` (an edit to `tables.xml` itself is refused), the pipelines wiki and the site's tables page | `general-purpose` | sonnet | medium |

R9b is two PRs. R9b-1 (done): `jmri/layouts/hart/data/devices.csv` and its dictionary `devices.columns.csv` (`hartlib.devices`), the two device maps and `public_name_map.csv` generated from it and held byte-identical by `check.sh`, and the writers `build_staging_masts.py`, `build_device_map.py` and `panel_items.py` writing their own rows. `public_name_map.csv` lost its 416 alias rows and 25 retired identity rows. R9b-2: move the readers to the master (`railroad_facts` and `railroad_invariants` `DeviceMap`/`NameMap`, `level_devices`, `names`, `staging_device_map`, `build_layout_le`, `le_common`, `le_names`, `le_checks`, `build_signals`, `build_cats_panel`, `cats_panel_facts`, `cats_panel`, `plan_lengths`, `sync_staging_signals`, `lcos_mqtt_mimic`, `cats_turnout_io`, `audit_panel_contracts`, `capture_public_name_baseline`, `layout_facts`, `check_layout_facts`, `check_name_copies`, `refresh_wiring_docs`, `add_main_upper_levels`, `build_layout_index`, `jmri_additions_page`, `check_hart_phase02`), retire `apply_public_names*.py` and `sync_public_name_map.py` (they read alias rows that are gone), then drop the `pnm_*` columns.

Each build PR runs `make panels CHECK=1`, the approval fingerprints rule and `make panelpro-test`. R9c and R9d change what the hosts load, so the coordinator:

1. pulls any live Store first (`make tables-pull-pi`);
2. deploys `--pi --win` after the merge;
3. confirms on the Mac that PanelPro and both CATS desks load the generated file.

None of this runs while the operating flag is set.

## Progress and owner decisions (2026-11-20)

**Merged:** W3 #765, W5b #766, W4a #767, W4b #768, W1b #770, W4c #771, W2 #781; W4s splits #772 (wiring), #776 (waybills), #777 (card template), #779 (station maps); the CK1 deletion lnevo/sts-docker-helpers#12 with #778; the decisions #780; R9b #782. Auto-merge is on.

**Order from here (agreed with the level-unification session):** its step 2, the one mast process, merges first, after the owner's panel approval. Then R9b-2 (the readers move to `devices.csv`), the W6b `mast_rule.py` items (band `level`, read from `interlockings.csv`; crossover halves from the plan; the loop flag), R9c, R9d and R9e. The W6b plugin rules (101/103 three-way, `level_leg` faults) do not touch masts and run now.

**W5, file moves (owner):** `docs/ops/opspro-build/` to `archive/`; `DISPATCHER_LAYOUT_HOOPS.md` beside the parked data; `DIGICON_SCHEMATIC.md` to `docs/ctc/`; the speed-matching profiles stay where they are. Done in #766.

**W4b:** `gen_ctc_track_plan.py` serves the parked USS machine plus one live check. Owner: no split while USS is parked.

**W1a leftovers (owner):** the broken CK1 weigh scripts are deleted (lnevo/sts-docker-helpers#12), which closes the sts-helpers clean-up. The Main West fold is dropped: Main West stays straight and Brick-Plane is the only turnback.

**W6, source-data rows 8 and 10 (owner):**
- `role` goes in the R9 device master; readers move to it after R9b.
- Each band entry in `plan_overrides.json` (main_upper section) gets a `level` field. The band names stay as drawn text, and the stale "until B2" note is fixed. No rename.
- A crossover's two halves come from the plan's structure; A and B stay as labels only.
- `level_leg` stays as preferences. The plugin reports its causes: two blocks in one CATS cell, or a desk that is too wide.
- 101 and 103 are drawn tight and split by a plugin rule from the three-way part, and the HART entries go. **Done in #785** (schematic-maps 0.1.48), along with the plugin's desk faults for the `level_leg` causes.
- `le_shift` stays until staging is next redrawn.
- Staging `le_labels`: `name_columns` and `name_steps` become plugin rules, HART derives its button groups, and `lamp_columns` goes if it does nothing. The fingerprints must not change.
- `le_signal_boundaries.csv` is retired, along with `apply_le_sml_facing.py` once it is shown to change nothing, before R9c. Done 2026-11-20: the script was a no-op on `tables.xml` (byte-identical); the deploy audit now checks every staging mast against `staging_masts.csv` through the plugin's slot index.
- The screen sizes stay in the preferences.

W6b builds wait for R9b and the level-unification mast step, since both touch `mast_rule.py` and the device maps.

**R9a (owner):** recorded in [ADR-029](../decisions/ADR-029-tables-xml-is-an-output.md). In short:
- the master is `data/devices.csv`, with `devices.columns.csv` describing its columns;
- the old pre-ADR-005 names and the retired names are dropped, and the spares are kept;
- `assignment`, `role` and `written_by` columns, the last checked against one list of owning scripts;
- comments are generated from the wiring columns;
- one JMRI-format template, with the discovered SML in its own file and a fixed envelope;
- the staging block paths are dropped after a sandbox test;
- a PanelPro rename on a hand-kept row updates the master;
- a strict cut-over, with the deploy rewrite folded into the generator.

R9b merged as #782: the master and its writers. R9b-2 (the readers, 2026-11-20): every reader of `public_name_map.csv`, `device_map_staging.csv` and `device_map_main_upper.csv` now gets its rows from `devices.csv` through `hartlib.devices` (`device_map_lines`, `name_map_lines`), and `hartlib.railroad.Sources` has one `devices` path in place of `name_map` and `device_map`. The three old files are still generated and held byte-identical by `check.sh`; only the generator check and its tests read them. Readers that told a kind by its name prefix test `role` (`DeviceRow.role`, `DeviceMap.turnouts`, the LCC alias tests); `check_hart_phase02.py` stays free of hartlib and reads `devices.csv` with `csv` (a main or upper "BS Switch" corner has the same role as an OS corner, so it keeps the name test, on staging rows only). The name-map readers still read the `pnm_*` columns, because the name map's comments (a block's area, a head's wiring) differ from the device map's; they go with the `pnm_*` columns in R9e. `apply_public_names*.py` and `sync_public_name_map.py` are already gone from the repo. R9e (2026-11-20): the three old files are deleted and no longer generated. The `pnm_*` columns stay, as the only copy of 236 staging rows' hardware ID, DCC address, control point and wiring comment; folding them into the master's columns is a later clean-up (loose ends below).

## Final state (2026-11-20, evening)

**Merged:**
- W3 #765, W5b #766, W1b #770, W2 #781;
- tests W4a #767, W4b #768, W4c #771;
- splits #772, #776, #777, #779 (W4b's USS generator not split while USS is parked, owner);
- CK1 deletion lnevo/sts-docker-helpers#12 with #778;
- decisions and ADR-029 #780, loose ends #784;
- W6b: three-way rule and `level_leg` faults lnevo/model-railroad-skills#81 with #785; band levels, crossover halves and the loop flag #787; `le_signal_boundaries.csv` retired #791;
- R9b #782, R9b-2 #790, R9c #795, R9e #800.

R9c is deployed to the Pi and Windows (7f2d3e26, `tables.xml` hash equal to the repo's), and the site is deployed after R9c and R9e.

**R9d was parked (owner, 2026-11-20); the redesign below replaced it.** The first pull split was on branch `agent/claude/r9d-store-split` (c3067931, deleted after #806 merged), with no PR. It passed the full check except one Linux test, now fixed but not rerun. A third review found these gaps:
- With no base, the split compares against the checkout as it stands, so a repo change made since the deploy can be reverted as an "owner edit".
- The refusal for an earlier Store that was never split in is never shown.
- `carry()` does not check that the carried edits land.
- `split_at` runs this checkout's hartlib over the deployed commit's files.
- An earlier-Store check failure can leave files written, and two messages are wrong.

The owner was offered a strict, simple split instead: split only when this checkout's `tables.xml` equals the host's base, otherwise refuse with the worktree command, with no carry-forward or second-Store mode. Until the redesign below is built, R9c's behaviour stands: a pull keeps the Store in `media/pulled-stores/` in the main checkout, records it as taken, and the edits go into `devices.csv` or the template by hand.

**R9d redesign (owner review, 2026-11-20).** It replaces both the parked branch and the strict split. A Store mostly holds non-device settings that must be kept, so the default is to keep, not to refuse:
1. **Keep the Store.** Everything outside the generated sections (settings, memories, the clock sensor, LogixNG the owner made, manager options) is taken from the normalised Store and becomes the new `tables_template.xml`, with no review.
2. **Repo wins on generated sections.** The `devices.csv` beans, the Layout Editor panel and its startup LogixNG, the Signal Mast Logic and the Digicon boot rule always come from the repo. A Store edit inside them is dropped, and the pull lists it for review with the source to change instead.
3. **Device facts are reviewed.** A Store difference from `devices.csv` (a rename, a comment, a new device) is reported, and the owner chooses merge or drop for each one. A clash where both the repo and the Store changed the same item since the deploy is reported the same way. The base, the host's deployed commit, only labels who changed what.
4. **Review in chat.** The agent running the pull asks merge-or-drop questions in batches of up to 4, with the before and after values, then applies the answers.
5. **Stop before commit.** The pull writes the template and the chosen `devices.csv` edits in a task worktree, rebuilds `tables.xml` and checks it, then stops. The agent or owner commits, and it merges through a PR as usual.
6. **Taken only after merge.** The Pi's Store counts as taken only once the split is merged, so deploys stay blocked until then. A later Store before that is cumulative (the Pi's file holds both sessions), so the pull always uses the newest Store.
7. **Build fresh.** A new, smaller tool, mostly for the Pi pull; the Mac pull uses the same code. It reuses the parked branch's normalising, comparison and rebuild check, and drops ROUTES' refusals and the carry-forward and earlier-Store modes. Delete the parked branch once it lands.

**Built (2026-11-20):** `hartlib.store_split` (the plan, the new template, the device edits, the rebuild check) and `tools/schematic/split_store.py` (report, `--show`, `--apply --plan FP --merge ... --drop ...`). The pulls keep the Store once per hash with `STORE.base` (`tools/hosts/pi/tables_base.sh`) and no longer record it as taken. A merged split's hash in `data/store_splits.csv` is what lets the deploy (`unpulled_changes.sh`, `profile_tables_unpulled`) replace the host's file. `read_template` now accepts an extra section a split kept (a Route table, say). Steps are in the `tables-pull` skill. Tried on a real PanelPro Store with one edit of each kind: the template took the memory, the clock rate and a Route section; a comment merged into `devices.csv`; a merged turnout rename was refused by the build (its FB rows follow the name) and every file was put back. Merged as #806. The review follow-ups (#807): a setting tag given more than once is matched by each copy's id, else by content; a Store from a newer JMRI always gives the template its `<jmriversion>`, an older one is listed; `store_splits.csv` is written inside the undo; a second pull of the same Store keeps its first base unless that was `none`; and a deploy whose commit shipped another file finds its base among the kept Stores.

**Not done from this hand-off:**
- W6b staging `le_labels` rules: **superseded and done** (branch `agent/claude/le-bands-by-level`, 2026-11-20). The owner decided on 2026-11-20 that Layout Editor label rules are defined by the preferences, each sheet's in its own section of `preferences.json`. Staging's rules (`extra_steps`, `extra_follow`, `name_columns`, `name_steps`, `lamp_columns`) were already only there, and the plugin's one reader (`le_labels.options`) reads them for every band, so they stay. `lamp_columns` stays too: it reserves room for the parked lamps before any label is placed, so removing it could move labels. The one look rule hard-coded in HART code, staging against the left edge of the three-level panel (`band_align={STAGING: "left"}` in `build_layout_le.py`), moved to `preferences.json[staging]` as `le_band_align: {"1": "left"}`, read by `le_common.le_band_align`. The owner's earlier note still holds: the rules change nothing on today's panel and pay off when main and upper get yards like these.
- The row 8 follow-up: **done** in the same branch. `le_common.STAGING` is gone, and bands are found by level and height (`below`) through `le_common.find_band`, `base_band` and `base_keys`. The callers are `le_names`, `build_layout_le`, `staging_device_map.staging_band` and `build_cats_panel.bound_index`. `band_key` is now the plugin's own `draw.band_key`, used only to key what is handed to the plugin.

## Carried from the archived hand-offs (2026-11-20)

These were still open when the older hand-offs went to `archive/wiki/projects/` ([`review-2026-11-19-handoff.md`](../../archive/wiki/projects/review-2026-11-19-handoff.md), [`architecture-followups-handoff.md`](../../archive/wiki/projects/architecture-followups-handoff.md)). Each is small and none is scheduled.

- **Hand-typed names, phases 2 and 3 (owner, 2026-11-14):** the desk, Layout Editor and wiring generators still hold some track, block and mast names typed by hand. They wait for the import of the main and upper levels. Phase 0 (`tools/audit/check_name_copies.py` in `check.sh`) and phase 1 are done.
- **`signal_number` at MP 6.6 and 6.7:** it gives 67/66 at MP 6.6 and 67/68 at MP 6.7, so two pairs a tenth apart share a westward name, and MP 9.8 westward returns 99 although the message says names stop at 98. Pinned by the `test_open_question_...` tests in `tools/schematic/tests/test_build_masts.py`. The staging signal rule decides it.
- **`sts_car_sync.py` reported a failed batch as saved:** fixed 2026-11-20. Stock `ThreadingUtil.runOnGUI` logs and drops an exception raised in the function it runs, so the worker's `on_gui` now catches it there and raises it again: the reply is `ok: false` with the batch id and names the cars already changed in memory (the next save writes them), and the batch is not saved. Tests in `jmri/layouts/hart/scripts/tests/test_sts_car_sync_worker.py`.
- **Redeploy runs the preflight twice:** kept on purpose (2026-11-20). The older commit's own ssh check closes the gap after the redeploy's check, so a host that drops in between still stops the run before the Pi step, and the hosts keep matching. It costs about a second.

## Loose ends from the 2026-11-20 run

Found while running this hand-off. Each is small. None blocks the R9 or W6b work.

- **`refresh_wiring_docs.py` would put old names back (closed 2026-11-20):** it and the v84 import are archived (`archive/tools-wiring/`); v86 is written from the repo's wiring source by `tools/wiring/write_inventory.py`, and v85 is frozen history.
- **`pnm_*` columns stayed (R9e, 2026-11-20; dropped 2026-11-21):** they are the only copy of 236 staging rows' hardware ID, DCC address, control point and wiring comment, so R9e kept them and retired only the three files. Folding them into the master's own columns (and dropping the `pnm_` names) is a later clean-up, after the level unification's step 6 (owner, 2026-11-20). Done 2026-11-21: they held no fact the master's own columns lacked but staging line blocks' station, now in `cp`, and Head 6LB's newer note, now in `notes`; every reader reads the real columns (source-data hand-off row 9).
- **Head comments can't be refreshed:** `refresh_bean_comments.py` writes head comments through `hartlib.devices.set_pnm_comments`, which changes hand-kept rows only. Every head row belongs to `build_masts.py` or `panel_items.json`, so a real comment change is refused, naming that script. Decided in R9b-2: `set_pnm_comments` lets a builder's row take the comment. `pnm_comment` is no builder's output (a builder rewrite carries the `pnm_` columns over from the row it replaces), so the change survives the next run and `written_by` stays. Tests hold both. When the `pnm_` columns go (R9e) the head wiring comment becomes the `wiring` column, written by `build_masts.py` from `wiring.csv`. Closed 2026-11-21: `set_pnm_comments` is gone; `build_masts.py` writes a wired head's `wiring` from `wiring.csv`, and `refresh_bean_comments.py` only checks that they agree.
- **`test_redeploy_commit` was flaky:** fixed in #803 (each run counts only the worktrees under its own TMPDIR).
- **Two switch-number tables:** fixed 2026-11-20; the full map takes `SWNUM` from `kit`, and a test holds it.
- **sts-docker docs named deleted scripts:** fixed in lnevo/sts-docker#22. The `track_scale/` folder at the sts-helpers root stays: its README lists it as a config reference.
- **Traps left by the splits (#772, #776, #777, #779):** constants re-exported on an entry module do not change the moved functions when a test patches them on the entry. Each entry has a comment naming the module to patch. The wiring entry also imports its sibling modules by bare name.
- **First live R9d split:** done 2026-11-20 on an owner test Store from the Pi (an audio source and turnout MTT120), in a test worktree, not merged; the Pi was then deployed with `HART_DISCARD_PI_CHANGES=1` (owner). The audio section went into the template and the rebuild check passed. The turnout was dropped, so the owner amended ADR-029: an added device becomes a level-less `devices.csv` row with its beans in `jmri_bean` (built 2026-11-20). MTT120 itself is the planned system name of main row `DCC Switch 101` (an LCC alias, DCC 120, still virtual), so the split names that row instead of adding a second. The three `IMSTS_CAR_SYNC_*` memories `sts_car_sync.py` makes at start-up are now in the template (#816). MTT120 stays a planned name; the owner uses unplanned names for test turnouts (not tracked).
- **Rollback after a split:** closed (owner, 2026-11-20). The rare case is covered by the deploy skill: `HART_DISCARD_PI_CHANGES=1` with the owner's yes.
- **`gen_ctc_track_plan.py` leftovers (parked):** bare `assert`s in `main()` and unclosed PIL images. Fix these if USS is unparked and the script is split.

## Done when

- Auto-merge is on.
- Every item above is merged, or stopped at an owner gate with its question asked.
- `wiki/STATUS.md` names whatever is still open.
- The close-out report lists, for each item, its PR number, the model that did it, whether a deploy happened, and the loose ends.

# Project health: hand-off (2026-11-20)

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
- **Screen sizes:** the owner's screen sizes (`le_window`, `cats_window`) in the committed preferences. Should they move to a host-local setting?
- **Band names and the 5 cm cut:** these sit in `main_upper.plan_overrides.json` `levels` "until B2". What is B2, and can they go now?

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

R9b is two PRs. R9b-1 (done): `jmri/layouts/hart/data/devices.csv` and its dictionary `devices.columns.csv` (`hartlib.devices`), the two device maps and `public_name_map.csv` generated from it and held byte-identical by `check.sh`, and the writers `build_staging_masts.py`, `build_device_map.py` and `panel_items.py` writing their own rows. `public_name_map.csv` lost its 416 alias rows and 25 retired identity rows. R9b-2: move the readers to the master (`railroad_facts` and `railroad_invariants` `DeviceMap`/`NameMap`, `level_devices`, `names`, `staging_device_map`, `build_layout_le`, `le_common`, `le_names`, `le_checks`, `build_signals`, `build_cats_panel`, `cats_panel_facts`, `cats_panel_levels`, `plan_lengths`, `sync_staging_signals`, `lcos_mqtt_mimic`, `cats_turnout_io`, `audit_panel_contracts`, `capture_public_name_baseline`, `layout_facts`, `check_layout_facts`, `check_name_copies`, `refresh_wiring_docs`, `add_main_upper_levels`, `build_layout_index`, `jmri_additions_page`, `check_hart_phase02`), retire `apply_public_names*.py` and `sync_public_name_map.py` (they read alias rows that are gone), then drop the `pnm_*` columns.

Each build PR runs `make panels CHECK=1`, the approval fingerprints rule and `make panelpro-test`. R9c and R9d change what the hosts load, so the coordinator:

1. pulls any live Store first (`make tables-pull-pi`);
2. deploys `--pi --win` after the merge;
3. confirms on the Mac that PanelPro and both CATS desks load the generated file.

None of this runs while the operating flag is set.

## Carried from the archived hand-offs (2026-11-20)

These were still open when the older hand-offs went to `archive/wiki/projects/` ([`review-2026-11-19-handoff.md`](../../archive/wiki/projects/review-2026-11-19-handoff.md), [`architecture-followups-handoff.md`](../../archive/wiki/projects/architecture-followups-handoff.md)). Each is small and none is scheduled.

- **Hand-typed names, phases 2 and 3 (owner, 2026-11-14):** the desk, Layout Editor and wiring generators still hold some track, block and mast names typed by hand. They wait for the import of the main and upper levels. Phase 0 (`tools/audit/check_name_copies.py` in `check.sh`) and phase 1 are done.
- **`signal_number` at MP 6.6 and 6.7:** it gives 67/66 at MP 6.6 and 67/68 at MP 6.7, so two pairs a tenth apart share a westward name, and MP 9.8 westward returns 99 although the message says names stop at 98. Pinned by the `test_open_question_...` tests in `tools/schematic/tests/test_build_staging_masts.py`. The staging signal rule decides it.
- **`sts_car_sync.py` line 239:** stock `ThreadingUtil.runOnGUI` logs and drops an exception raised off the GUI thread, so a failed batch answers `ok: true, saved: true`. Pinned as a known fault in `jmri/layouts/hart/scripts/tests/test_sts_car_sync_worker.py`; not fixed.
- **Redeploy runs the preflight twice** when the commit already has it (`tools/hosts/sync_hart_package.sh`, `redeploy_commit.sh`).
- **Main West turnback:** the owner's call, kept in `wiki/STATUS.md` under Owed.

## Done when

- Auto-merge is on.
- Every item above is merged, or stopped at an owner gate with its question asked.
- `wiki/STATUS.md` names whatever is still open.
- The close-out report lists, for each item, its PR number, the model that did it, whether a deploy happened, and the loose ends.

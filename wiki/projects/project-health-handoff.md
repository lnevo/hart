# Project health: hand-off (2026-11-20)

Comes from the 2026-11-20 quick review of open fixes, workflow and where facts are kept. The owner made these choices on 2026-11-20:

- Source-data rows 8 and 10 are included, as proposals the owner reviews before anything is built.
- GitHub auto-merge is turned on.
- The large scripts get tests, then a split.
- File moves are proposed first and made after the owner approves.

Row 9 (device facts kept three times) is **not** in this hand-off yet. The owner wants to discuss it first, and it is added under [Row 9](#row-9-device-facts-held) afterwards.

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

1. Turn on auto-merge with `gh repo edit lnevo/hart --enable-auto-merge`. The owner approved this on 2026-11-20. Confirm it with `gh repo view lnevo/hart --json autoMergeAllowed`.
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

## Row 9: device facts (held)

Waiting on the owner's discussion. The coordinator adds the agreed plan here before the final hand-off goes out. Background: row 9 in [`source-data-exceptions-handoff.md`](source-data-exceptions-handoff.md).

## Done when

- Auto-merge is on.
- Every item above is merged, or stopped at an owner gate with its question asked.
- `wiki/STATUS.md` names whatever is still open.
- The close-out report lists, for each item, its PR number, the model that did it, whether a deploy happened, and the loose ends.

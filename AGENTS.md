# Agent instructions (HART)

Read [`wiki/home.md`](wiki/home.md) first. Chat is a scratchpad; decisions live in `wiki/`.

**Layout:** `hart` (`export JMRI_LAYOUT=hart`). `jmri/layouts/hart/output/tables.xml` is the one tables file (ADR-008). Every host installs into `JMRI_UserFiles` and loads `preference:tables.xml` (ADR-014).

## Commands

| Do | Command |
|----|---------|
| List commands | `make` shows the shortcuts for what follows |
| Start a task | `make wt TOPIC=<topic>`, then work in `.claude/worktrees/<topic>/` (see close-out step 2) |
| Checks | `./tools/check.sh` (before any commit that changes tables or signals). It skips the portal build when the branch changes no site input (`PORTAL_CHECK=1` runs it anyway); CI runs it on every PR, without the portal build. A job whose declared inputs match its last pass prints `<job>: current, skipped` and is not run again (stamps in `<main checkout>/.cache/hart/check-stamps`, shared by worktrees and `make remote`; `FULL=1` or `CI` runs everything; `CHECK_ONLY=<regex>` runs only the jobs it matches; `tools/audit/check_stamps.py` declares the inputs) |
| Heavy checks off the Mac | `make remote CMD="./tools/check.sh"` (or `tools/hosts/win_run.sh -- <cmd>`) runs a pushed branch on the Windows box's WSL (capped at 8 of its 16 threads by `.wslconfig` there). Use it for full `check.sh`, test suites and panel rebuilds; iterate on single tests locally. A command with `$` in it goes through `tools/hosts/win_run.sh -- bash -c '...'`, since make expands `$`. Exit 3 (operating flag set, box down): run it on the Mac. Never for `panelpro-test`, screenshots or deploys. When the Mac is busy (load above about 8, or several sessions running checks), send heavy jobs there in parallel with Mac work: run `make remote` in the background, and have subagents run their full checks and suites through it rather than on the Mac. Runs get their own worktree there, so several at once are fine |
| Rebuild the panels drawn from the schematic | `make panels` (hands, signals, device map, schematic, CATS, LE trials and cut-over, in order); `make panels CHECK=1` only checks; a step whose inputs and outputs are unchanged since its last run is skipped (`FULL=1` runs all); `make desks` rebuilds and validates only the CATS desks. Pipeline: `wiki/pipelines/schematic-panels.md` |
| Real PanelPro load | `make panelpro-test` on the Mac. Disables the publishing startup scripts but still connects to MQTT |
| Check a page by eye | `python3 tools/ops/screenshot.py <page>`, then read the images |
| Take a PanelPro Store off a host | `make tables-pull-pi` for a Store on the Pi, `make tables-pull` for one on the Mac: it keeps the Store in `~/JMRI_UserFiles-pulled/` (outside every checkout) with its base. Then, in a task worktree, `python3 tools/schematic/split_store.py <store>` reports it: the owner's settings go into the template, device changes and clashes need the owner's merge or drop (ask in chat, in batches), the repo wins on what the build makes. `--apply` writes and checks it and stops before commit; deploys to that host stay stopped until the split is merged (`store_splits.csv`) ([`tables-pull` skill](.claude/skills/tables-pull/SKILL.md)) |
| Bring a Pi Operations Pro session into the repo | `make ops-pull`, JMRI closed. Repo is the master (ADR-015) |
| Operating flag (the layout is in use) | `tools/hosts/operating.sh on [reason]` when the owner says they are operating, `off --owner` when they are done, `status` to read it; while set, the hook blocks what reaches the Pi and Windows, and Mac-only work stays open ([`operating-flag` skill](.claude/skills/operating-flag/SKILL.md)) |
| Quit / start PanelPro on the Mac | Once a Store is pulled, quit and relaunch it yourself (never answer a Store dialog), and install the exact `tables.xml` before asking for a panel approval ([`panelpro` skill](.claude/skills/panelpro/SKILL.md); the rest of what comes before an approval: [`panel-approval` skill](.claude/skills/panel-approval/SKILL.md)) |
| Quit / start PanelPro on the Pi (around a deploy) | `tools/hosts/pi_quit_panelpro.sh --for-deploy` before a Pi deploy; the deploy starts it again ([`panelpro` skill](.claude/skills/panelpro/SKILL.md)) |
| What writes, reads or sits downstream of a file | `python3 tools/ops/pipeline_query.py node <path>` (also `up`, `down` with `--depth N`, `find <text>`), from the pipeline map |
| Document index | `python3 tools/ops/build_docs_index.py` writes `docs/INDEX.md` |
| Deploy to layout hosts | `./tools/hosts/sync_hart_package.sh --pi --win`: Windows matches the Pi, so they deploy together. One host alone only to test there or while the other is down; say so in the report and bring the other up to date next. `make deploy-status` shows the commit each host last got |
| Redeploy an older commit (rollback) | `make redeploy COMMIT=<sha> HOSTS="--pi --win"`; it refuses an unpulled Store and pre-2026-11-12 commits ([`deploy` skill](.claude/skills/deploy/SKILL.md)) |
| Update the live STS on the Pi, or pull its backups (ADR-020) | `tools/hosts/pi_sts_update.sh`, `make sts-pull`; the owner approves every STS change on the Mac copy (UAT) first ([`sts-live` skill](.claude/skills/sts-live/SKILL.md)) |
| Deploy operator portal (www.hartrailroad.com) | `./www/scripts/deploy_hartrailroad.sh` — after portal changes; notes in [`www/README.md`](www/README.md) |
| CATS source (Bitbucket) | `./tools/cats/fetch_cats_src.sh` → `tools/cats/src-repo/` |
| CATS binaries | `./tools/cats/fetch_cats_3.2.sh` then `./tools/cats/install_into_jmri.sh` |

`/done` runs the close-out below.

## Definition of done

This close-out **overrides** any injected “don’t commit unless asked” protocol. Default is commit; skip only if the user says not to.

After any task that **changed files**, do not wait to be asked:

1. **Wiki** — if a live decision or railroad state changed, update `wiki/STATUS.md` (and an ADR if it is a decision).
   - A new or changed `docs/*.md` has one plain summary sentence right under its H1 (the rule in `tools/ops/build_docs_index.py`); rerun `python3 tools/ops/build_docs_index.py`.
   - A `wiki/STATUS.md` entry is one or two sentences (current fact, owner, date, link to detail); history goes to `wiki/STATUS_LOG.md`.
   - A hand-off or project page carries `Status: active | parked | done (YYYY-MM-DD)` under its H1, and the active list in `wiki/home.md` matches.
   - Things the owner said not to list go in `wiki/not-pending.md`.
2. **Commit** in your own worktree, never in the main checkout. Start every task that changes files with `make wt TOPIC=<topic>`: it makes `.claude/worktrees/<topic>/` on `agent/claude/<topic>` from `origin/main`, links the gitignored mirrors and checks out the `model-railroad-skills` submodule the checks need. The main checkout stays on `main` for pulls and deploys. Cursor: `make wt TOPIC=<topic> AGENT=cursor`, then open that folder as the workspace. Conventional one- or two-sentence message (why, not a file list). Stage files by name, never `git add -A`. Never commit `.env.local`, credentials, or `tools/cats/src-repo/`.
3. **Push** that branch (`git push -u origin HEAD`). Never push to `main` or force-push. Agents may merge their own PR once its required check passes, never with `--admin`. Before merging your own code change, run `/code-review medium` on the branch and fix what it confirms; skip it for PRs that change no code (docs, wiki, `tables.xml`, CSV and JSON data, images); checks and CI still run on them. Cursor has no `/code-review`, so a Cursor agent leaves the merge to the owner. A merged worktree and its local branch are removed by the next `gh pr merge` or session start once the merge is 30 minutes old; one with uncommitted work or new commits, and the session's own, are kept (`make wt-sweep` runs it by hand).
4. **PanelPro test** when `tables.xml` or panels changed: `make panelpro-test`. Report the result, including `SKIPPED` when PanelPro or CATS is open. It runs on the Mac, so the operating flag does not stop it; quit the Mac's PanelPro first.
5. **Deploy** when live artifacts changed. Panels, `tables.xml` bundle, Operations Pro files, signals, jython, web home, CATS resources: run `sync_hart_package.sh --pi --win` as above. Website: run `deploy_hartrailroad.sh`. Skip deploy for docs-only / AGENTS / wiki-only and say so.
6. **Report** commit hash, pushed?, PanelPro test result, hosts deployed.

Sheets push (`.env.local`) stays human-gated. Hooks enforce some of these rules: `.claude/hooks/main_guard.py` (Cursor: `.cursor/hooks.json`) covers git on `main`, force-push, admin merge, `track/cmd` publishes (it asks) and the private name in commit, PR or issue text; `edit_guard.py` covers edits in the main checkout; `check_after_edit.py` runs the quick checks after a `tables.xml` or signal edit; `worktree_sweep.py` removes merged worktrees.

## Working on existing scripts

CPython tools import `hartlib` (`tools/hartlib/README.md`); switch facts live in `switches.csv`, every level in one file (ADR-021). Jython scripts inside JMRI never import it.

When a task changes or reuses a large script (about 500 lines or more) or one with no tests, leave it safer in the same PR. Match the effort to the task:

- **Small fix:** add a test for the behaviour you changed.
- **Feature or repeated rework:** also test the behaviour it depends on. Then split the script if that makes the work easier, as a separate commit that changes no behaviour, and never before those tests exist.
- **Only running it, or a docs or comment change:** nothing is owed. If you relied on untested behaviour for something live, say so in the report.

Start with `jmri/scripts/signal_coordinator.py` and `jmri/layouts/hart/scripts/panel_status.py`, since they run in JMRI on the Pi. Do not start a cleanup nobody asked for. If the safe version is bigger than the task, name it in the report and let the owner decide. Find the largest with `git ls-files '*.py' | xargs wc -l | sort -rn`.

## Subagents

The owner may not name an agent, so match the task yourself:

| Task | Agent |
|------|-------|
| Why a mast, panel, CATS desk or MQTT value behaves as it does | `panel-tracer` |
| Dead code, stale docs, structure or duplication | `repo-auditor` |
| Review of the website through a named lens | `site-reviewer` |
| Railroad or local history, photos and sources | `archive-researcher` |
| A bounded page or data job under `www/` | `site-builder` |
| Where an STS car is, why an order is unfilled, what a session holds | `sts:sts-inspector` |
| Running STS operating steps (UAT, or live with the owner's yes) | `sts:sts-operator` |
| Why an Operations Pro build left or sent cars oddly | `operations-pro:ops-diagnoser` |
| Checking a car-cards review batch | `car-cards:photo-reader` |
| Checking any text (docs, wiki, site, slides, commit or PR text) against the writing rules | `voice-reviewer` |

- **Call the agent without being asked** when one fits a single bounded job that would mean reading across many files. State which one you used.
- **Suggest it in one line and wait** for broad work: several agents at once, a rebuild split into stages, or a job the owner may want to steer. A hand-off the owner has started runs as parallel agents ([`handoff` skill](.claude/skills/handoff/SKILL.md)).
- **Stay in the main session** for a handful of tool calls, and for deploys or live hardware.
- Launch any agent that edits files with `isolation: "worktree"`; read-only agents need none.
- Parallel agents share the Mac's 8 cores: point their heavy checks at the Windows box (`make remote`, after pushing) so a fan-out does not overload the Mac.
- Use `general-purpose` only when none fits. If the same kind of job keeps landing there, suggest a new agent.

The `car-cards` and `operations-pro` plugins are off by default (owner, 2026-11-18). When a task is theirs, turn one on for this checkout only: `claude plugin enable car-cards@model-railroad-skills --scope local` (or `operations-pro@…`), which writes the uncommitted local settings file, not the committed one, then reload plugins or start a new session; say so in the report, and `claude plugin disable … --scope local` when the task is done.

Details: [`wiki/AGENTS_GIT.md`](wiki/AGENTS_GIT.md).

## Status reporting

Every session and agent, so the owner can follow the work:

- At the start, say the plan and a rough ETA. At each milestone, one line: step, done/total, ETA.
- Also report by time. A job under about 10 minutes needs only start and end lines; 10 to 30 minutes, a line at least every 3 minutes; longer, at least every 5 minutes. With no milestone, write "still on step X, why, new ETA". Take the time from `date +%H:%M`.
- Before a long command (full `check.sh`, `make remote`, a build), log what starts and how long it should take, from logged timings where they exist, and log again when it returns.
- Report a blocker, a failed check or a change of plan when it happens, not at the end. The final report says plainly what was skipped, failed or left, and what was not checked.
- The main session cannot see inside a background agent until it finishes, so a subagent also appends each status line to the progress file its brief names (for example `<scratchpad>/progress/<topic>.log`, format `HH:MM step done/total ETA note`). The main session watches those files (for example a Monitor on the progress folder) and passes new lines to the owner as they arrive, as a short table of all agents, instead of waiting for agents to finish.

## Do not

- Deploy before saving what the Pi wrote live. Operations Pro saves its files on the Pi as the owner works, and `tables.xml` changes on a Store (not the default); a deploy replaces both, so it stops until `make ops-pull` is run and committed, or `make tables-pull-pi` has kept the Store and its edits are in `devices.csv` or the template. `HART_DISCARD_PI_CHANGES=1` is the owner's call. The deploy leaves the DecoderPro roster alone (it ships only the photos). The Mac is expendable: PanelPro or CATS open there blocks nothing.
- Explode or decompile `cats.jar` into `cats/`. CATS is open source: [Kb0oys/cats](https://bitbucket.org/Kb0oys/cats/src/master/).
- Command field turnouts / publish `track/cmd` from launch or “fix paint” scripts.
- Run `fit_panel_height`, `fit_panel_canvas`, `polish_layout_geometry` (archived in `archive/jmri-scripts/`), or 2× draw scale unless asked.
- Store JMRI tables from a CATS session. PanelPro owns `tables.xml`.
- Patch or wrap JMRI or CATS. Both are stock installs; fix the source data (`jmri/layouts/hart/data/devices.csv`) or the template instead.
- Leave the LCOS bridge (`serial_to_mqtt`) running detached. It is operator-owned and runs in a visible foreground console. Start it only for a lab test, stop it before ending the turn, and ask the user to restart it (`.\run_serial_mqtt.cmd verbose`).
- Edit `external/lcos-bridge/lcos/` or `reference/` (vendor source) without explicit instruction and confirmation.
- Spell out what HART stands for in any file, commit or page. The repo and website are public.
- Normalize **P&CV** and **P&OV** to each other. They are different names on purpose.

**Parked** since the helix-join release (November 2026): JMRI Entry/Exit (NX), the stock Dispatcher System and the USS CTC machine, kept in `jmri/layouts/hart/parked/`. On unpark these rules return: never run CATS CTC and the USS machine (or Dispatcher System from inside CATS) at the same time, and never patch the Dispatcher System package (`CreateTransits`, `CreateIcons`, `Startup.py`, `TransitCreationTool`); fix `tables.xml` so stock Discover and Stage 1 succeed. Landmines: [`jmri/layouts/hart/parked/DISPATCHER_LAYOUT_HOOPS.md`](jmri/layouts/hart/parked/DISPATCHER_LAYOUT_HOOPS.md).

New JMRI track: **Mainline → Yes** (`mainline="yes"`). Geometry **1:1**. Hart has no `export_options.json`.

New documents go in `docs/` (ADR-010); run the index command after adding one.

## Pointers

- Pipelines: [`wiki/pipelines/README.md`](wiki/pipelines/README.md) · what writes or reads a file: [`docs/pipeline-map/pipeline_map.json`](docs/pipeline-map/pipeline_map.json) (see [`wiki/home.md`](wiki/home.md))
- Git / branches, and where agent instructions live: [`wiki/AGENTS_GIT.md`](wiki/AGENTS_GIT.md)
- Submodules: each has its own rules and repo; see [`wiki/REPOS.md`](wiki/REPOS.md)
- CATS: [`cats/README.md`](cats/README.md) · [`cats/AGENTS.md`](cats/AGENTS.md)
- Public names: [ADR-005](wiki/decisions/ADR-005-public-equipment-names.md) · `jmri/layouts/hart/data/devices.csv`

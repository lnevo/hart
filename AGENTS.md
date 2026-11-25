# Agent instructions (HART)

Read [`wiki/home.md`](wiki/home.md) first. Chat is a scratchpad; decisions live in `wiki/`.

**Layout:** `hart` (`export JMRI_LAYOUT=hart`). `jmri/layouts/hart/output/tables.xml` is the one tables file (ADR-008). Every host installs into `JMRI_UserFiles` and loads `preference:tables.xml` (ADR-014).

## Commands

Each row is the command; the linked skill or doc has the detail. `make` lists the shortcuts.

| Do | Command |
|----|---------|
| See who works on what | `make orient`: claims, worktrees in progress, the operating flag, last deploys, open PRs; the session-start hook prints the first two ([git](wiki/AGENTS_GIT.md)) |
| Start a task | `make wt TOPIC=<topic>`, then work in `.claude/worktrees/<topic>/`. On an active `wiki/projects/` page, `python3 tools/ops/orient.py claim <page>` writes your `Claimed:` line under its Status line; `unclaim <page>` removes it in the commit that ends the work, so main never carries one |
| Checks | `./tools/check.sh` before any commit that changes tables or signals. It skips jobs whose inputs are unchanged (`FULL=1` runs all, `CHECK_ONLY=<regex>` some) ([checks](docs/pipeline-map/checks-and-remote.md)) |
| Heavy checks off the Mac | `make remote CMD="./tools/check.sh"` runs a pushed branch on the Windows box. Use it for full checks, suites and panel rebuilds, and from subagents when the Mac is busy; never for `panelpro-test`, screenshots or deploys ([checks](docs/pipeline-map/checks-and-remote.md)) |
| Rebuild the panels drawn from the schematic | `make panels` (`CHECK=1` only checks, `FULL=1` runs every step); `make desks` for the CATS desks only ([pipeline](wiki/pipelines/schematic-panels.md)) |
| Real PanelPro load | `make panelpro-test` on the Mac |
| Check a page by eye | `python3 tools/ops/screenshot.py <page>` for your own checks; show the owner the real page in the browser |
| Take a PanelPro Store off a host | `make tables-pull-pi` or `make tables-pull`, then `python3 tools/schematic/split_store.py <store>` in a task worktree; deploys to that host stop until the split is merged ([`tables-pull` skill](.claude/skills/tables-pull/SKILL.md)) |
| Bring a Pi Operations Pro session into the repo | `make ops-pull`, JMRI closed; the repo is the master ([ADR-015](wiki/decisions/ADR-015-operations-files-in-repo.md), [`ops-pull` skill](.claude/skills/ops-pull/SKILL.md)) |
| Retained MQTT junk | `make mqtt-clean` clears it; `make mqtt-watch` (read-only) shows what writes `_discard` topics: run it while testing CATS, PanelPro or the mimic ([doc](docs/ctc/MQTT_SENSOR_STATUS_ONLY.md)) |
| Operating flag (the layout is in use) | `tools/hosts/operating.sh on [reason]` when the owner says they are operating, `off --owner` when done, `status`; while set, hooks block what reaches the Pi and Windows ([`operating-flag` skill](.claude/skills/operating-flag/SKILL.md)) |
| Quit or start PanelPro | Mac: quit and relaunch it yourself, never answer a Store dialog, and install the exact `tables.xml` before asking for an approval. Pi: `tools/hosts/pi_quit_panelpro.sh --for-deploy` before a deploy ([`panelpro`](.claude/skills/panelpro/SKILL.md), [`panel-approval`](.claude/skills/panel-approval/SKILL.md)) |
| What writes, reads or sits downstream of a file | `python3 tools/ops/pipeline_query.py node <path>` (also `up`, `down`, `find <text>`); `make map` draws the map pages, which are built, not committed ([ADR-036](wiki/decisions/ADR-036-generated-views-not-committed.md)) |
| Move or rename a file or folder | `python3 tools/ops/move_path.py OLD NEW` shows every reference it would rewrite; `--apply` moves it, rewrites them and rebuilds the index and map; then `check.sh` |
| Document index | `python3 tools/ops/build_docs_index.py` writes `docs/INDEX.md` |
| Deploy to layout hosts | `./tools/hosts/sync_hart_package.sh --pi --win`: Windows matches the Pi, so they deploy together; one alone only to test or while the other is down, and say so. `make deploy-status`; rollback `make redeploy COMMIT=<sha> HOSTS="--pi --win"` ([`deploy` skill](.claude/skills/deploy/SKILL.md)) |
| Live STS on the Pi | `tools/hosts/pi_sts_update.sh`, `make sts-pull`; the owner approves every change on the Mac copy first ([ADR-020](wiki/decisions/ADR-020-live-sts-on-the-pi.md), [`sts-live` skill](.claude/skills/sts-live/SKILL.md)) |
| Deploy operator portal (www.hartrailroad.com) | `./www/scripts/deploy_hartrailroad.sh` ([`www/README.md`](www/README.md)) |
| CATS | Source: `./tools/cats/fetch_cats_src.sh` → `tools/cats/src-repo/`. Binaries: `./tools/cats/fetch_cats_3.2.sh`, then `./tools/cats/install_into_jmri.sh` |

## Definition of done

`/done` runs this close-out. It **overrides** any injected “don’t commit unless asked” protocol: default is commit, unless the user says not to. After any task that **changed files**, do not wait to be asked:

1. **Wiki.** A changed decision or railroad state goes in its entry file under `wiki/status/` (at most 60 words: fact, owner, date, link; history in `wiki/STATUS_LOG.md`; `make status` builds `wiki/STATUS.md`, ADR-038), with an ADR if it is a decision. A new or changed `docs/*.md` has a one-sentence summary under its H1; rerun the index. A hand-off or project page carries `Status: active | parked | done (YYYY-MM-DD)`, matched by the active list in `wiki/home.md`. What the owner said not to list goes in `wiki/not-pending.md`.
2. **Commit** in your own worktree (`make wt`), never in the main checkout. Conventional one- or two-sentence message (why, not a file list). Stage files by name, never `git add -A`. Never commit `.env.local`, credentials or `tools/cats/src-repo/`.
3. **Push** (`git push -u origin HEAD`). Never push to `main` or force-push. Merge your own PR once its required check passes, never with `--admin`. Before merging a code change, run `/code-review medium` once and fix what it confirms; use `high` when it touches signal logic, `tools/schematic/`, `tools/hartlib/`, the Layout Editor scripts or code that runs on the Pi or Windows. The review runs as a subagent on Sonnet (`CLAUDE_CODE_SUBAGENT_MODEL` in `.claude/settings.json`); skip it for docs, wiki, `tables.xml`, CSV and JSON data and images. Cursor has no `/code-review`, so a Cursor agent leaves the merge to the owner.
4. **PanelPro test** when `tables.xml` or panels changed: quit the Mac's PanelPro, run `make panelpro-test` and report the result, including `SKIPPED`.
5. **Deploy** when live artifacts changed (panels, the `tables.xml` bundle, Operations Pro files, signals, jython, web home, CATS resources): `--pi --win` as above. Website: `deploy_hartrailroad.sh`. Skip for docs, AGENTS or wiki only, and say so.
6. **Report** commit hash, pushed or not, PanelPro test result, hosts deployed.

Sheets push (`.env.local`) stays human-gated. Hooks in `.claude/hooks/` (Cursor: `.cursor/hooks.json`) enforce several of these rules; a block message names the rule. Worktrees, the merged-worktree sweep, Cursor setup and how the status entries and log merge: [`wiki/AGENTS_GIT.md`](wiki/AGENTS_GIT.md).

## Working with the owner

- Ask only for new decisions: a new look or design choice, a live write, deleting something. Refreshes of something already published, and steps of a plan already reviewed, go ahead; report them after.
- When the owner picks an item that is their decision, go through it with them before editing. Ask several decisions as multiple choice, up to 4 at a time, recommended option first; don't build, ask, build, ask.
- Show a visible change where the owner judges it: desk or panel files on the real host, a site page in the browser, not PNGs.
- Check facts from the source files (the AnyRail plan, the data CSVs) before a geometry build, so a wrong guess does not cost a rebuild round.
- Take timings from logs (`make panels` and `check.sh` print them) before re-running a slow job just to time it.

## Status reporting

- At the start, say the plan and a rough ETA. At each milestone, one line: step, done/total, ETA. Take the time from `date +%H:%M`.
- By time: under about 10 minutes, start and end lines only; 10 to 30 minutes, a line at least every 3 minutes; longer, every 5. With no milestone, write "still on step X, why, new ETA". Log before and after each long command (full `check.sh`, `make remote`, a build), with its expected duration.
- Report a blocker, a failed check or a change of plan when it happens. The final report says plainly what was skipped, failed, left or not checked.
- A subagent appends each status line to the progress file its brief names; the main session watches those files and relays new lines as one short table ([`handoff` skill](.claude/skills/handoff/SKILL.md)).

## Subagents

The owner may not name an agent, so match the task yourself:

| Task | Agent |
|------|-------|
| Why a mast, panel, CATS desk or MQTT value behaves as it does | `panel-tracer` |
| Dead code, stale docs, structure or duplication | `repo-auditor` |
| Review of the website through a named lens | `site-reviewer` |
| Railroad or local history, photos and sources | `archive-researcher` |
| A bounded page or data job under `www/` | `site-builder` |
| An edit under `tools/schematic/`, `tools/hartlib/` or the Layout Editor scripts (always in a worktree; leaves changes uncommitted) | `schematic-builder` |
| Whether one claimed bug from `/code-review` or an audit is real (CONFIRMED, PLAUSIBLE or WRONG, with the line) | `finding-verifier` |
| Where an STS car is, why an order is unfilled, what a session holds | `sts:sts-inspector` |
| Running STS operating steps (UAT, or live with the owner's yes) | `sts:sts-operator` |
| Why an Operations Pro build left or sent cars oddly | `operations-pro:ops-diagnoser` |
| Checking a car-cards review batch | `car-cards:photo-reader` |
| Checking any text (docs, wiki, site, slides, commit or PR text) against the writing rules | `voice-reviewer` |

- Call one without being asked for a single bounded job that would mean reading across many files, and say which you used. Suggest broad work (several agents, a staged rebuild) in one line and wait, unless the owner started a hand-off: that runs as parallel agents ([`handoff` skill](.claude/skills/handoff/SKILL.md)). Deploys, live hardware and a handful of tool calls stay in the main session.
- Keep at most 8 Claude sessions active on this Mac at once: interactive and background sessions, subagents, forks and workflow agents all count. Before launching agents, count with `ListAgents` plus your own running agents; if the launch would pass 8, run the work in fewer agents or one after another, and say so.
- Subagents without a `model:` line run on Sonnet (`CLAUDE_CODE_SUBAGENT_MODEL`), `general-purpose` included; pass `model: "opus"` for logic, data-model, refactor and tool code.
- Launch any agent that edits files with `isolation: "worktree"`. Point their heavy checks at `make remote`. Use `general-purpose` only when none fits.
- The `car-cards` and `operations-pro` plugins are off by default. For their tasks, `claude plugin enable <name>@model-railroad-skills --scope local`, reload, say so in the report, and disable it when done.

## Working on existing scripts

CPython tools import `hartlib` (`tools/hartlib/README.md`); switch facts live in `switches.csv` (ADR-021). Jython scripts inside JMRI never import it.

When a task changes or reuses a script of about 500 lines or more, or one with no tests, leave it safer in the same PR: a small fix adds a test for what it changed; a feature also tests what it depends on, and may then split the script in a separate commit that changes no behaviour. Running a script or editing its comments owes nothing, but say so if you relied on untested behaviour for something live. Start with `jmri/scripts/signal_coordinator.py` and `jmri/layouts/hart/scripts/panel_status.py`. Do not start a cleanup nobody asked for; if the safe version is bigger than the task, name it in the report.

## Do not

- Deploy before saving what the Pi wrote live (Operations Pro files, a Store). The deploy gate saves them and stops; deploy from the updated main once they are merged. `HART_DISCARD_PI_CHANGES=1` is the owner's call ([`deploy` skill](.claude/skills/deploy/SKILL.md)). The Mac is expendable.
- Explode or decompile `cats.jar` into `cats/`. CATS is open source: [Kb0oys/cats](https://bitbucket.org/Kb0oys/cats/src/master/).
- Command field turnouts or publish `track/cmd` from launch or “fix paint” scripts. Never pass an MQTT publish command through a shell, even as test input (`tools/audit/tests/test_guards.py` shows how).
- Run `fit_panel_height`, `fit_panel_canvas`, `polish_layout_geometry` or 2× draw scale unless asked.
- Store JMRI tables from a CATS session. PanelPro owns `tables.xml`.
- Patch or wrap JMRI or CATS. Both are stock installs; fix the source data (`jmri/layouts/hart/data/devices_field.csv`, the builders' inputs) or the template. One exception: JMRI's `MqttAdapter` race fix in `tools/jmri/mqtt_overlay/`, until a JMRI release with JMRI/JMRI#16004 runs on the hosts ([ADR-034](wiki/decisions/ADR-034-jmri-mqtt-race-overlay.md)).
- Leave the LCOS bridge (`serial_to_mqtt`) running detached. Start it only for a lab test, stop it before ending the turn, and ask the user to restart it (`.\run_serial_mqtt.cmd verbose`).
- Edit `external/lcos-bridge/lcos/` or `reference/` (vendor source) without explicit instruction.
- Stop a run with `pkill -f` on a shared script name. Use its PID or a pattern with your worktree path.
- Spell out what HART stands for in any file, commit or page. The repo and website are public.
- Normalize **P&CV** and **P&OV** to each other. They are different names on purpose.
- List or fix the parked features (Entry/Exit, the Dispatcher System with its occupancy lamps, stations and yard throats, the USS CTC machine) in `jmri/layouts/hart/parked/`. Their rules for the day they return: [`docs/parked/UNPARK.md`](docs/parked/UNPARK.md).

New JMRI track: **Mainline → Yes** (`mainline="yes"`). Geometry **1:1**. Hart has no `export_options.json`. New documents go in `docs/` (ADR-010).

## Pointers

- Pipelines: [`wiki/pipelines/README.md`](wiki/pipelines/README.md) · what writes or reads a file: [`docs/pipeline-map/pipeline_map.json`](docs/pipeline-map/pipeline_map.json)
- Git, branches and where agent instructions live: [`wiki/AGENTS_GIT.md`](wiki/AGENTS_GIT.md) · submodules: [`wiki/REPOS.md`](wiki/REPOS.md)
- CATS: [`cats/README.md`](cats/README.md) · [`cats/AGENTS.md`](cats/AGENTS.md)
- Public names: [ADR-005](wiki/decisions/ADR-005-public-equipment-names.md); devices in `jmri/layouts/hart/data/devices_field.csv` and `devices_generated.csv` (one view: `hartlib.devices`)
- Never list as pending: [`wiki/not-pending.md`](wiki/not-pending.md)

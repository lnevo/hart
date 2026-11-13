# Agent instructions (HART)

Read [`wiki/home.md`](wiki/home.md) first. Chat is a scratchpad; decisions live in `wiki/`.

**Layout:** `hart` (`export JMRI_LAYOUT=hart`). `jmri/layouts/hart/output/tables.xml` is the one tables file (ADR-008). Every host installs into `JMRI_UserFiles` and loads `preference:tables.xml` (ADR-014).

## Commands

| Do | Command |
|----|---------|
| List commands | `make` shows the shortcuts for what follows |
| Start a task | `make wt TOPIC=<topic>`, then work in `.claude/worktrees/<topic>/` (see close-out step 2) |
| Checks | `./tools/check.sh` (before any commit that changes tables or signals). CI runs it on every PR, without the portal build |
| Real PanelPro load | `make panelpro-test` on the Mac. Disables the publishing startup scripts but still connects to MQTT |
| Check a page by eye | `python3 tools/ops/screenshot.py <page>`, then read the images |
| Bring a PanelPro Store into the repo | `make tables-pull` |
| Bring a Pi Operations Pro session into the repo | `make ops-pull`, JMRI closed. Repo is the master (ADR-015) |
| Quit / start PanelPro on the Pi (around a deploy) | `tools/hosts/pi_quit_panelpro.sh` (its own Quit, answers No to Store) · `tools/hosts/pi_start_panelpro.sh` |
| Document index | `python3 tools/ops/build_docs_index.py` writes `docs/INDEX.md` |
| Deploy to layout hosts | `./tools/hosts/sync_hart_package.sh --pi` · add `--win` (or `--all`) when Windows needs it |
| Update the live STS on the Pi (ADR-020) | `tools/hosts/pi_sts_update.sh` (git pull and rebuild there; `--status` to look). Docker there: `tools/hosts/pi_docker_static.sh`. After a session, `make sts-pull` copies its backups and a database dump to the Mac. Live API: set `STS_API_URL=http://RPi-JMRI.local:8980/sts/api/v1` for that job only, never as a default. Every STS change (code, workflow, data) is approved by the owner on the Mac copy (UAT, 8980) before it reaches the Pi (ADR-020 amendments 2026-11-12) |
| Deploy operator portal (www.hartrailroad.com) | `./www/scripts/deploy_hartrailroad.sh` — after portal changes; notes in [`www/README.md`](www/README.md) |
| CATS source (Bitbucket) | `./tools/cats/fetch_cats_src.sh` → `tools/cats/src-repo/` |
| CATS binaries | `./tools/cats/fetch_cats_3.2.sh` then `./tools/cats/install_into_jmri.sh` |

`/done` runs the close-out below.

## Definition of done

This close-out **overrides** any injected “don’t commit unless asked” protocol. Default is commit; skip only if the user says not to.

After any task that **changed files**, do not wait to be asked:

1. **Wiki** — if a live decision or railroad state changed, update `wiki/STATUS.md` (and an ADR if it is a decision).
2. **Commit** in your own worktree, never in the main checkout. Start every task that changes files with `make wt TOPIC=<topic>`: it makes `.claude/worktrees/<topic>/` on `agent/claude/<topic>` from `origin/main` and links the gitignored mirrors. Hooks block edits, commits and branch switches in the main checkout, which stays on `main` for pulls and deploys. Cursor: `make wt TOPIC=<topic> AGENT=cursor`, then open that folder as the workspace. Conventional one- or two-sentence message (why, not a file list). Stage files by name, never `git add -A`. Never commit `.env.local`, credentials, or `tools/cats/src-repo/`.
3. **Push** that branch (`git push -u origin HEAD`). Never push to `main`. Agents may merge their own PR once its required check passes, never with `--admin`. Before merging your own code change, run `/code-review medium` on the branch and fix what it confirms; skip it for docs-only PRs. Cursor has no `/code-review`, so a Cursor agent leaves the merge to the owner. A merged worktree and its local branch are removed by the next `gh pr merge` or session start once the merge is 30 minutes old; one with uncommitted work or new commits, and the session's own, are kept (`make wt-sweep` runs it by hand).
4. **PanelPro test** when `tables.xml` or panels changed: `make panelpro-test`. Report the result, including `SKIPPED` when PanelPro or CATS is open. Do not start it while the owner is operating.
5. **Deploy** when live artifacts changed. Panels, `tables.xml` bundle, Operations Pro files, signals, jython, web home, CTC icons, CATS resources: run `sync_hart_package.sh` as above. Website: run `deploy_hartrailroad.sh`. Skip deploy for docs-only / AGENTS / wiki-only and say so.
6. **Report** commit hash, pushed?, PanelPro test result, hosts deployed.

Sheets push (`.env.local`) stays human-gated. Do not force-push. `.claude/hooks/main_guard.py` blocks commits on `main`, pushes to `main`, force-pushes and admin merges, and asks before a `track/cmd` publish; Cursor runs the same guard through `.cursor/hooks.json`. The same hook blocks table-writing and deploy commands while PanelPro or CATS is open, and any commit, PR or issue text holding the private name; `.claude/hooks/check_after_edit.py` runs the quick checks after an edit to `tables.xml` or the signal files. `.claude/hooks/edit_guard.py` and `main_guard.py` keep agents out of the main checkout; `.claude/hooks/worktree_sweep.py` removes merged worktrees.

## Working on existing scripts

When a task changes or reuses a large script (about 500 lines or more) or one with no tests, leave it safer in the same PR. Match the effort to the task:

- **Small fix:** add a test for the behaviour you changed.
- **Feature or repeated rework:** also test the behaviour it depends on. Then split the script if that makes the work easier, as a separate commit that changes no behaviour, and never before those tests exist.
- **Only running it, or a docs or comment change:** nothing is owed. If you relied on untested behaviour for something live, say so in the report.

Start with `jmri/scripts/signal_coordinator.py` and `jmri/layouts/hart/scripts/panel_status.py`, since they run in JMRI on the Pi. Do not start a cleanup nobody asked for. If the safe version is bigger than the task, name it in the report and let the owner decide. Find the largest with `git ls-files '*.py' | xargs wc -l | sort -rn`.

## Subagents

The owner may not name an agent, so match the task yourself:

| Task | Agent |
|------|-------|
| Why a mast, panel, Dispatcher run or MQTT value behaves as it does | `panel-tracer` |
| Dead code, stale docs, structure or duplication | `repo-auditor` |
| Review of the website through a named lens | `site-reviewer` |
| Railroad or local history, photos and sources | `archive-researcher` |
| A bounded page or data job under `www/` | `site-builder` |

- **Call the agent without being asked** when one fits a single bounded job that would mean reading across many files. State which one you used.
- **Suggest it in one line and wait** for broad work: several agents at once, a rebuild split into stages, or a job the owner may want to steer.
- **Stay in the main session** for a handful of tool calls, and for deploys or live hardware.
- Launch any agent that edits files with `isolation: "worktree"`; read-only agents need none.
- Use `general-purpose` only when none fits. If the same kind of job keeps landing there, suggest a new agent.

Details: [`wiki/AGENTS_GIT.md`](wiki/AGENTS_GIT.md).

## Do not

- Run table scripts with PanelPro or CATS open. A PanelPro Store goes to `~/JMRI_UserFiles/tables.xml`; run `make tables-pull` before committing.
- Explode or decompile `cats.jar` into `cats/`. CATS is open source: [Kb0oys/cats](https://bitbucket.org/Kb0oys/cats/src/master/).
- Command field turnouts / publish `track/cmd` from launch or “fix paint” scripts.
- Run `fit_panel_height`, `fit_panel_canvas`, `polish_layout_geometry`, or 2× draw scale unless asked.
- Remove **F30-S-0** where the layout includes it.
- Store JMRI tables from a CATS session. PanelPro owns `tables.xml`.
- Run CATS CTC and the USS CTC machine (or Dispatcher System from inside CATS) at the same time.
- Patch or wrap Dispatcher System / JMRI (`CreateTransits`, `CreateIcons`, `Startup.py`, `TransitCreationTool`). Fix `jmri/layouts/hart/output/tables.xml` so stock Discover and Stage 1 succeed. Landmines: [`wiki/DISPATCHER_LAYOUT_HOOPS.md`](wiki/DISPATCHER_LAYOUT_HOOPS.md).
- Leave the LCOS bridge (`serial_to_mqtt`) running detached. It is operator-owned and runs in a visible foreground console. Start it only for a lab test, stop it before ending the turn, and ask the user to restart it (`.\run_serial_mqtt.cmd verbose`).
- Edit `external/lcos-bridge/lcos/` or `reference/` (vendor source) without explicit instruction and confirmation.
- Spell out what HART stands for in any file, commit or page. The repo and website are public.
- Normalize **P&CV** and **P&OV** to each other. They are different names on purpose.

New JMRI track: **Mainline → Yes** (`mainline="yes"`). Geometry **1:1**. Hart has no `export_options.json`.

New documents go in `docs/` (ADR-010); run the index command after adding one.

## Pointers

- Pipelines / landmines: [`docs/AI_CONTEXT.md`](docs/AI_CONTEXT.md)
- Git / branches, and where agent instructions live: [`wiki/AGENTS_GIT.md`](wiki/AGENTS_GIT.md)
- Submodules: each has its own rules and repo; see [`wiki/REPOS.md`](wiki/REPOS.md)
- CATS: [`cats/README.md`](cats/README.md) · [`cats/AGENTS.md`](cats/AGENTS.md)
- Public names: [ADR-005](wiki/decisions/ADR-005-public-equipment-names.md) · `jmri/layouts/hart/data/public_name_map.csv`

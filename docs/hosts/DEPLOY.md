# Layout host deploy: how it works

Reference for the [`deploy` skill](../../.claude/skills/deploy/SKILL.md). The skill says what to run and what to do when a deploy stops; this page says how the scripts work inside and why they stop.

## Steps and scripts

- `sync_hart_package.sh` is the entry point; it runs the steps in `tools/hosts/deploy/` in order: `gate.sh` (every check), `stage.sh` (builds the host packages once), `ship_mac.sh`, `ship_pi.sh`, `ship_win.sh`, with `common.sh` holding what they share (host settings, stamp facts, ssh connections). Every check runs in `gate.sh` before anything is sent or installed: the host ssh answers, the Pi's unpulled files, the panel audit, the `tables.xml` checks, this Mac's own Store check, a trial build of the package (thrown away) and, for Windows, a probe that it can make a temp folder and has `tar` (the probe makes and removes a folder, and `scp` and `tar` must exist on the Mac). A failed check leaves the Mac, the Pi and Windows as they were, so a retry of one host after a fix starts from the same state. The steps can be run alone (`tools/hosts/deploy/ship_win.sh [--dry-run] DIR/win` on a package `stage.sh` built); the operating-flag hook refuses `ship_pi.sh`, `ship_win.sh` and `gate.sh --pi/--win` like the entry point.
- With no flag it installs on the Mac only. A host flag also installs on the Mac, then sends one staged package: the Pi by rsync, Windows by tarball over ssh. Each host unpacks into a temporary folder, installs into `JMRI_UserFiles`, and removes the folder. The package is built once per run; the Pi and Windows copies differ only in the CATS panels (rewritten for each host's user files) and the stamp.
- `--dry-run` shows what would be sent (it still connects to the hosts). `--stage-only DIR` builds the Pi and Windows packages into `DIR/pi` and `DIR/win` and stops: no ssh, no Mac install, `tables.xml` only checked. Use it to look at or compare a package.
- Each host's calls share one ssh connection: the Pi's ssh, rsync and restart-check calls on one socket, the Windows ssh and scp calls on another (masters in a folder made for the run, closed and removed on every way out). `HART_SSH_MUX=0` turns sharing off for both; `HART_WIN_SSH_MUX=0` turns it off for Windows only, if its OpenSSH server misbehaves with a shared connection.
- The gate runs `audit_panel_contracts.py --strict` and checks the Digicon SML MQTT destinations are off in the shipped tables (the generator turns them off).
- Operations files are overwritten on every host once the Pi check passes (`HART_OVERWRITE_OPS=1` is the default; `0` restores the per-file guards).
- Hosts come from `HART_PI_SSH`, `HART_WIN_SSH`, `HART_WIN_SSH_PORT`, `HART_PI_USERFILES`, `HART_WIN_USERFILES` and `HART_PI_WEB_HOST` (the Pi's name in the Mac web home's links), read by `tools/env/load_env.sh` like the Python tools read theirs: environment, then `tools/env/hart.env`, then the default in `tools/env/defaults.env`.
- Edit host scripts in `tools/hosts/pi/` and `tools/hosts/windows/`; the package places them where the hosts expect them.
- Each host it installs ends with `JMRI_UserFiles/cats/deploy_stamp.txt` (commit, branch, dirty, sha256 of the shipped `tables.xml` and `tables_modified_by_deploy`, date, deploying machine, target, `source` and `redeploy_from`), written last by the apply step. Both apply steps install into the configured `HART_PI_USERFILES` / `HART_WIN_USERFILES`, so the stamp and `deploy_status.sh` agree. A checkout with uncommitted or untracked files deploys with a WARNING and the stamp records `dirty=yes`.

## G0b: the commit shipped

A deploy to the Pi or Windows ships `origin/main` itself: it fetches `origin/main` and stops before any ssh when HEAD is not on it, or is behind it (`ship_pi.sh` and `ship_win.sh` run alone check it too). Merge first and deploy from the updated main; an older commit goes through `redeploy_commit.sh`. `HART_ALLOW_UNMERGED=1` deploys another commit (a test on the hosts, a fix that cannot wait); say so in the report. `--dry-run`, `--check-only` and a Mac-only run are not held. Uncommitted files are not held either.

## G0c: main is red

A deploy or `--dry-run` to the Pi or Windows stops before any ssh when the commit's push run of `check.yml` on main ended failure, cancelled or timed out (owner 2026-11-27): `STOP: main is red: ... (<run URL>). Fix forward or revert first`. A run still going, no push run for the commit yet, another ending or a GitHub error (gh missing, logged out, a timeout, an odd answer) do not block, and a pass goes on; the gate prints a `main red check:` line saying which, naming the error. `--check-only`, `--stage-only`, a Mac-only run and a redeploy do not ask. `python3 tools/hosts/deploy/ci_pass.py --main-red --commit $(git rev-parse HEAD)` shows the answer without deploying. The website deploy has the same check before its build and upload.

## G2: the Pi's unpulled files

A Pi deploy stops before sending anything when the Pi's Operations Pro files, `tables.xml` or DecoderPro roster changed since the last deploy or pull, and it saves them first:

- A Store: it runs `tools/ops/pull_tables_pi.sh` (kept in `media/pulled-stores/` in the main checkout; it prints "kept the Pi's Store as <path>; split it ..."). The Store's split must be merged (see the `tables-pull` skill).
- Operations files: it quits PanelPro with `pi_quit_panelpro.sh --for-deploy` (the stop starts it again) and runs `tools/ops/pull_ops.sh --no-mark`, then stops. From the main checkout the pull goes into an `ops-pull-<stamp>` worktree, which the message names; otherwise into the checkout it runs from. The Pi stays unmarked, so it counts as pulled only once the Operations files are committed and merged (a deploy before that stops again; from the updated main it passes). See the `ops-pull` skill.
- The roster: see below.
- A pull failure stops saying nothing was kept. A redeploy never pulls: it stops as it did. `HART_NO_AUTOPULL=1` stops without pulling; `HART_DISCARD_PI_CHANGES=1` skips the check and replaces the Pi's changes, only on the owner's say. The operating flag blocks all of it first. A Mac Store waiting: `make tables-pull`.

## DecoderPro roster

The roster is a repo master (`jmri/layouts/hart/roster/`, ADR-039 amendment 2026-11-26): the deploy installs `roster.xml` and the files it names on the Mac, the Pi and Windows, with a backup of what it replaces (`JMRI_UserFiles/backups/roster/`), and the roster photos as before. Files `roster.xml` does not name stay. A Pi deploy stops when the Pi's roster changed since the last deploy (a programming session, a new loco) and pulls it like the Operations files (`tools/ops/pull_roster.sh`, into the same checkout or worktree; no PanelPro quit), saying "brought the Pi's DecoderPro roster into ..."; commit and merge it, then deploy. The Mac and Windows are replaced without a check (their own edits live only in the backup). Restart DecoderPro or PanelPro after a deploy that changed the roster.

## G4: tables.xml regeneration, skipped on a CI pass

The gate's `tables.xml` regeneration (`build_tables.py --check`, G4) is skipped on a real `--pi`/`--win` deploy when CI's full `check.sh` pass covers the commit shipped (owner, 2026-11-24): `tools/hosts/deploy/ci_pass.py` needs a clean checkout at that commit (edits inside a submodule do not count; a submodule at another commit does), a passing push run of `check.yml` on main for it, main's check stamps for it in CI's cache, and that run's log showing a full run (stamps recorded, none skipped, `SCHEMATIC_REQUIRED` 1) whose `panels-tables` job (`build_tables.py --check`, what G4 runs; one job per panels step since ADR-037 stage 6) ran with the commit's plugin pin and printed "current"; a log of another shape runs G4. The gate prints `skipped G4: CI full pass for <sha>` or `ran G4: <why>` (no CI pass, stamps unreadable, a dry run). The approvals (G4b) and the Digicon check (G5) always run. `python3 tools/hosts/deploy/ci_pass.py --commit $(git rev-parse HEAD)` shows the verdict without deploying.

## Host failures

- A real deploy, and a redeploy of an older commit, first asks every host named on the command line for an ssh answer and stops (`STOP: cannot reach ... over ssh`) before the Pi's unpulled check, the Mac install, the `tables.xml` gates or any host step if one does not reply (the gate's first host check), so `--pi --win` with Windows down sends and installs nothing on the Pi. PanelPro quit there for the deploy is started again, and the output says so. A dry run skips this check.
- With `--pi --win`, a Windows that cannot take the package (no temp folder or no `tar`) stops the run in the gate, before the Pi is touched; a Pi failure in its own step (for example "Connection refused") exits before the Windows step runs.
- If the Pi step fails, run `--win` on its own, then `--pi` once the Pi accepts ssh on port 22, so the two match again.
- If Windows fails after the Pi step finished (it answered the gate, then dropped during the copy or the apply), the run names the commit the Pi got (and says Windows may be partly installed if its apply failed): once Windows answers, give it the same commit with `make redeploy COMMIT=<sha> HOSTS=--win`. A Windows temp folder that cannot be removed after a good apply is only a warning.
- PanelPro: quit it on the Pi with `tools/hosts/pi_quit_panelpro.sh --for-deploy` first; the Pi deploy starts it again afterwards, also if it fails. A plain quit, or PanelPro the owner closed, stays closed. `HART_PI_RESTART=0` skips the restart.
- The host names and ports come from the settings above. Windows has had repeated hard power-offs.

## Redeploy an older commit (rollback)

- `make redeploy COMMIT=<sha> HOSTS="--pi --win"` (`tools/hosts/redeploy_commit.sh`; `--mac` for the Mac only). Quit PanelPro on the Pi first, as for any deploy.
- It makes a temporary detached worktree at that commit, runs that commit's own `sync_hart_package.sh` there with a clean environment (`env -i`: PATH, HOME, ssh agent, the deploy switches, and the host settings this checkout resolves, named by `load_env.sh`'s `HART_HOST_NAMES`), then removes the worktree. `--dry-run` and `--stage-only DIR` pass through.
- It refuses a commit that is not on `origin/main` (git fetch first; `--allow-unmerged` overrides) and one without `tools/hosts/sync_hart_package.sh` or the deploy stamp (before the ADR-007 amendment 2026-11-12). It stops before building anything if `~/JMRI_UserFiles/tables.xml` holds a Store that is not pulled (the same test as the deploy, `tools/hosts/profile_tables_guard.sh`): run `make tables-pull` first.
- The Operations files keep their guards (`HART_OVERWRITE_OPS=0`): an unpulled Pi session stops the Pi step, so run `make ops-pull`; a running JMRI keeps its files. `HART_OVERWRITE_OPS=1` replaces them as a normal deploy does.
- With `--pi` or `--all` it makes the same Pi check as the deploy (`make ops-pull`, `make tables-pull-pi`; `HART_DISCARD_PI_CHANGES=1`), since older commits' deploys lack it.
- The older commit's deploy then makes its own Pi check, against that commit's `store_splits.csv`. If the Pi holds a Store that was split in after that commit, this checkout's check passes and the older one can stop at "the Pi's tables.xml changed" (found in the #806 review, not reproduced). The Store is already in the repo, so the way through is `HART_DISCARD_PI_CHANGES=1`, and only with the owner's yes, since it skips the Operations check too: run `make ops-pull` first.
- The stamp says `source=redeploy` and `redeploy_from=<commit that ran it>` (a normal deploy writes `source=deploy`).
- The stamp keeps no history. To find the commit to go back to, read the current one with `make deploy-status` and look at `git log --first-parent --oneline origin/main` for the merge before it.
- After a rollback the Mac and the hosts hold the old commit's `tables.xml`. Go forward with a normal deploy from `main` before a PanelPro Store, or `make tables-pull` would bring the old tables back into the repo.

## Website deploy details

`www/scripts/deploy_hartrailroad.sh` builds with `prepare_github_pages.py`, checks links with `check_portal_build.py`, then rsyncs with `--delete`. The build needs the gitignored originals in `media/` and `ops/car-cards/`; only the main checkout has them, and `make wt` links both into a new worktree. Without them photos are stripped and the run stops at the `--require-mirrors` check, which `--force` does not skip. It also needs `ops/hart-ops/operator_logos/`, a real rsync on the Mac (`brew install rsync`) or `HART_WEB_HOST` and `HART_WEB_DOCROOT` (values in the owner's private notes, `private/web-server/` in the main checkout only). It has the G0c main-red check before the build and the upload. Untracked files are not published; uncommitted changes only give a warning.

## Sources

- `tools/hosts/sync_hart_package.sh`, `tools/hosts/deploy/` (the steps), `tools/hosts/redeploy_commit.sh`, `tools/hosts/deploy_status.sh`, `tools/env/load_env.sh`, `www/scripts/deploy_hartrailroad.sh`
- `www/README.md` (Deploy safety, server notes)
- `.claude/commands/done.md` (step 5), `wiki/STATUS.md`
- [ADR-014](../../wiki/decisions/ADR-014-jmri-user-files.md), [ADR-015](../../wiki/decisions/ADR-015-operations-files-in-repo.md)

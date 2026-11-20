---
name: deploy
description: Use when live artifacts changed and need to reach the layout hosts (Pi, Windows) or the public website, when asked to run sync_hart_package.sh or deploy_hartrailroad.sh, or when a deploy fails with a connection error, a missing media check or a Build count drop.
---

# Deploy

Two separate deploys. Pick by what changed (AGENTS.md, close-out step 5).

| Changed | Run |
|---|---|
| Panels, `tables.xml` bundle, Operations Pro files, signals, jython, web home, CATS resources | `./tools/hosts/sync_hart_package.sh --pi --win` |
| Website (`www/`) | `./www/scripts/deploy_hartrailroad.sh` |
| Docs, AGENTS, wiki only | No deploy. Say so in the report. |

Windows is kept matching the Pi, so both get every layout deploy (`make deploy-layout` runs the same; `--all` and `make deploy-all` are the same as `--pi --win`). Deploy one host alone only to test something there or while the other is down; say so in the report and bring the other host up to date next. `make deploy-site` runs the website deploy.

## Layout hosts

Before you run it:

- A Pi deploy stops before sending anything when the Pi's Operations Pro files or `tables.xml` changed since the last deploy or pull: run `make ops-pull` or `make tables-pull-pi` (see the `ops-pull` and `tables-pull` skills) and commit. `HART_DISCARD_PI_CHANGES=1` replaces them anyway, only on the owner's say. A Mac Store waiting: `make tables-pull`.
- `--dry-run` shows what would be sent (it still connects to the hosts).
- `--stage-only DIR` builds the Pi and Windows packages into `DIR/pi` and `DIR/win` and stops: no ssh, no Mac install, `tables.xml` only checked. Use it to look at or compare a package.
- A checkout with uncommitted or untracked files prints a WARNING and deploys anyway; the stamp records `dirty=yes`. Commit first unless the owner wants a work-in-progress deploy.

What it does:

- With no flag it installs on the Mac only. A host flag also installs on the Mac, then sends one staged package: the Pi by rsync, Windows by tarball over ssh. Each host unpacks into a temporary folder, installs into `JMRI_UserFiles`, and removes the folder.
- It runs `audit_panel_contracts.py --strict` first and turns off the Digicon SML MQTT destinations in the shipped tables.
- Operations files are overwritten on every host once the Pi check passes (`HART_OVERWRITE_OPS=1` is the default; `0` restores the per-file guards).
- Hosts come from `HART_PI_SSH`, `HART_WIN_SSH`, `HART_WIN_SSH_PORT`, `HART_PI_USERFILES`, `HART_WIN_USERFILES` and `HART_PI_WEB_HOST` (the Pi's name in the Mac web home's links), read by `tools/env/load_env.sh` like the Python tools read theirs: environment, then `tools/env/hart.env`, then the default in `tools/env/defaults.env`.
- Edit host scripts in `tools/hosts/pi/` and `tools/hosts/windows/`; the package places them where the hosts expect them.
- Each host it installs ends with `JMRI_UserFiles/cats/deploy_stamp.txt` (commit, branch, dirty, sha256 of the shipped `tables.xml` and `tables_modified_by_deploy`, date, deploying machine, target, `source` and `redeploy_from`), written last by the apply step. Both apply steps install into the configured `HART_PI_USERFILES` / `HART_WIN_USERFILES`, so the stamp and `deploy_status.sh` agree.

Redeploy an older commit (rollback):

- `make redeploy COMMIT=<sha> HOSTS="--pi --win"` (`tools/hosts/redeploy_commit.sh`; `--mac` for the Mac only). Quit PanelPro on the Pi first, as for any deploy.
- It makes a temporary detached worktree at that commit, runs that commit's own `sync_hart_package.sh` there with a clean environment (`env -i`: PATH, HOME, ssh agent, the deploy switches, and the host settings this checkout resolves, named by `load_env.sh`'s `HART_HOST_NAMES`), then removes the worktree. `--dry-run` and `--stage-only DIR` pass through.
- It refuses a commit that is not on `origin/main` (git fetch first; `--allow-unmerged` overrides) and one without `tools/hosts/sync_hart_package.sh` or the deploy stamp (before the ADR-007 amendment 2026-11-12). It stops before building anything if `~/JMRI_UserFiles/tables.xml` holds a Store that is not pulled (the same test as the deploy, `tools/hosts/profile_tables_guard.sh`): run `make tables-pull` first.
- The Operations files keep their guards (`HART_OVERWRITE_OPS=0`): an unpulled Pi session stops the Pi step, so run `make ops-pull`; a running JMRI keeps its files. `HART_OVERWRITE_OPS=1` replaces them as a normal deploy does.
- With `--pi` or `--all` it makes the same Pi check as the deploy (`make ops-pull`, `make tables-pull-pi`; `HART_DISCARD_PI_CHANGES=1`), since older commits' deploys lack it.
- The stamp says `source=redeploy` and `redeploy_from=<commit that ran it>` (a normal deploy writes `source=deploy`).
- The stamp keeps no history. To find the commit to go back to, read the current one with `make deploy-status` and look at `git log --first-parent --oneline origin/main` for the merge before it.
- After a rollback the Mac and the hosts hold the old commit's `tables.xml`. Go forward with a normal deploy from `main` before a PanelPro Store, or `make tables-pull` would bring the old tables back into the repo.

Hosts and failures:

- The Pi is `RPi-JMRI.local` (10.0.0.150, ssh alias `pi`). Windows is `minipc-e5h6x.local` (ssh port 2222) and has had repeated hard power-offs.
- A real deploy first asks every host named on the command line for an ssh answer and stops (`STOP: cannot reach ... over ssh`) before the Mac install, the `tables.xml` gates or any host step if one does not reply, so `--pi --win` with Windows down leaves the Pi as it was. A dry run skips this check.
- With `--pi --win`, a Pi failure after that check (for example "Connection refused") exits before the Windows step runs.
- If the Pi step fails, run `--win` on its own, then `--pi` once the Pi accepts ssh on port 22, so the two match again.
- Quit PanelPro on the Pi with `tools/hosts/pi_quit_panelpro.sh --for-deploy` first; the Pi deploy starts it again afterwards, also if it fails. A plain quit, or PanelPro the owner closed, stays closed. `HART_PI_RESTART=0` skips the restart.
- Check afterwards with `make deploy-status HOSTS="--pi --win"` (or `tools/hosts/deploy_status.sh`), which reads the stamp back and compares its commit with this checkout, and with a sha256 of `tables.xml` on each host.
- Do not leave the LCOS bridge (`serial_to_mqtt`) running, and do not publish `track/cmd` from a deploy.

## Website

Before you run it:

- The build needs the gitignored originals in `media/` and `ops/car-cards/`. Only the main checkout has them. `make wt` links both into a new worktree; for an older worktree, symlink them from the main checkout first. Without them photos are stripped, and the run stops at the `--require-mirrors` check. `--force` does not skip that check.
- `ops/hart-ops/operator_logos/` must exist, or the deploy refuses to run.
- A real rsync is needed on the Mac (`brew install rsync`), or set `HART_WEB_HOST=www.easte.net` for a normal login.

What it does: builds with `prepare_github_pages.py`, checks links with `check_portal_build.py`, then rsyncs with `--delete`.

After it runs:

- Read the Build counts in the output (files, archive items, logos, gallery and fleet items). A drop of more than 10% against the last deploy stops it. `--force` overrides, but find out why counts fell first. Missing symlinks are the usual cause.
- The server may take up to a minute to show the change.
- Untracked files are not published. Uncommitted changes only give a warning.

## Report

Name the hosts and sites deployed, or say which were skipped and why.

## Sources

- `tools/hosts/sync_hart_package.sh`, `tools/hosts/redeploy_commit.sh`, `tools/hosts/deploy_status.sh`, `tools/env/load_env.sh`, `www/scripts/deploy_hartrailroad.sh`
- `www/README.md` (Deploy safety, server notes)
- `AGENTS.md` (close-out step 5), `wiki/STATUS.md`
- `wiki/decisions/ADR-014-jmri-user-files.md`, `wiki/decisions/ADR-015-operations-files-in-repo.md`

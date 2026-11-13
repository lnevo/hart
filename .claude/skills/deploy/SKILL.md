---
name: deploy
description: Use when live artifacts changed and need to reach the layout hosts (Pi, Windows) or the public website, when asked to run sync_hart_package.sh or deploy_hartrailroad.sh, or when a deploy fails with a connection error, a missing media check or a Build count drop.
---

# Deploy

Two separate deploys. Pick by what changed (AGENTS.md, close-out step 5).

| Changed | Run |
|---|---|
| Panels, `tables.xml` bundle, Operations Pro files, signals, jython, web home, CTC icons, CATS resources | `./tools/hosts/sync_hart_package.sh --pi`, add `--win` (or use `--all`) when Windows needs it |
| Website (`www/`) | `./www/scripts/deploy_hartrailroad.sh` |
| Docs, AGENTS, wiki only | No deploy. Say so in the report. |

`make deploy-layout`, `make deploy-all` and `make deploy-site` run the same commands. `cats/scripts/sync_hart_package.sh` still works: it is a wrapper for `tools/hosts/sync_hart_package.sh` (ADR-007 amendment 2026-11-12).

## Layout hosts

Before you run it:

- Run `make tables-pull` if a Store may be waiting (see the `tables-pull` skill), and `make ops-pull` first to keep a Pi Operations session (see the `ops-pull` skill). The repo wins on both.
- `--dry-run` shows what would be sent (it still connects to the hosts).
- `--stage-only DIR` builds the Pi and Windows packages into `DIR/pi` and `DIR/win` and stops: no ssh, no Mac install, `tables.xml` only checked. Use it to look at or compare a package.
- A checkout with uncommitted or untracked files prints a WARNING and deploys anyway; the stamp records `dirty=yes`. Commit first unless the owner wants a work-in-progress deploy.

What it does:

- With no flag it installs on the Mac only. A host flag also installs on the Mac, then sends one staged package: the Pi by rsync, Windows by tarball over ssh. Each host unpacks into a temporary folder, installs into `JMRI_UserFiles`, and removes the folder.
- It runs `audit_panel_contracts.py --strict` first and turns off the Digicon SML MQTT destinations in the shipped tables.
- Operations files are overwritten on every host (`HART_OVERWRITE_OPS=1` is the default; `0` restores the guards).
- Hosts come from `HART_PI_SSH`, `HART_WIN_SSH`, `HART_WIN_SSH_PORT`, `HART_PI_USERFILES` and `HART_WIN_USERFILES`, read by `tools/env/load_env.sh` like the Python tools read theirs: environment, then `tools/env/hart.env`, then the default in `load_env.sh`.
- Inside the package the host scripts still sit at cats/scripts/pi and cats/scripts/windows, where the hosts expect them; their repo source is `tools/hosts/pi/` and `tools/hosts/windows/`.
- Each host it installs ends with `JMRI_UserFiles/cats/deploy_stamp.txt` (commit, branch, dirty, date, deploying machine, target), written last by the apply step.

Hosts and failures:

- Since 2026-11-11 the Pi (`RPi-JMRI.local`, 10.0.0.150, ssh alias `pi`) is on the house network directly, no longer through Windows. Windows is `minipc-e5h6x.local` (ssh port 2222) and has had repeated hard power-offs.
- With `--pi --win`, a Pi failure (for example "Connection refused") exits before the Windows step runs.
- If the Pi step fails, run `--win` on its own. Run `--pi` again once the Pi accepts ssh on port 22.
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

- `tools/hosts/sync_hart_package.sh`, `tools/hosts/deploy_status.sh`, `tools/env/load_env.sh`, `www/scripts/deploy_hartrailroad.sh`
- `www/README.md` (Deploy safety, server notes)
- `AGENTS.md` (close-out step 5), `wiki/STATUS.md`
- `wiki/decisions/ADR-014-jmri-user-files.md`, `wiki/decisions/ADR-015-operations-files-in-repo.md`

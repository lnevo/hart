---
name: deploy
description: Use when live artifacts changed and need to reach the layout hosts (Pi, Windows) or the public website, when asked to run sync_hart_package.sh or deploy_hartrailroad.sh, or when a deploy fails with a connection error, a missing media check or a Build count drop.
---

# Deploy

Two separate deploys. Pick by what changed (`/done` step 5). How the scripts work inside, and the long forms of the stops below: [`docs/hosts/DEPLOY.md`](../../../docs/hosts/DEPLOY.md).

| Changed | Run |
|---|---|
| Panels, `tables.xml` bundle, Operations Pro files, signals, jython, web home, CATS resources | `./tools/hosts/sync_hart_package.sh --pi --win` |
| Website (`www/`) | `./www/scripts/deploy_hartrailroad.sh` |
| Docs, AGENTS, wiki only | No deploy. Say so in the report. |

Windows is kept matching the Pi, so both get every layout deploy (`make deploy-layout` runs the same; `--all` and `make deploy-all` are the same as `--pi --win`). Deploy one host alone only to test something there or while the other is down; say so in the report and bring the other host up to date next. `make deploy-site` runs the website deploy.

## Layout hosts

Before you run it:

- Quit PanelPro on the Pi with `tools/hosts/pi_quit_panelpro.sh --for-deploy`; the deploy starts it again, also if it fails. `HART_PI_RESTART=0` skips the restart.
- Do not stop or restart the LCOS bridge (the `lcos-bridge` service on the Pi), and do not publish `track/cmd` from a deploy.
- `--dry-run` shows what would be sent (it still connects). `--stage-only DIR` builds the packages into `DIR/pi` and `DIR/win` and stops, with no ssh: use it to look at a package.

Stops and what to do:

- **Operating flag set:** a hook blocks every Pi and Windows action (`ship_pi.sh`, `ship_win.sh`, `gate.sh --pi/--win` too). See the `operating-flag` skill.
- **G0b, HEAD is not on `origin/main` or is behind it:** merge first and deploy from the updated main. An older commit goes through `make redeploy`. `HART_ALLOW_UNMERGED=1` deploys another commit (a test on the hosts, a fix that cannot wait); say so in the report. `--dry-run`, `--check-only` and a Mac-only run are not held.
- **G0c, `STOP: main is red: ... (<run URL>)`:** the commit's push run of `check.yml` on main failed, was cancelled or timed out. Fix forward or revert first. A run still going, no run yet or a GitHub error do not block (the `main red check:` line says which). Check without deploying: `python3 tools/hosts/deploy/ci_pass.py --main-red --commit $(git rev-parse HEAD)`.
- **G2, the Pi's Operations Pro files, `tables.xml` or DecoderPro roster changed since the last deploy or pull:** the deploy saves them and stops.
  - Store: kept in `media/pulled-stores/` ("kept the Pi's Store as <path>; split it ..."); split and merge it (`tables-pull` skill).
  - Operations files: it quits PanelPro, runs `tools/ops/pull_ops.sh --no-mark` into an `ops-pull-<stamp>` worktree the message names (from the main checkout, else the checkout it runs from). Commit and merge the files, then deploy from the updated main (`ops-pull` skill). The Pi counts as pulled only after that merge.
  - Roster ("brought the Pi's DecoderPro roster into ..."): commit and merge it, then deploy. The roster is a repo master, so the deploy replaces the roster on all three hosts (backup in `JMRI_UserFiles/backups/roster/`); restart DecoderPro or PanelPro afterwards.
  - A pull failure stops saying nothing was kept. A redeploy never pulls. `HART_NO_AUTOPULL=1` stops without pulling. `HART_DISCARD_PI_CHANGES=1` skips the check and replaces the Pi's changes, only on the owner's say. A Mac Store waiting: `make tables-pull`.
- **`STOP: cannot reach ... over ssh`:** a named host did not answer; nothing was sent or installed (a PanelPro quit for the deploy is started again). If the Pi step fails, run `--win` alone, then `--pi` once the Pi accepts ssh on port 22. If Windows fails after the Pi finished, the run names the commit the Pi got: once Windows answers, `make redeploy COMMIT=<sha> HOSTS=--win`. Windows has had hard power-offs.
- **Dirty checkout:** uncommitted or untracked files print a WARNING and the deploy goes on (the stamp records `dirty=yes`). Commit first unless the owner wants a work-in-progress deploy.
- **Roster:** see G2 above; a Windows or Mac roster is replaced without a check.

The gate checks everything before sending, so a failed check leaves all hosts as they were. G4 (`tables.xml` regeneration) is skipped when CI's full pass covers the commit; the gate prints `skipped G4` or `ran G4: <why>`. Operations files are overwritten on every host once the Pi check passes.

After it runs: `make deploy-status HOSTS="--pi --win"` (or `tools/hosts/deploy_status.sh`) reads each host's stamp (`JMRI_UserFiles/cats/deploy_stamp.txt`) back, compares its commit with this checkout and checks the `tables.xml` sha256.

### Rollback (older commit)

- `make redeploy COMMIT=<sha> HOSTS="--pi --win"` (`--mac` for the Mac only; `--dry-run` and `--stage-only DIR` pass through). Quit PanelPro on the Pi first.
- It refuses a commit not on `origin/main` (`git fetch` first; `--allow-unmerged` overrides) and stops if `~/JMRI_UserFiles/tables.xml` holds an unpulled Store: run `make tables-pull` first. An unpulled Pi session stops the Pi step: run `make ops-pull`. For the Pi it makes the same check as a deploy (`make ops-pull`, `make tables-pull-pi`).
- The older commit's own Pi check can stop at "the Pi's tables.xml changed" when the Pi holds a Store split in after that commit. The Store is already in the repo, so the way through is `HART_DISCARD_PI_CHANGES=1`, only with the owner's yes (it skips the Operations check too: run `make ops-pull` first).
- Find the commit to go back to with `make deploy-status` (the stamp keeps no history) and `git log --first-parent --oneline origin/main`.
- Afterwards go forward with a normal deploy from `main` before a PanelPro Store, or `make tables-pull` would bring the old tables back into the repo.

## Website

Before you run it:

- The build needs the gitignored originals in `media/` and `ops/car-cards/`, only in the main checkout. `make wt` links both into a new worktree; for an older worktree, symlink them first. Without them the run stops at the `--require-mirrors` check, which `--force` does not skip.
- `ops/hart-ops/operator_logos/` must exist, or the deploy refuses to run.
- It stops with the same `STOP: main is red` line as G0c when HEAD's push run of `check.yml` on main failed.
- It needs a real rsync on the Mac (`brew install rsync`), or `HART_WEB_HOST` and `HART_WEB_DOCROOT` (in `private/web-server/` in the main checkout only).

After it runs:

- Read the Build counts (files, archive items, logos, gallery and fleet items). A drop of more than 10% against the last deploy stops it. `--force` overrides, but find out why counts fell first; missing symlinks are the usual cause.
- The server may take up to a minute to show the change. Untracked files are not published; uncommitted changes only warn.

## Report

Name the hosts and sites deployed, or say which were skipped and why.

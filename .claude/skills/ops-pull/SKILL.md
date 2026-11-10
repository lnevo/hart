---
name: ops-pull
description: Use when a Pi Operations Pro session (moves, car or train state) must be saved into the repo, before any deploy that would replace the Pi's Operations files, or when asked to run make ops-pull.
---

# Bring Pi Operations Pro state into the repo

The repo is the master of the six Operations Pro files, in `jmri/layouts/hart/operations/` (ADR-015). JMRI writes session state into them on the Pi. Deploy installs the repo copies over the Pi's, so a session that is not pulled first survives only in the backup deploy makes.

## Before you run it

- Quit JMRI and CATS on the Pi. The script checks over ssh and refuses to run otherwise.
- The Pi is the only host whose Operations changes are kept. Changes made on the Mac or Windows are replaced at the next deploy.

## Steps

1. `make ops-pull` (runs `tools/ops/pull_ops.sh`).
2. The script copies these from `JMRI_UserFiles/operations` on the Pi into `jmri/layouts/hart/operations/`: `Operations.xml`, `OperationsCarRoster.xml`, `OperationsEngineRoster.xml`, `OperationsLocationRoster.xml`, `OperationsRouteRoster.xml`, `OperationsTrainRoster.xml`. It then writes `.deployed.sha256` on the Pi and prints `git status` for the folder.
3. Review the diff. Settings "Add Operations to main menu" and "Close window on save" must stay true in `Operations.xml` (see `wiki/STATUS.md`).
4. Commit the changed files by name. Deploy afterwards if the files should reach the other hosts (see the `deploy` skill).

## Related

- `bin/cars publish` writes straight to the repo roster. Commit it, then deploy. It does not need a pull.
- Restart JMRI after a roster change. A running JMRI can write its old roster back over installed files.
- The DecoderPro roster is separate: `tools/hosts/sync_roster_from_pi.sh`.
- The Pi's ssh name and folder come from `HART_PI_SSH` and `HART_PI_USERFILES`; the defaults are in the script.

## Sources

- `tools/ops/pull_ops.sh`, the `ops-pull` target in `Makefile`
- `wiki/decisions/ADR-015-operations-files-in-repo.md`, `wiki/STATUS.md`

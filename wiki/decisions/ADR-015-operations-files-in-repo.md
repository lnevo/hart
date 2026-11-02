# ADR-015 — Operations Pro files in the repo

- **Status:** Accepted. Amends ADR-013 items 3 and 6.
- **Date:** 2026-11-02
- **Deciders:** lnevo

## Context

The Pi's six Operations Pro files had no reviewed history. Other copies sat in `~/JMRI_UserFiles`, `external/hart-ops` and the ignored `jmri/host-copies/`, and they had drifted: the Mac held 90 cars and the Pi 99.

## Decision

1. `jmri/layouts/hart/operations/` is the master of the six files, as `output/tables.xml` is of tables. Changes are made there and reviewed in git.
2. `sync_hart_package.sh` installs them into `JMRI_UserFiles/operations` on every host it deploys to, backing up what it replaces. The repo wins, even with JMRI running. `HART_OVERWRITE_OPS=0` restores the guards: skip a host running JMRI, and stop on unpulled Pi changes.
3. JMRI writes session state into these files on the Pi. `make ops-pull` brings it into the repo, to commit. A deploy without a pull replaces that state, and only the backup keeps it.
4. `bin/cars publish` writes directly to the repo roster. Commit it, then deploy.
5. The `out_of_service` column in `external/hart-ops/data/image_metadata.csv` (ADR-013) is the one record of a car being out of service. `bin/cars service out|in <id>` sets it. `bin/cars publish` sends it to STS as **Unavailable** (seed and running database) and to the roster as `outOfService="true"`. A car changed in STS or JMRI directly shows up in `bin/cars compare`, and the next publish undoes it.

## Consequences

- Roster changes get a diff, and every host gets the same files.
- A session on the Pi needs `make ops-pull` and a commit before the next deploy, or its state stays only in the backup.
- A JMRI left running keeps its loaded roster and can write it back over the installed files, so restart JMRI after a roster change.
- The Pi is the only host whose Operations changes are kept. Changes on the Mac or Windows are replaced at the next deploy.
- The DecoderPro roster is not part of this. `tools/hosts/sync_roster_from_pi.sh` still copies it from the Pi.

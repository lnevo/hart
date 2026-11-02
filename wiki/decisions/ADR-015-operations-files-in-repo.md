# ADR-015 — Operations Pro files in the repo

- **Status:** Accepted. Amends ADR-013 item 6 and the install steps in `wiki/pipelines/car-workflow.md`.
- **Date:** 2026-11-02
- **Deciders:** lnevo

## Context

The Pi's six Operations Pro files had no reviewed history. Other copies sat in `~/JMRI_UserFiles`, `external/hart-ops` and the ignored `jmri/host-copies/`, and they had drifted: the Mac held 90 cars and the Pi 99.

## Decision

1. `jmri/layouts/hart/operations/` is the managed copy of the six files. Changes are made there and reviewed in git.
2. The Pi stays the live copy. JMRI writes session state there, so run `./tools/hosts/ops_files.sh pull` and commit before changing the repo files.
3. `./tools/hosts/ops_files.sh install` puts the repo files on the Pi with JMRI closed, and backs up what it replaces.
4. An STS **Unavailable** car is **Out of Service** in Operations Pro (`outOfService="true"`). STS holds the status; the roster follows it by hand until a tool compares them.

## Consequences

- Roster changes get a diff, and the flag difference between STS and Operations Pro can be seen.
- Session state appears as repo changes after a pull, so sessions need a commit.
- `bin/cars publish` still merges new cars from the hart-ops copy, not this folder. Moving it here is later work.

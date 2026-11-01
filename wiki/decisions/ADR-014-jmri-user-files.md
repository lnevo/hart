# ADR-014 — JMRI_UserFiles on every host

- **Status:** Accepted. Amends ADR-008 items 1 and 3.
- **Date:** 2026-11-01
- **Deciders:** lnevo

## Context

The hosts had grown apart. The Pi used `~/JMRI_UserFiles`, Windows and the Mac used the profile folder, the Mac loaded `tables.xml` straight from the repo, and deploy copied files into every profile as well.

## Decision

1. Every host's profile sets `user-files` to `home:JMRI_UserFiles/`, so `preference:` means the same folder everywhere.
2. Deploy installs only into `JMRI_UserFiles`. The profile folder holds JMRI's own settings.
3. Every host loads `preference:tables.xml`, including the Mac.
4. `jmri/layouts/hart/output/tables.xml` is still the master. Table scripts edit it, git tracks it, and deploy installs it.
5. A PanelPro Store goes to `~/JMRI_UserFiles/tables.xml`. `make tables-pull` brings it back into the repo. Deploy stops if a Store has not been pulled.
6. PanelPro automation (`run_panelpro_*.sh`, the Discover scripts) points Start Up at the repo file for its run, then restores the profile.
7. CATS files live in `JMRI_UserFiles/cats`, because CATS has no JMRI home. Deploy unpacks into `/tmp` or `%TEMP%` and removes it.

## Consequences

- An install looks the same on every host, and nothing depends on where the repo is checked out.
- A Store on the Mac is no longer a repo change until it is pulled.

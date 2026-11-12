---
name: tables-pull
description: Use when a PanelPro Store has changed ~/JMRI_UserFiles/tables.xml and it must come back into the repo, when deploy stops with "tables.xml changed since the last deploy", or before committing after a PanelPro session.
---

# Bring a PanelPro Store into the repo

`jmri/layouts/hart/output/tables.xml` is the one tables file (ADR-008). Every host loads `preference:tables.xml` from `JMRI_UserFiles` (ADR-014). A Store in PanelPro writes `~/JMRI_UserFiles/tables.xml`, which is not a repo change until it is pulled.

## Before you run it

- Quit PanelPro and CATS. The script refuses to run while either is open.
- Do not run table scripts while they are open either.
- Do not store tables from a CATS session. PanelPro owns `tables.xml`.

## Steps

1. `make tables-pull` (runs `tools/ops/pull_tables.sh`).
2. The script:
   - stops if PanelPro or CATS is running, or if `~/JMRI_UserFiles/tables.xml` is missing;
   - exits with "already matches" if the files are identical;
   - otherwise copies the Store over the repo file and writes `~/JMRI_UserFiles/.tables_deployed.sha256`, which clears the deploy guard.
3. Review `git diff jmri/layouts/hart/output/tables.xml`. Check that only the changes you expect are there. Expected extra: the memory `IMHART_MIMIC` with an "ack <n>" value after a Pi Store (see `wiki/pipelines/mqtt-mimic.md`).
4. Run `./tools/check.sh` before any commit that changes tables or signals.
5. If tables or panels changed, run `make panelpro-test` when the owner is not operating (AGENTS.md close-out, step 4).
6. Commit the file by name, then follow the close-out in AGENTS.md. A changed tables file needs a deploy.

## Why deploy stops

`sync_hart_package.sh` stops with "tables.xml changed since the last deploy" when the Mac's `~/JMRI_UserFiles/tables.xml` differs from the last deployed hash. The guard covers the Mac install only; the Pi and Windows copies are replaced without a check. Run this pull first. `HART_OVERWRITE_PROFILE_TABLES=1` skips the guard and throws the Store away, so use it only when the owner says to.

## Sources

- `tools/ops/pull_tables.sh`, the `tables-pull` target in `Makefile`
- `wiki/decisions/ADR-008-tables-ownership.md`, `wiki/decisions/ADR-014-jmri-user-files.md`
- `cats/scripts/sync_hart_package.sh` (`install_tables_local`)

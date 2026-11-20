---
name: tables-pull
description: Use when a PanelPro Store on the Pi or the Mac has changed JMRI_UserFiles/tables.xml and it must come back into the repo, when deploy stops with "tables.xml changed since the last deploy" or "the Pi's tables.xml changed", or before committing after a PanelPro session.
---

# Bring a PanelPro Store into the repo

`jmri/layouts/hart/output/tables.xml` is the one tables file (ADR-008). Every host loads `preference:tables.xml` from `JMRI_UserFiles` (ADR-014). Since R9c it is generated (ADR-029: `tools/schematic/build_tables.py`), so a Store is never copied over it. Until R9d splits a Store into the sources, both pulls keep the Store in the gitignored `jmri/layouts/hart/output/pulled/` and stop: `make tables-pull` (Mac) and `make tables-pull-pi` (`tools/ops/pull_tables_pi.sh`, which leaves the Pi's `.tables_deployed.sha256` alone, so the deploy keeps stopping). The owner's PanelPro edits are kept in that file; carry them into `devices.csv`, the template or the discovered Signal Mast Logic, run `make panels`, commit, and deploy.

## Before you run it

- Let a Store finish before you pull. A PanelPro or CATS open on the Mac does not stop the script.
- Do not store tables from a CATS session. PanelPro owns `tables.xml`.

## Steps

1. `make tables-pull` (runs `tools/ops/pull_tables.sh`).
2. The script:
   - stops if `~/JMRI_UserFiles/tables.xml` is missing;
   - exits with "already matches" if the files are identical;
   - otherwise saves the Store as `jmri/layouts/hart/output/pulled/mac-<date>.xml`, changes nothing else, and stops with exit 1.
3. Compare the saved Store with `tables.xml` to find the owner's edits (a Store also writes its file history, clock time and memory values, and may reorder beans; those are not edits). Carry each edit into its source.
4. Run `./tools/check.sh` before any commit that changes tables or signals.
5. If tables or panels changed, run `make panelpro-test` when the owner is not operating (AGENTS.md close-out, step 4).
6. Run `python3 tools/schematic/build_tables.py` (or `make panels`), commit the changed sources and `tables.xml` by name, then follow the close-out in AGENTS.md. A changed tables file needs a deploy. Once the edits are deployed the host no longer counts as unpulled.

## Why deploy stops

`sync_hart_package.sh` stops with "tables.xml changed since the last deploy" when the Mac's `~/JMRI_UserFiles/tables.xml` differs from the last deployed hash. Run this pull first. On the Pi the deploy checks before sending anything (`tools/hosts/pi/unpulled_changes.sh`) and stops with "the Pi's tables.xml changed since the last deploy": run `make tables-pull-pi`. `HART_DISCARD_PI_CHANGES=1` replaces the Pi's Store and Operations files anyway, so use it only when the owner says to. Windows is replaced without a check. `HART_OVERWRITE_PROFILE_TABLES=1` skips the guard and throws the Store away, so use it only when the owner says to.

## Sources

- `tools/ops/pull_tables.sh`, `tools/ops/pull_tables_pi.sh`, the `tables-pull` and `tables-pull-pi` targets in `Makefile`
- `wiki/decisions/ADR-008-tables-ownership.md`, `wiki/decisions/ADR-014-jmri-user-files.md`
- `tools/hosts/sync_hart_package.sh` (`install_tables_local`)

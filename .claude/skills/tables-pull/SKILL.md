---
name: tables-pull
description: Use when a PanelPro Store on the Pi or the Mac has changed JMRI_UserFiles/tables.xml and it must come back into the repo, when deploy stops with "tables.xml changed since the last deploy" or "the Pi's tables.xml changed", or before committing after a PanelPro session.
---

# Bring a PanelPro Store into the repo

`jmri/layouts/hart/output/tables.xml` is the one tables file (ADR-008). Every host loads `preference:tables.xml` from `JMRI_UserFiles` (ADR-014). Since R9c it is generated (ADR-029: `tools/schematic/build_tables.py`), so a Store is never copied over it. Until R9d splits a Store into the sources automatically, both pulls (`make tables-pull` on the Mac, `make tables-pull-pi` for the Pi, `tools/ops/pull_tables_pi.sh`) take a Store that differs from what was last deployed or pulled (`tools/hosts/pi/unpulled_changes.sh` decides, as the deploy does), keep it in the gitignored `jmri/layouts/hart/output/pulled/<host>-<date>.xml`, and once it is safely saved record it as taken on the host (`.tables_deployed.sha256`). The next deploy then goes ahead and replaces the host's file with the generated `tables.xml`, so the owner's PanelPro edits are only in the kept file: carry them into `devices.csv`, the template or the discovered Signal Mast Logic before that deploy.

## Before you run it

- Let a Store finish before you pull. A PanelPro or CATS open on the Mac does not stop the script.
- Do not store tables from a CATS session. PanelPro owns `tables.xml`.

## Steps

1. `make tables-pull` (runs `tools/ops/pull_tables.sh`).
2. The script:
   - stops if `~/JMRI_UserFiles/tables.xml` is missing or does not parse;
   - says "Nothing to pull" when the file is what was last deployed or pulled;
   - otherwise keeps the Store as `jmri/layouts/hart/output/pulled/mac-<date>.xml` and records it as taken.
3. Compare the saved Store with `tables.xml` to find the owner's edits (a Store also writes its file history, clock time and memory values, and may reorder beans; those are not edits). Carry each edit into its source.
4. Run `./tools/check.sh` before any commit that changes tables or signals.
5. If tables or panels changed, run `make panelpro-test` when the owner is not operating (AGENTS.md close-out, step 4).
6. Run `python3 tools/schematic/build_tables.py` (or `make panels`), commit the changed sources and `tables.xml` by name, then follow the close-out in AGENTS.md. A changed tables file needs a deploy, which replaces the host's file with the generated one: do it only once the edits are in the sources.

## Why deploy stops

`sync_hart_package.sh` stops with "tables.xml changed since the last deploy" when the Mac's `~/JMRI_UserFiles/tables.xml` differs from the last deployed hash. Run this pull first; it records the Store as taken, so the deploy goes ahead after it. On the Pi the deploy checks before sending anything (`tools/hosts/pi/unpulled_changes.sh`) and stops with "the Pi's tables.xml changed since the last deploy": run `make tables-pull-pi`. `HART_DISCARD_PI_CHANGES=1` replaces the Pi's Store and Operations files anyway, so use it only when the owner says to. Windows is replaced without a check. `HART_OVERWRITE_PROFILE_TABLES=1` skips the guard and throws the Store away, so use it only when the owner says to.

## Sources

- `tools/ops/pull_tables.sh`, `tools/ops/pull_tables_pi.sh`, the `tables-pull` and `tables-pull-pi` targets in `Makefile`
- `wiki/decisions/ADR-008-tables-ownership.md`, `wiki/decisions/ADR-014-jmri-user-files.md`
- `tools/hosts/sync_hart_package.sh` (`install_tables_local`)

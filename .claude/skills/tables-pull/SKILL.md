---
name: tables-pull
description: Use when a PanelPro Store on the Pi or the Mac has changed JMRI_UserFiles/tables.xml and it must come back into the repo, when deploy stops with "tables.xml changed since the last deploy" or "the Pi's tables.xml changed", or before committing after a PanelPro session.
---

# Bring a PanelPro Store into the repo

`jmri/layouts/hart/output/tables.xml` is the one tables file (ADR-008). Every host loads `preference:tables.xml` from `JMRI_UserFiles` (ADR-014). Since R9c it is generated (ADR-029: `tools/schematic/build_tables.py`), so a Store is never copied over it. A Store is split back into the sources instead (R9d, the owner's design of 2026-11-20 in `archive/wiki/projects/project-health-handoff.md`, "R9d redesign"):

- the owner's settings, memories, LogixNG and other new items the build does not claim go into `data/tables_template.xml` (KEPT, no review);
- a rename or comment on a level-less device's row (DEVICE), a device added in the Store, a change to a level-less device, and any template item the repo changed too (CLASH), wait for the owner's merge or drop. Every device edit lands in `devices_field.csv` (the owner's file, edited by key), never in `devices_generated.csv`, which only the builders write (ADR-029 amendment, 2026-11-21). An added device (a test turnout, a DCC accessory) becomes a `devices_field.csv` row with no level, cp or role, its beans kept exactly in `jmri_bean`, until the owner gives its details (owner, 2026-11-20). A new device on a name a row already plans (a virtual row's `system_name`) is dropped, naming that row;
- the repo wins on what the build makes: the device master's beans' other parts, the Layout Editor panel and its LogixNG, the Signal Mast Logic, the Digicon rule (DROPPED, listed with what to change instead).

A Store counts as taken only once its split is merged (`data/store_splits.csv` holds its hash), so a deploy to that host stops until then.

## Before you run it

- Let a Store finish before you pull. A PanelPro or CATS open on the Mac does not stop the script.
- Do not store tables from a CATS session. PanelPro owns `tables.xml`.

## Steps

1. Start a task worktree: `make wt TOPIC=store-split` and work there. The split refuses the main checkout.
2. Pull: `make tables-pull-pi` (Pi) or `make tables-pull` (Mac). It keeps the Store as `media/pulled-stores/<host>-<date>.xml` in the main checkout (gitignored, shared by every worktree) (once per hash) with `<file>.base`, which names what the host had before the session (the deployed commit and its hash). Older Stores may still be in `~/JMRI_UserFiles-pulled` until moved. It does not record the Store as taken. "Nothing to pull" means the host has what was last deployed, or a Store already split in.
3. Report: `python3 tools/schematic/split_store.py <store>`. It prints the plan fingerprint and every item by kind (K, C, D, G ids). `--show <id>` prints one item as a diff. "NO BASE" means the base is not known, so every template change is a CLASH.
4. Review with the owner in chat, multiple choice, up to 4 questions a batch: for each C and D item, merge or drop (give the before and after values). Show the KEPT and DROPPED lists too, so the owner sees what was taken and what the repo overrode; the owner may drop a K item.
5. Apply: `python3 tools/schematic/split_store.py <store> --apply --plan <fingerprint> --merge <C and D ids> [--drop <K ids>]`. It writes the template and the merged `devices_field.csv` cells, rebuilds `tables.xml`, checks the rebuild gives exactly what the plan promised, and records the Store in `store_splits.csv`. On any failure it puts every file back and says why. A merged rename often needs other names changed too (a turnout's FB rows, a block's length row, the discovered logic); the build refuses it, so drop that merge or rename by hand across the sources.
6. If `devices_field.csv` changed, run `make panels CHECK=1` (and `make panels` if it reports stale outputs). A kept section of a new kind (audio, routes) stops the website's tables page until `www/scripts/tables_page.py` `GROUPS` describes it: add that one plain line in the same PR. Any change to `tables.xml` also needs `python3 www/scripts/build_layout_index.py` and `python3 www/scripts/build_tables_browser.py` rerun and their outputs committed.
7. Run `./tools/check.sh`, then `make panelpro-test` (`/done` step 4).
8. Commit the files it names, by name, then follow the close-out (`/done`). After the merge, deploy `--pi --win`: the host's Store now counts as taken, and the deploy replaces it with the generated file that holds its edits.

## Not for a one-line setting

For a memory or clock change, use `tools/schematic/template_edit.py` instead of a Store: it edits the template and rebuilds `tables.xml` (`template_edit.py list`, `memory add|set|remove`, `clock set`, `setting set`; `--dry-run` writes nothing). Pull a Store only for what that tool does not hold.

## Why deploy stops

`sync_hart_package.sh` stops with "tables.xml changed since the last deploy" when the Mac's `~/JMRI_UserFiles/tables.xml` differs from the last deployed hash and no merged split names it. On the Pi the deploy checks before sending anything (`tools/hosts/pi/unpulled_changes.sh`, given the split hashes) and stops with "the Pi's tables.xml changed since the last deploy". In both cases, run the steps above. A Pi deploy now runs the pull itself (no PanelPro quit needed for a Store): it keeps the Store as `pull_tables_pi.sh` does, prints "kept the Pi's Store as <path>; split it ..." and stops, so step 2 is already done and you start at step 3 (`HART_NO_AUTOPULL=1` restores the plain stop). `HART_DISCARD_PI_CHANGES=1` replaces the Pi's Store and Operations files anyway, so use it only when the owner says to. Windows is replaced without a check. `HART_OVERWRITE_PROFILE_TABLES=1` skips the guard and throws the Store away, so use it only when the owner says to.

## Sources

- `tools/ops/pull_tables.sh`, `tools/ops/pull_tables_pi.sh`, `tools/hosts/pi/tables_base.sh`, the `tables-pull` and `tables-pull-pi` targets in `Makefile`
- `tools/schematic/split_store.py`, `tools/hartlib/src/hartlib/store_split.py`
- `wiki/decisions/ADR-008-tables-ownership.md`, `wiki/decisions/ADR-014-jmri-user-files.md`, `wiki/decisions/ADR-029-tables-xml-is-an-output.md`
- `tools/hosts/sync_hart_package.sh` (`install_tables_local`), `tools/hosts/profile_tables_guard.sh` (`hart_split_shas`)

# One bean and row process for every level: plan (2026-11-23)

Status: done (2026-11-24)

Folded into [the naming-layers plan](../../../../wiki/projects/naming-layers-handoff.md) (ADR-033) on 2026-11-24: its steps 1 to 8 are steps 1, 8 to 12, 6 and 13 (step 7) and 14 there, and it no longer waits for main and upper wiring. The findings and the owner's answers below still hold.

The owner parked this on 2026-11-23: it is about 8 PRs and 7 to 9 agent-days, and staging is not harmed by the split today. Pick it up when the main and upper levels' wiring (STATUS, Owed, "Finalize wiring") is close: today's main and upper bean code makes virtual beans only, so the first physical swap needs either this merge or a branch added to code the merge would delete.

## Where it came from

The 2026-11-23 architecture review (repo-auditor) found that ADR-030 ("no file or script per level") is not met. A planning pass at `799e37da` narrowed it:

- **Rows are already one process.** `tools/schematic/build_device_map.py` writes every level's block, occupancy and part rows, and staging's wired turnout, alias and fb rows (`device_map_staging.py` is its helper). The real difference is wired or proposed, a per-device state that the code tests as `level == 1`.
- **Beans are two processes.** Staging's come from `tables_build.master_beans` (`GENERATED_LEVELS = ("1",)`); main and upper's from `le_tables.add_level_objects`, `add_level_sensors`, `add_level_clear` and `add_level_signals` while the panel is drawn, with `IT:HART:C3:<n>` turnouts, DIRECT feedback, block names numbered at draw time from `block_numbering.csv`, fixed comment strings and the sensors-clear LogixNG.
- **Masts are two scripts.** Staging's from `build_masts.py`, main and upper's from `build_device_map.plan_masts`; both call `mast_plan.plan`.
- **Two readers.** `staging_device_map.load` (level 1) and `le_names.level_names` (levels 2 and 3), with the same trial-key grammar since 2026-11-20.

What is truly per level: staging's names are the field's; main and upper have a draft plant and LCOS proposals; staging is drawn at plan lengths; heads are C1 on staging and C3 on main and upper; staging has anchor masts.

## Target

- **Rows:** one builder, `build_device_map.py`, which takes over part 1 of `build_masts.py`. Wired or proposed becomes data (an `lcos_nodes.csv` status column; `wiring.csv` rows decide what is frozen).
- **Beans:** one function, `tables_build.master_beans`, for every row whose `assignment` is not `none`. The bean name is `system_name` for a field row and `jmri_name` otherwise; feedback is TWOSENSOR when the turnout's fb rows have beans, else DIRECT; clear-on-load from `assignment=virtual` and a new `start` column. `GENERATED_LEVELS` and `le_common.BASE_LEVELS` go; `le_tables.py` keeps panel binding and numbering checks.
- **One reader** keyed by `trial_name`, merging `le_names` and `staging_device_map.load`.
- **Swap-in:** every reader takes the bean name from the row's `jmri_name`, so a physical swap is one row edit (ADR-028). The `cats_panel.py` (~540) half is the separate deferred fix in STATUS.

## Owner's answers (2026-11-23)

| Question | Answer |
|----------|--------|
| Main and upper bean comments | Unify the text with staging's in the merge: a listed `tables.xml` diff, `make panelpro-test` and a deploy; no SML rediscovery (comments are outside its digest) |
| Main and upper block and layout-block numbers | Keep today's numbers; they are renumbered when those levels are wired for good. Until then `block_numbering.csv` stays the source and the builder copies the numbers into the rows |
| Anchor masts | One rule on every level; any main or upper mast change goes through the owner's panel approval |
| Order against station maps (level unification step 7) and the wiring freeze | Not decided; the merge was parked instead |

## Staged plan

Each PR leaves `tables.xml`, the desks and `devices_generated.csv` byte-identical unless it says otherwise, and passes `make panels CHECK=1`, `./tools/check.sh` (FULL=1 for the bean PRs, through `make remote`), an unchanged `build_tables.py --base-hash` (no rediscovery) and, for the bean PRs, `make panelpro-test`.

1. **Tests first** (0.5 to 1 day): golden tests of every main and upper bean `le_tables` makes; unit tests of `master_beans` per assignment and of `build_masts.generate` on staging. `build_device_map.py` (833 lines) and `tables_build.py` (963) need cover before anything moves. Check here that the two block length formats agree (`round(v,1):.1f` against `plan_in*25.4:.1f`).
2. **Main and upper block names into the rows** (0.5 day): the builder writes `jmri_name` and `layout_block` from `block_numbering.csv`; `le_tables` reads them instead of numbering. **Done (2026-11-25)** as naming-layers step 8: [Step 8 findings](../../../../wiki/projects/naming-layers-handoff.md#step-8-findings).
3. **`start` column and comment data** (0.5 day): the rows carry what `le_tables` hard-codes. **Done (2026-11-25)** as naming-layers step 9: [Step 9 findings](../../../../wiki/projects/naming-layers-handoff.md#step-9-findings).
4. **Bean shapes by column in `master_beans`** (1 day), still limited to level 1, so no output changes. **Done (2026-11-25)** as naming-layers step 10: [Step 10 findings](../../../../wiki/projects/naming-layers-handoff.md#step-10-findings).
5. **Every level through `master_beans`; delete `add_level_*`** (1 day). With the owner's comment answer this PR has a listed comment diff; every other byte stays. `check_bound`'s split assumes base levels, and `strip_build_owned` recognises beans by name grammar: both change here. **Done (2026-11-25)** as naming-layers step 11, pending the PanelPro test and deploy: [Step 11 findings](../../../../wiki/projects/naming-layers-handoff.md#step-11-findings).
6. **One mast step** (1 to 1.5 days): `build_masts` part 1 into the builder; anchors by one rule (owner's answer), head prefix as data; any main or upper mast change goes to panel approval. **Done (2026-11-25)** as naming-layers step 12, pending the SML discovery and the owner's panel approval: [Step 12 findings](../../../../wiki/projects/naming-layers-handoff.md#step-12-findings).
7. **One reader** (1 to 1.5 days): panel fingerprint unchanged. **Done (2026-11-25)** as naming-layers step 13, keyed by device ID, not `trial_name` (`hartlib.drawing_keys`); the switch facts were moved in step 6: [Step 13 findings](../../../../wiki/projects/naming-layers-handoff.md#step-13-findings). Also the switch facts (owner, 2026-11-23, from the architecture review): `jmri/layouts/hart/scripts/layout_facts.py` (277 lines) is a second, staging-only loader of `switches.csv` and `mast_cells.csv`, used by `cats_panel.py`, `cats/scripts/cats_turnout_io.py`, `gen_ctc_track_plan.py` and tests; `jmri/scripts/check_hart_phase02.py`, `jmri/layouts/hart/scripts/speedmatch/analyze.py` and `tools/wiring/write_inventory.py` read `switches.csv` themselves. Move them onto `hartlib.railroad`, which reads every level, so a column change is made once and main and upper are not missed. Tests first: `layout_facts.py` has `test_layout_facts.py`; the other three need cover of what they read. (`build_hands.py` and `le_common.py` already go through `hartlib.railroad`.)
8. **Level tests to column tests** in `railroad_facts.py` (switch row shape ~246-308, `area` ~479-482), `railroad_invariants.py` (~328), `wiring.py` (~261) and `build_masts.py` (~181), with the docs and an ADR-030 note (1 day). **Done (2026-11-25)** as naming-layers step 14, with a main turnout and detector swapped by their field rows alone in a test copy; the level tests kept as facts of the drawing or the plant are listed there: [Step 14 findings](../../../../wiki/projects/naming-layers-handoff.md#step-14-findings). Every step of this plan is done.

## Risks

- Every module touched is over 400 lines and partly untested; step 1 is not optional.
- It shares readers with level unification step 7 (`stations.csv`, `sheets.csv`): run them one after the other.

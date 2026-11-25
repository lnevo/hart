# Cleanup and streamlining: hand-off (2026-11-25)

Status: active

Two read-only reviews on 2026-11-25 (sessions hart-rc-1 and hart-rc-2: "what is still not ideal in the architecture and pipeline") matched against the work in flight that day. Most findings already belong to an [ADR-037](../decisions/ADR-037-one-step-manifest.md) stage; this page orders the rest. The owner chose the options below on 2026-11-25.

| # | Item | Owner's choice |
|---|---|---|
| 1 | One file per STATUS entry (ADR-038, PR #1126) | Accept, then migrate |
| 2 | A check that fails when a Python file over 800 lines grows | Add it, plus tests for `railroad_facts.py` |
| 3 | Skip-chain gaps in `check_stamps` | Fold into ADR-037 stage 4b |
| 4 | Naming leftovers listed in the review | Went through them: already done, only the notes were stale (step A) |

## How to run this

- One PR per step. Steps A and B are docs; C, D and E are code and get `/code-review medium` (`high` for E, which touches `tools/schematic/`).
- Start each step only after ADR-037 stage 3 (PR #1127) is merged: it rewrites `check.sh` and the map's check edges, which C and D also touch.
- C and D can run in parallel as worktree agents; E runs alone. At most two agents at once.

## A. Stale notes (docs, S)

- `wiki/STATUS.md`: the swap entry still says a real `make panelpro-test` with a detector and a head swapped is to run; PR #1113 and #1122 record that it passed in a sandbox.
- `wiki/projects/naming-layers-handoff.md`: the "Open for step 12" (210LA faces Spur 2), "Open for step 5" (`main_lines.csv` staging names, derived `facing` not followed) and `publish_draft` stamp lines are closed. The step 12 swap made Mast 210LA face Track 209 Spur 1 (`devices_generated.csv`), `main_lines.csv` keys by block ID, `devices.follow_renames` carries renames into `facing` and `protects`, and the stamp is version 4. Mark each closed with its PR.
- Check whether naming step 11's `make panelpro-test` and deploy (hand-off table, row 11) were done by the 2026-11-25 11:31 deploy of `67b6d185`; record it either way. Step E waits on this.
- Worktrees whose lock names an ended session (pid 21210): `layout-docs-log-cars-stations` and `layout-docs-switches-stations` are merged; `naming-step5-tests` holds one commit (`0f37619b`, fixtures moved to the ID-keyed files) that step 5's merge appears to replace. Confirm and remove all three.

## B. ADR-038 migration (S to M)

hart-rc-1 marks the ADR Accepted and merges PR #1126. The migration then splits `wiki/STATUS.md` into `wiki/status/<section>/` entries of at most 60 words, builds STATUS.md with `make status` and the session-start hook, and stops committing it (amends ADR-036 point 4). The near-duplicate check from PR #1124 stays until the migration lands, then runs on the entry files or goes.

## C. ADR-037 stage 4b with the skip-chain gaps (M)

- Split the single `static` job into one job per check, so an unchanged check skips after a commit and in CI.
- Add `HART_CACHE_DIR` and `HART_GUARD_JMRI_RUNNING` to `check_stamps`' `KEY_ENV` (local runs only today).
- In the weekly full run, fail when a job a skipping run left out fails in the full run, so a wrong skip shows within a week.

## D. Size guard and `railroad_facts.py` tests (M)

- A check, from the manifest, that fails when a `.py` file over 800 lines grows past its size in a committed list; shrinking updates the list.
- Growth since 2026-11-22: `railroad_facts.py` 1240 to 1474 lines (no test file of its own), `build_device_map.py` 833 to 1063 (split in health round 2, item 2), `tables_build.py` 963 to 1185, `hartlib` `devices.py` 1057 to 1237.
- Tests for `railroad_facts.py` first; a split, if any, in a later commit that changes no behaviour.

## E. ADR-037 stage 5: the panels step list (M to L)

The panels step list is kept by hand in six places (`build_panels.sh` list and header, `schematic-panels.md`, `test_build_panels.STEPS`, `panel_stamps.STEPS`, the map). Generate them from `panels.toml`. It also clears the stale comment at `tools/schematic/panel_stamps.py` (masts "writes devices_generated.csv"), repeated in the `build_panels.sh` header and a test. ADR-037 point 5 holds it until the naming work (ADR-033) is closed and unclaimed: the hand-off is done, so it waits only on step A's step 11 check.

## Not in this plan

- The cold Layout Editor build (120 s, 69 s of it `sml-current` label placement) after a plugin pin bump: speed only.
- CI skipping unchanged panels steps (ADR-037 stage 6, optional).
- How `docs/INDEX.md` is kept: the owner's call under ADR-036.

## Done when

Steps A to E are merged, `./tools/check.sh` (`FULL=1` through `make remote`) passes on main, and this page is `Status: done`.

# Cleanup and streamlining: hand-off (2026-11-25)

Status: active
Coordinator: hart-95 holds the merge queue across sessions (since 2026-11-25 13:18; `coordinate` skill).

Two read-only reviews on 2026-11-25 (sessions hart-rc-1 and hart-rc-2: "what is still not ideal in the architecture and pipeline") matched against the work in flight that day. Most findings already belong to an [ADR-037](../decisions/ADR-037-one-step-manifest.md) stage; this page orders the rest. The owner chose the options below on 2026-11-25.

| # | Item | Owner's choice |
|---|---|---|
| 1 | One file per STATUS entry (ADR-038, PR #1126) | Accept, then migrate |
| 2 | A check that fails when a Python file over 800 lines grows | Add it, plus tests for `railroad_facts.py`; since 2026-11-25 (size sweep F, PR #1182) it also covers `.js` at 800 lines and `.sh` at 500 and warns at 90 percent of a limit |
| 3 | Skip-chain gaps in `check_stamps` | Fold into ADR-037 stage 4b |
| 4 | Naming leftovers listed in the review | Went through them: already done, only the notes were stale (step A) |

## How to run this

- One PR per step. Steps A and B are docs; C, D and E are code and get `/code-review medium` (`high` for E, which touches `tools/schematic/`).
- Owners (agreed 2026-11-25 13:05): the "agent experience improvements" session owns all of ADR-037 (C and E here, plus 4a, 4c and 6); hart-25 owns A and D; the ADR-038 agent owns B. Only the ADR-037 owner edits `check.sh`, `checks.toml` and `check_stamps.py` while a stage is open; D's guard entry goes in after 4b merges (about 14:15).
- At most 8 non-idle Claude sessions on the Mac, subagents included; heavy checks through `make remote`.

## Merges and checks: one at a time

Parallel PRs kept failing after merge (2026-11-25): GitHub does not require a branch to be up to date with main (`required_status_checks.strict` is false), so two PRs that each passed CI on an old main could merge into a broken or doubled main. Until that changes, the sessions on this plan follow these rules:

- **One merge at a time.** hart-25 holds the merge queue. A session sends hart-25 "ready #N", merges only on "go #N", and replies with the merge commit; the next PR gets its "go" after that.
- **Up to date before merging.** After "go", merge `origin/main` into the branch, push, wait for the required check on that head, then merge. If main moved meanwhile, do it again. No auto-merge, since it skips this.
- **One writer per shared file.** `check.sh`, `checks.toml` and `check_stamps.py`: the ADR-037 owner only; another step's entry goes in through that owner or after its stage merges. `wiki/STATUS.md` is frozen while the ADR-038 migration's PR is open; new entries wait for the entry files.
- **Full checks only on the Windows box** (`make remote`, two slots that queue). On the Mac, only the docs-only path or `CHECK_ONLY=`.

## A. Stale notes (docs, S)

- `wiki/STATUS.md`: the swap entry still says a real `make panelpro-test` with a detector and a head swapped is to run; PR #1113 and #1122 record that it passed in a sandbox.
- `wiki/projects/naming-layers-handoff.md`: the "Open for step 12" (210LA faces Spur 2), "Open for step 5" (`main_lines.csv` staging names, derived `facing` not followed) and `publish_draft` stamp lines are closed. The step 12 swap made Mast 210LA face Track 209 Spur 1 (`devices_generated.csv`), `main_lines.csv` keys by block ID, `devices.follow_renames` carries renames into `facing` and `protects`, and the stamp is version 4. Mark each closed with its PR.
- Naming step 11 shipped: its merge (`adddc0d6`) is in the 2026-11-25 11:31 deploy of `67b6d185`; the hand-off table now says so.
- Ended-session worktrees: the two `layout-docs-*` ones are gone. `naming-step5-tests` (`0f37619b`) matches main file for file, so it is replaced; its worktree holds a submodule, so removing it needs `git worktree remove --force` (the owner's call), then the branch on origin goes.

## B. ADR-038 migration (S to M)

hart-rc-1 marks the ADR Accepted and merges PR #1126. The migration then splits `wiki/STATUS.md` into `wiki/status/<section>/` entries of at most 60 words, builds STATUS.md with `make status` and the session-start hook, and stops committing it (amends ADR-036 point 4). The near-duplicate check from PR #1124 stays until the migration lands, then runs on the entry files or goes.

## C. ADR-037 stage 4b with the skip-chain gaps (M)

Done 2026-11-25: #1136.

- Split the single `static` job into one job per check, so an unchanged check skips after a commit and in CI.
- Add `HART_CACHE_DIR` and `HART_GUARD_JMRI_RUNNING` to `check_stamps`' `KEY_ENV` (local runs only today).
- In the weekly full run, fail when a job a skipping run left out fails in the full run, so a wrong skip shows within a week.

## D. Size guard and `railroad_facts.py` tests (M)

Done 2026-11-25: the tests in #1134, the `py-sizes` guard in #1141.

- A check, from the manifest, that fails when a `.py` file over 800 lines grows past its size in a committed list; shrinking updates the list. Since 2026-11-25 it also covers `.js` files at 800 lines and `.sh` files at 500 and warns at 90 percent of a limit; `check.sh` stays one file (docs/pipeline-map/checks-and-remote.md).
- Growth since 2026-11-22: `railroad_facts.py` 1240 to 1474 lines (no test file of its own), `build_device_map.py` 833 to 1063 (split in health round 2, item 2), `tables_build.py` 963 to 1185, `hartlib` `devices.py` 1057 to 1237.
- Tests for `railroad_facts.py` first; a split, if any, in a later commit that changes no behaviour.

## E. ADR-037 stage 5: the panels step list (M to L)

Done 2026-11-25: #1135.

The panels step list is kept by hand in six places (`build_panels.sh` list and header, `schematic-panels.md`, `test_build_panels.STEPS`, `panel_stamps.STEPS`, the map). Generate them from `panels.toml`. It also clears the stale comment at `tools/schematic/panel_stamps.py` (masts "writes devices_generated.csv"), repeated in the `build_panels.sh` header and a test. ADR-037 point 5 holds it until the naming work (ADR-033) is closed and unclaimed: the hand-off is done, so it waits only on step A's step 11 check.

## Not in this plan

- The cold Layout Editor build (120 s, 69 s of it `sml-current` label placement) after a plugin pin bump: speed only.
- CI skipping unchanged panels steps (ADR-037 stage 6, optional).
- How `docs/INDEX.md` is kept: settled, it stays committed with a union merge and a duplicate check (PR #1119, owner's choice).

## Done when

Steps A to E are merged, `./tools/check.sh` (`FULL=1` through `make remote`) passes on main, and this page is `Status: done`.

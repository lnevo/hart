# ADR-041 — Baselines are lowered at the end of each wave

- **Status:** Accepted
- **Date:** 2026-11-27
- **Deciders:** lnevo

## Context

Four ratchets keep a committed list of counts that may fall but not rise: `check_mypy.py` (`tools/audit/mypy_baseline.json`), `check_habits.py` (`tools/audit/habits_baseline.json`), `check_py_sizes.py` (`tools/audit/py_sizes.csv`) and `check_hand_tables.py` (`tools/audit/hand_tables.csv`). Of 80 recent PRs, 23 changed the mypy baseline, 21 the habits baseline, 16 `hand_tables.csv` and 12 `py_sizes.csv`. Each change made the other open PRs merge `main` again and wait for another CI run, because `main` requires branches to be up to date.

The ratchets already pass when a count falls and print a note. PRs rewrote the lists anyway because the hand-off text told each lane to run `--update`. `check_hand_tables.py` also failed on a row whose table was gone, so a PR that removed a table had to edit the list.

## Decision

1. **Lanes do not lower baselines** (owner, 2026-11-27). A lane runs the ratchets without `--update` and fixes any rise. It adds or changes a row only for a new or moved file.
2. **The queue holder sweeps at the end of each wave** with `make baselines`, which runs the four ratchets' `--update` in turn, in one PR.
3. **A `hand_tables.csv` row for a table no longer found is a note, not a failure** (owner, 2026-11-27). The sweep's `--update` drops it. A new table still needs a row with status `keep` and a reason, and a (file, table) pair listed twice still fails.
4. **`hand_tables.csv` and `py_sizes.csv` merge with git's union driver** (`.gitattributes`). Rows two branches add both stay. A row both branches edited comes out twice, and each file's loader stops on it as "listed twice", so the union never hides a real conflict. `tools/audit/tests/test_union_merge_lists.py` runs both cases. The two JSON baselines keep the default merge.

The text lives in the `handoff` skill (Merge, step 2), the `coordinate` skill (Baseline sweep) and the `tool-fixer` agent.

## Consequences

- Between sweeps the lists run high, and the notes say how many files are below their baseline. A rise is still caught against the higher count.
- Like the other merge drivers, the union merge runs in local merges only, not on GitHub's merge button.
- Dropping the strict up-to-date rule is a separate step (owner), and the wording about merging `main` changes with it ([ADR-042](ADR-042-strict-off-main-push-run-watched.md)).

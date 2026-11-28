# Merging PRs: the mechanics

The one home for the merge rules. The `handoff` skill (alone, or splitting a plan across your own agents) and the `coordinate` skill (beside other sessions) both link here. This file is not a skill: it loads only when one of them points to it.

## Who merges, and when main goes back in

The main session merges, never with `--admin`, through `make land PR=N` (wait for the required check on the head, merge at that head, watch main's push run by full SHA, list the open PRs that must now merge main locally, say what ships).

`make land PR=N` takes a numbered ticket in the merge queue (`/tmp/hart-land-queue/`, `tools/agent/land_queue.py`) and returns at once with the ticket and its log, `~/.cache/hart/land/<N>.log`; a background job does the steps (owner, 2026-11-28). The lowest live ticket merges; the others wait for their own `check` meanwhile, then for their turn, with no time limit while every ticket ahead is alive. A ticket whose process is gone is skipped with a line. Marking a draft ready, the second look at main, the merge and the watch of main's push run happen only at the head. `make land-status` lists the tickets (PR, session, state) and the last lines of each log; `WATCH=1` runs in the foreground with today's exit codes. Until no `make land` from older code can still run, the head also takes the old lock `/tmp/hart-land.lock`, so an old land and a new one never merge together; a later PR removes it. The subagent guard blocks `land.py` and `make land` for subagents, as before. `main` requires `check` to pass on the PR's head. Since `strict` was turned off (owner, 2026-11-27) it no longer requires the branch to be up to date ([ADR-042](../../../wiki/decisions/ADR-042-strict-off-main-push-run-watched.md)). Beside other sessions, merges go through the queue in the `coordinate` skill: no auto-merge, one at a time. Alone, queue auto-merge (`gh pr merge <n> --merge --auto`) once a PR's reviews are done, never before, or a fast CI merges ahead of the findings.

A PR does not merge `origin/main` in again just because main moved. Merge it in only when GitHub shows a conflict, or when the PR's last `check` run is older than the latest change on main to a file the PR touches. Merge locally (never rebase; force-push is blocked), regenerate what the branch owns, push. Say in the PR or to the coordinator why you merged main.

## Merge drivers

Local merges only for files with merge drivers. `.gitattributes` has the full list. The union merge (`tools/audit/hand_tables.csv`, `tools/audit/py_sizes.csv`, `wiki/STATUS_LOG.md`, `docs/INDEX.md`) and the pipeline-map driver (`docs/pipeline-map/pipeline_map.json`) run only in a local `git merge origin/main`. GitHub's merge button, update-branch and the web conflict editor do not run them. A PR that touches any of these files always merges main locally and pushes, never with update-branch or the web editor.

`pipeline_map.json` merges itself locally (`tools/ops/merge_pipeline_map.py`, a git merge driver that `make wt` and the session-start hook set up). It stops only on two different edits to one box or link, or a link left pointing at a deleted box. A PR that shows a conflict there needs `origin/main` merged into the branch locally, then `python3 tools/ops/build_pipeline_map.py --check`. A branch from before ADR-036 that still changes `docs/pipeline-map/index.html` or `www/library/pipeline-map.html` gets a modify/delete conflict on them when it merges main: `git rm` them.

Generated files that several PRs regenerate (`docs/INDEX.md` and the like): each branch regenerates its own. On a rebase conflict, take main's copy and run the generator again (`python3 tools/ops/build_docs_index.py` for the index). Never merge a generated file by hand.

## After a merge

Whoever merged watches main's push run of `check.yml` for the merge commit and reports how it ended: that run catches what two PRs break together. `make land` does this itself; by hand, find it with `gh run list --workflow check.yml --branch main --event push --commit <merge sha>` (the full 40-character SHA, since a short one matches nothing), then `gh run watch <id>`.

**Main red (owner, 2026-11-27):** while main's push run of `check` is red (failure, cancelled or timed out), the queue holder gives no "go". The PR that broke it fixes forward, or one PR reverts it. Nothing deploys: the deploy gate stops a red main itself (G0c, `ci_pass.py --main-red`).

## Baseline sweep (owner, 2026-11-27)

Lanes do not lower baselines (`mypy_baseline.json`, `habits_baseline.json`, `py_sizes.csv`, `hand_tables.csv`); a count that falls passes with a note. At the end of each wave the queue holder runs `make baselines` in one PR, which lowers the first two and `hand_tables.csv`. `py_sizes.csv` rows are caps with 10 percent headroom that are never lowered; the sweep only drops the rows of files gone or at or under their limit. A lane still adds or changes a row for a new or moved file.

## No failed PRs

A branch becomes a PR only after these pass on it, in order. A lane runs steps 1 to 5 with one `make ready FILES=... MSG=... TITLE=... BODY_FILE=...` (`tools/agent/ready.py`), which stops at the first failure and reports the PR, the head and the remote log.

1. `git fetch && git merge origin/main`, then regenerate what the branch owns.
2. The ratchets without `--update`: `check_mypy.py`, `check_habits.py`, `check_py_sizes.py` and `check_ruff.py`. The lane fixes any rise; baselines follow the sweep above.
3. `git add` new files, then `build_pipeline_map.py`, `manifest.py check` and `build_pipeline_map.py --check`.
4. `make static`.
5. Push without a PR, then the gate `make ready` prints in one line. When a changed path feeds a check step that reads a private file (`tools/ci/changed_kind.py --private`; today the AnyRail plan), or with `REMOTE=1`: run `make remote CMD="./tools/check.sh"` with the log saved, and open the PR only on ALL PASSED. Otherwise GitHub's check is the gate: the PR opens as a draft and leaves draft only once that check passes (owner, 2026-11-28).
6. `make land PR=N` watches `check` on the head and merges on its pass (with the queue holder's go beside other sessions); a draft is refused until then and marked ready (`gh pr ready N`) before the merge. Merge `origin/main` again only on a conflict or a stale run as above, then rerun 2 to 4.

The remote box holds private files that GitHub CI lacks, such as the AnyRail plan. A remote pass does not prove CI will pass. Run plan-reading tests without the plan too.

Owner decisions on the gates:

- A docs-only PR skips the full remote run before it opens. It is docs-only when every changed file is Markdown under `wiki/` or `docs/`, Markdown under `.claude/skills/` or `.claude/agents/`, or `AGENTS.md`, and no code, tables, `www/` or `checks.toml` changes. The one generated file it may change is `pipeline_map.json`, and only in the agent-doc lane's boxes and links that `make map` rebuilds from the skills, agents, commands and `AGENTS.md` (owner, 2026-11-27; the rule: `docs/pipeline-map/checks-and-remote.md`, "Docs-only changes"); a folder's `AGENTS.md` and `CLAUDE.md` are full. It still passes `make static` locally and the quick docs checks (`./tools/check.sh` runs only those on a docs-only diff, never the full run) and the required CI before merging.
- A data edit that changes no behaviour skips it too (owner, 2026-11-26), and `make pr-kind` decides it: it prints `light` when every changed file is docs or data that only static checks read, such as the pipeline map's Start presets (the rule: `docs/pipeline-map/checks-and-remote.md`, "Light changes"). It passes `./tools/check.sh`, which then runs the light checks and ends `LIGHT CHECKS PASSED`, then the required CI. Say in the PR body that `make pr-kind` printed `light`. Box labels, descriptions or anything else in `pipeline_map.json`, and a change to anything a script, check, table or host acts on, print `full`.
- Anything else gets the full `make remote` only when it reads private files, as in step 5; the rest opens as a draft with GitHub's check as the gate (owner, 2026-11-28).
- Group related work into fewer PRs: one branch per lane, and small related lanes batched into one PR rather than a PR per step. Each merge costs a CI cycle and a push run on main to watch.

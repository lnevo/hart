---
name: handoff
description: Use when the owner says go on a hand-off or a plan with several independent items, when a job is split across parallel subagents, or when briefing, tracking, merging or closing out several agents' work.
---

# Run a hand-off as parallel agents

`AGENTS.md`, "Subagents", says how to pick an agent and when to ask first; the agents' own descriptions say which fits a job. The progress intervals are under "While they run". On "go" for a hand-off, run its independent items as parallel agents without being asked.

## Split

- When another session runs (`ListAgents`), follow the `coordinate` skill first: find the merge queue's coordinator and the files other lanes own.
- Run `make orient` first: an item on a project page another branch has claimed, or in files a worktree in progress changes, waits or goes to that agent.
- Up to 5 agents, launched in one message, one item each. Items that edit the same files go to one agent, or run one after another.
- Generated files that several PRs regenerate (`docs/INDEX.md` and the like): each branch regenerates its own. On a rebase conflict, take main's copy and run the generator again (`python3 tools/ops/build_docs_index.py` for the index). Never merge a generated file by hand.
- `isolation: "worktree"` branches from main, so an item that needs an unmerged branch waits for that merge.
- Deploys, live hosts, signal logic and LE geometry decisions stay in the main session.
- Check the Mac's load (`uptime`) first. Keep about 2 heavy local jobs per session; agents run full checks and suites through `make remote` after pushing.

## Model

Agents in `.claude/agents/` carry their own model. For others: `haiku` for read-only sweeps (every file that names X, is a page stale); `sonnet` for bounded edits, regenerations and site work; `opus` for logic, data-model, refactor and plugin or tool code, passed explicitly: unnamed subagents default to Sonnet (`CLAUDE_CODE_SUBAGENT_MODEL` in `.claude/settings.json`). Say which agent and model got each item.

## Brief

```
Repo: <path>. Read AGENTS.md first and follow it.
Worktree: create branch agent/claude/<topic> from origin/main (or make wt TOPIC=<topic>).
Claim: <page in wiki/projects/, or none>. First, in your worktree:
  python3 tools/ops/orient.py claim <page>; in your last commit, orient.py unclaim <page>.
Goal: <one or two sentences>. Already ruled out: <...>.
Scope: <paths you may change>. Do not touch: <paths other agents own>.
Quality (code only): 1 clear domain errors, not raw exceptions; 2 no silent fallbacks
  (guessing, defaulting, skipping); 3 invariant checks after mutations; 4 inputs validated
  up front; 5 no duplicated helpers or per-call rebuilds. Test the error paths. Check your
  whole diff against these five before reporting. Reviews here keep finding: paths
  (symlinked worktree mirrors such as media/ and ops/car-cards/, cwd-relative names,
  ../ and ./ segments), git or subprocess failures shown as tracebacks, graph or tree
  walks (shortest level first, cycles), Markdown parsing (wrapped paragraphs, code
  fences, HTML comments, multi-line list items, lines that start with bold), links
  copied into another file without rewriting, and checks that compare more than they
  claim. Test the ones that apply. Also the AGENTS.md "Scripts" habits: no copied
  helpers, `from exc` not `from None`, no dated history in comments, behaviour tests
  not source greps, typed records, annotations that pass mypy.
Checks: single tests while iterating; make static (about 20 s) before each push;
  the full ./tools/check.sh once, through make remote CMD="./tools/check.sh" after
  pushing. Take timings from logs, not re-runs. Rules the static checks enforce, to
  keep in mind while writing: no script outside hartlib reads a layout data file
  (data-readers); every new script or file in an output folder gets a map box, through
  make map (pipeline-map-coverage); Python files stay under their size limit (py-sizes);
  plain writing (ai-speak, public-text).
  Stop your own background jobs by PID or a pattern holding your worktree path, never
  pkill -f a shared script name: other sessions run the same scripts.
Review (code only): after pushing, run /code-review medium (high for the code `/done`
  step 3 names) on your branch while
  make remote runs, fix what it confirms with a test each, push again, and list
  its findings and what you did with each in the report.
Close: commit (stage by name, conventional message), git push -u origin HEAD,
  gh pr create. Do NOT merge.
Progress (required): append one line per milestone, blocker or failed check to
  <scratchpad>/progress/<topic>.log, format "HH:MM <topic> step done/total ETA note"
  (time from date +%H:%M). Interval for this job: <start and end only | every 3 min |
  every 5 min>; with no milestone, write "still on step X, why, new ETA". Before a
  long command (check.sh, make remote, a build), log it and its expected duration;
  log again when it returns.
Report: PR URL, files changed, checks and where they ran, what was skipped, failed,
  left or not checked.
```

Traps every code brief names (waves 1 and 2):
- A dataclass in a module loaded by path without `sys.modules` fails: use a NamedTuple or TypedDict, or register the module.
- Tests that read source text break when code moves: test behaviour.
- Tests name layout data files through the hartlib constants, never literally.
- When code changes from SystemExit to a named error, update every test that asserts SystemExit (grep every test folder).
- A `checks.toml` `quiet_inputs` list keeps the order `test_manifest_scans` expects.
- The Windows box's venv does not follow `requirements.txt` by itself; a new package is installed there by hand.
- A new worktree may need `git submodule update --init`.
- Run a test that reads the private AnyRail plan once with `ANYRAIL_PLAN` set to a missing path before the push; it must skip, not fail.
- Review agents report to their coordinator, not to `main`.

Agents defined in `.claude/agents/` cannot commit, push or open PRs (`subagent_guard.py`). For them, replace Close with: leave changes uncommitted and list the files to stage; the main session commits and opens the PR.

## While they run

Set each brief's interval by the job's expected length: under about 10 minutes, start and end lines only; 10 to 30 minutes, a line at least every 3 minutes; longer, every 5. The main session follows the same intervals in its own reports, and logs before and after each long command (full `check.sh`, `make remote`, a build) with its expected duration. Watch the progress folder with a Monitor that polls every `*.log` in it and tracks each file's line count (`tail -F *.log` misses files created after it starts), prefixes each new line with the file's topic, and put new lines on the wave's live dashboard as they arrive (`dashboard` skill), which every hand-off of more than one agent has. Tell the owner only blockers, decisions and merges. Never report a pending agent's result before it arrives.

## Merge

The main session merges, never with `--admin`. `main` requires `check` to pass on the PR's head; since `strict` was turned off (owner, 2026-11-27) it no longer requires the branch to be up to date ([ADR-042](../../../wiki/decisions/ADR-042-strict-off-main-push-run-watched.md)). When another session runs, merges go through its merge queue (`coordinate` skill): no auto-merge, one at a time. Alone, queue auto-merge (`gh pr merge <n> --merge --auto`) once a PR's reviews are done, never before, or a fast CI merges ahead of the findings. Either way, a PR does not merge `origin/main` in again just because main moved. Merge it in only when GitHub shows a conflict, or when the PR's last `check` run is older than the latest change on main to a file the PR touches; then regenerate what the branch owns and push. After each merge, whoever merged watches main's push run of `check.yml` for the merge commit (`gh run watch`) and reports it: that run catches what two PRs break together. If it ends red, the Main red rule in the `coordinate` skill applies.

Local merges only for files with merge drivers. The union merge (`tools/audit/hand_tables.csv`, `tools/audit/py_sizes.csv`, `wiki/STATUS_LOG.md`, `docs/INDEX.md`) and the pipeline-map driver (`docs/pipeline-map/pipeline_map.json`) run only in a local `git merge origin/main`; `.gitattributes` has the full list. GitHub's merge button, update-branch and the web conflict editor do not run them. A PR that touches any of these files merges main locally and pushes, never with update-branch or the web editor.

`docs/pipeline-map/pipeline_map.json` merges itself locally (`tools/ops/merge_pipeline_map.py`, a git merge driver that `make wt` and the session-start hook set up); it stops only on two different edits to one box or link, or a link left pointing at a deleted box. GitHub never runs it, so a PR that shows a conflict there needs `origin/main` merged into the branch locally, then `python3 tools/ops/build_pipeline_map.py --check`. A branch from before ADR-036 that still changes `docs/pipeline-map/index.html` or `www/library/pipeline-map.html` gets a modify/delete conflict on them when it merges main: `git rm` them.

No failed PRs: a branch becomes a PR only after these pass on it, in order. (1) `git fetch && git merge origin/main`, then regenerate what the branch owns. (2) The ratchets without `--update`: `check_mypy.py`, `check_habits.py`, `check_py_sizes.py`, and `check_ruff.py`; the lane fixes any rise. A lane adds or changes a baseline row only for a new or moved file; the queue holder lowers the baselines at the end of each wave with `make baselines` (owner, 2026-11-27). (3) `git add` new files, then `build_pipeline_map.py`, `manifest.py check` and `build_pipeline_map.py --check`. (4) `make static`. (5) Push without a PR, run `make remote CMD="./tools/check.sh"` with the log saved, and open the PR only on ALL PASSED. (6) Watch `check` on the head and merge on its pass (with the queue holder's go beside other sessions). Merge `origin/main` again only on a conflict or a stale run as above, then rerun 2 to 4. The remote box holds private files that GitHub CI lacks, such as the AnyRail plan. A remote pass does not prove CI will pass. Run plan-reading tests without the plan too.

Owner decisions on the gates:
- A docs-only PR skips the full remote run before it opens. It is docs-only when every changed file is Markdown under `wiki/` or `docs/`, Markdown under `.claude/skills/` or `.claude/agents/`, or `AGENTS.md`, and no code, tables, `www/`, `checks.toml` or generated file changes. It still passes `make static` locally and the required CI before merging.
- A data edit that changes no behaviour skips it too (owner, 2026-11-26), and `make pr-kind` decides it: it prints `light` when every changed file is docs or data that only static checks read, such as the pipeline map's Start presets (the rule: `docs/pipeline-map/checks-and-remote.md`, "Light changes"). It passes `./tools/check.sh`, which then runs the light checks and ends `LIGHT CHECKS PASSED`, then the required CI. Say in the PR body that `make pr-kind` printed `light`. Box labels, descriptions or anything else in `pipeline_map.json`, and a change to anything a script, check, table or host acts on, print `full`.
- Anything else gets the full `make remote`.
- Group related work into fewer PRs: one branch per lane, and small related lanes batched into one PR rather than a PR per step. Each merge costs a CI cycle and a push run on main to watch.

1. Code PRs are reviewed once, by their own agent (brief, Review). The main session does not review them again: it checks that each confirmed finding was fixed, and runs `/code-review low` only when those fixes changed code beyond the finding's own lines. When the agent could not run a review, the main session runs the `/done` step 3 review. Send each finding through `finding-verifier` first; fix what it confirms, check each PLAUSIBLE one against the code, and leave performance and style for later unless trivial. Add a finding that recurs to the list in the brief's Quality line. After a review, check `git branch --show-current` before committing; it can leave a detached HEAD.
2. Queue PRs that others build on first. When one merges, merge `origin/main` into a remaining one only when it now conflicts or its last `check` run predates the merged change to a file it touches (Merge, above), locally (no rebase: force-push is blocked), and regenerate its committed generated files.
3. Deploy once after the last merge if live artifacts changed (`deploy` skill).

## Finish

End with what is done (PR, agent, model), then "nothing left in progress" or what is and why, then loose ends grouped as waiting on the owner, parked, and outside our control. If `not-pending.md` exists in `wiki/` (a parallel PR adds it), drop anything it lists. Ask several owner decisions as multiple choice, up to 4 at a time, recommended option first.

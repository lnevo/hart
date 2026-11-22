---
name: handoff
description: Use when the owner says go on a hand-off or a plan with several independent items, when a job is split across parallel subagents, or when briefing, tracking, merging or closing out several agents' work.
---

# Run a hand-off as parallel agents

`AGENTS.md`, "Subagents", says which agent fits a job and when to ask first; "Status reporting" sets the progress rules. On "go" for a hand-off, run its independent items as parallel agents without being asked.

## Split

- Up to 5 agents, launched in one message, one item each. Items that edit the same files go to one agent, or run one after another.
- Generated files that several PRs regenerate (`docs/INDEX.md` and the like): each branch regenerates its own. On a rebase conflict, take main's copy and run the generator again (`python3 tools/ops/build_docs_index.py` for the index). Never merge a generated file by hand.
- `isolation: "worktree"` branches from main, so an item that needs an unmerged branch waits for that merge.
- Deploys, live hosts, signal logic and LE geometry decisions stay in the main session.
- Check the Mac's load (`uptime`) first. Keep about 2 heavy local jobs per session; agents run full checks and suites through `make remote` after pushing.

## Model

Agents in `.claude/agents/` carry their own model. For others: `haiku` for read-only sweeps (every file that names X, is a page stale); `sonnet` for bounded edits, regenerations and site work; the default model for logic, data-model, refactor and plugin or tool code. Say which agent and model got each item.

## Brief

```
Repo: <path>. Read AGENTS.md first and follow it.
Worktree: create branch agent/claude/<topic> from origin/main (or make wt TOPIC=<topic>).
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
  claim. Test the ones that apply.
Checks: single tests while iterating; the full ./tools/check.sh once, through
  make remote CMD="./tools/check.sh" after pushing. Take timings from logs, not re-runs.
  Stop your own background jobs by PID or a pattern holding your worktree path, never
  pkill -f a shared script name: other sessions run the same scripts.
Review (code only): after pushing, run /code-review medium on your branch while
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

Agents defined in `.claude/agents/` cannot commit, push or open PRs (`subagent_guard.py`). For them, replace Close with: leave changes uncommitted and list the files to stage; the main session commits and opens the PR.

## While they run

Set each brief's interval by the job's expected length (`AGENTS.md`, "Status reporting"). Watch the progress folder with a Monitor that polls every `*.log` in it and tracks each file's line count (`tail -F *.log` misses files created after it starts), prefixes each new line with the file's topic, and pass new lines to the owner as they arrive, as one short table of every agent (item, agent, model, stage, ETA). Never report a pending agent's result before it arrives.

## Merge

The main session merges, never with `--admin`. It queues GitHub auto-merge (`gh pr merge <n> --merge --auto`, on for the repo) once a PR's reviews are done, so the PR merges when its required `check` passes on its newest commit, with no polling. Never queue it before the reviews finish, or a fast CI merges ahead of the findings; a commit pushed afterwards makes auto-merge wait for that commit's check. `main` does not require PRs to be up to date (`strict` is off), so before queueing a PR that regenerates a shared output (`docs/INDEX.md`, the pipeline map, panels, `tables.xml`), merge `origin/main` into it and regenerate. CI on `main` after each merge catches what two PRs break together.

`docs/pipeline-map/pipeline_map.json` merges itself locally (`tools/ops/merge_pipeline_map.py`, a git merge driver that `make wt` and the session-start hook set up); it stops only on two different edits to one box or link, or a link left pointing at a deleted box. GitHub never runs it, so a PR that shows a conflict there needs `origin/main` merged into the branch locally, then the map pages rebuilt (`python3 tools/ops/build_pipeline_map.py` and the `--public` site build the driver prints).

1. Code PRs are reviewed by their own agent (brief, Review). Before merging, the main session runs `/code-review low` on the PR to catch what the fixes broke; when the agent could not run a review, it runs `/code-review medium` instead. Fix confirmed correctness bugs, check each unverified finding against the code, and leave performance and style for later unless trivial. Add a finding that recurs to the list in the brief's Quality line. After a review, check `git branch --show-current` before committing; it can leave a detached HEAD.
2. Queue PRs that others build on first. When one merges, merge `origin/main` into each remaining one (no rebase: force-push is blocked), regenerate its generated files, and leave auto-merge to wait for CI again.
3. Deploy once after the last merge if live artifacts changed (`deploy` skill).

## Finish

End with what is done (PR, agent, model), then "nothing left in progress" or what is and why, then loose ends grouped as waiting on the owner, parked, and outside our control. If `not-pending.md` exists in `wiki/` (a parallel PR adds it), drop anything it lists. Ask several owner decisions as multiple choice, up to 4 at a time, recommended option first.

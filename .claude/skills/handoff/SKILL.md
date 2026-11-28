---
name: handoff
description: Use when the owner says go on a hand-off or a plan with several independent items, when a job is split across parallel subagents, or when briefing, tracking, merging or closing out several agents' work.
---

# Run a hand-off as parallel agents

`AGENTS.md`, "Subagents", says how to pick an agent and when to ask first; the agents' own descriptions say which fits a job. The progress intervals are under "While they run". On "go" for a hand-off, run its independent items as parallel agents without being asked.

## Split

- When another session runs (`ListAgents`), follow the `coordinate` skill first: find the merge queue's coordinator and the files other lanes own. Merge mechanics, merge-driver files and the gates are in [`merging.md`](../coordinate/merging.md); generated files that several PRs regenerate follow the rule there.
- Run `make orient` first: an item on a project page another branch has claimed, or in files a worktree in progress changes, waits or goes to that agent.
- Up to 5 agents, launched in one message, one item each. Items that edit the same files go to one agent, or run one after another.
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
Code only: read .claude/skills/handoff/brief-reference.md (the five quality rules, what
  reviews keep finding, checks to run, the review step, the traps) and check your whole
  diff against it before reporting.
Gates: .claude/skills/coordinate/merging.md, "No failed PRs", before the PR opens.
  A docs-only lane runs make static (or the named static checks), never a local full
  ./tools/check.sh; CI runs check.sh on the PR.
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

Set each brief's interval by the job's expected length: under about 10 minutes, start and end lines only; 10 to 30 minutes, a line at least every 3 minutes; longer, every 5. The main session follows the same intervals in its own reports, and logs before and after each long command (full `check.sh`, `make remote`, a build) with its expected duration. Watch the progress folder with a Monitor that polls every `*.log` in it and tracks each file's line count (`tail -F *.log` misses files created after it starts), prefixes each new line with the file's topic, and put new lines on the wave's live dashboard as they arrive (`dashboard` skill), which every hand-off of more than one agent has. Tell the owner only blockers, decisions and merges. Never report a pending agent's result before it arrives.

## Merge and close

Merge mechanics (when main goes back into a branch, merge-driver files, the post-merge watch, Main red, the baseline sweep, the "No failed PRs" gates, docs-only and `make pr-kind` light PRs, batching lanes into fewer PRs): [`merging.md`](../coordinate/merging.md). Beside other sessions, merges go through the `coordinate` skill's queue.

1. Code PRs are reviewed once, by their own agent (`brief-reference.md`, Review). The main session does not review them again: it checks that each confirmed finding was fixed, and runs `/code-review low` only when those fixes changed code beyond the finding's own lines. When the agent could not run a review, the main session runs the `/done` step 3 review. Send each finding through `finding-verifier` first; fix what it confirms, check each PLAUSIBLE one against the code, and leave performance and style for later unless trivial. Add a finding that recurs to the Quality list in `brief-reference.md`. After a review, check `git branch --show-current` before committing; it can leave a detached HEAD.
2. Queue PRs that others build on first. When one merges, merge `origin/main` into a remaining one only by the rule in `merging.md`, and regenerate its committed generated files.
3. Deploy once after the last merge if live artifacts changed (`deploy` skill).

## Finish

End with what is done (PR, agent, model), then "nothing left in progress" or what is and why, then loose ends grouped as waiting on the owner, parked, and outside our control. If `not-pending.md` exists in `wiki/` (a parallel PR adds it), drop anything it lists. Ask several owner decisions as multiple choice, up to 4 at a time, recommended option first. An owner ruling about how a skill, tool or check works goes into that skill or the wiki in the lane's own PR; memory keeps only what has no place in the repo (private facts, owner preferences).

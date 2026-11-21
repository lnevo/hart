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
  whole diff against these five before reporting.
Checks: single tests while iterating; the full ./tools/check.sh once, through
  make remote CMD="./tools/check.sh" after pushing. Take timings from logs, not re-runs.
Close: commit (stage by name, conventional message), git push -u origin HEAD,
  gh pr create. Do NOT merge.
Progress (required): append one line per milestone, blocker or failed check to
  <scratchpad>/progress/<topic>.log, format "HH:MM step done/total ETA note".
Report: PR URL, files changed, checks and where they ran, what was skipped, failed,
  left or not checked.
```

Agents defined in `.claude/agents/` cannot commit, push or open PRs (`subagent_guard.py`). For them, replace Close with: leave changes uncommitted and list the files to stage; the main session commits and opens the PR.

## While they run

Keep one table of every agent (item, agent, model, stage, ETA) from the progress files, updated at each state change. Never report a pending agent's result before it arrives.

## Merge

The main session merges, one PR at a time, once its required check passes, never with `--admin`.

1. Code PRs first get `/code-review medium`. Fix confirmed correctness bugs, check each unverified finding against the code, and leave performance and style for later unless trivial. After a review, check `git branch --show-current` before committing; it can leave a detached HEAD.
2. Merge PRs that others build on first. Rebase each remaining one on the new main, regenerate its generated files, and wait for CI again.
3. Deploy once after the last merge if live artifacts changed (`deploy` skill).

## Finish

End with what is done (PR, agent, model), then "nothing left in progress" or what is and why, then loose ends grouped as waiting on the owner, parked, and outside our control. If `wiki/not-pending.md` exists, drop anything it lists. Ask several owner decisions as multiple choice, up to 4 at a time, recommended option first.

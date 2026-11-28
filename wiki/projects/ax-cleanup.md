# Agent experience cleanup (2026-11-27)

Status: active
Coordinator: hart-4e, since 2026-11-27 22:20
Dashboard: https://claude.ai/artifact/PzHCqE42g9vDyXrXgdWJvC

The owner asked on 2026-11-27 for a second look at the agent experience after the round of 2026-11-25 (#1104 to #1107). The review rated it about 8.5 of 10 and named four costs: memory had grown back from 32 to 49 files with overlaps and one conflict, every session start printed a line per kept worktree, `.claude/progress/` held 37 stale files, and two skills loaded more than 2,000 words each.

## Owner's choices

- The AWS guidance loads in no session unless the owner asks: it is a personal skill (`aws-guidance`), shown only by its description, and the AWS MCP server is off by default. Both live outside the repo.
- The session cap starts at 8 and stays flexible: more while the Mac's load is low, with heavy jobs one or two at a time.
- Each `SKILL.md` stays at or under 1,500 words; detail goes in a reference file the skill links to.
- A worktree whose merged PR has later commits is removed when every later patch is already on `main`.
- Lane agents ship their own work: `make ready` runs the gates, commits, pushes, runs `make remote` under a lock shared across sessions and opens the PR. The guard opens for that command only; merging, deploys and hosts stay with the coordinator (round 2).
- Reference files in `.claude/skills/` and `.claude/agents/` share the 1,500-word cap.
- When the owner gives a ruling, say in one line where it will live and put it there in the same PR (`AGENTS.md`).

## Lanes

| Lane | Scope | Agent | Ships |
|------|-------|-------|-------|
| AX-L0 AWS | the AWS block moved to a personal skill; the MCP server removed from the user config | coordinator | nothing |
| AX-L1 Memory | 49 to 38 memories: overlapping entries merged, what `AGENTS.md` says dropped, the session-cap conflict settled | coordinator | nothing |
| AX-L2 Sweep | one summary line at session start; worktrees with nothing of their own removed sooner; stale progress files pruned; tests | `tool-fixer`, opus | nothing |
| AX-L3 Skill cap | a check that fails a `SKILL.md` over 1,500 words; the `AGENTS.md` session-cap sentence | `tool-fixer`, opus | nothing |
| AX-L4 deploy | the script internals moved to a `docs/hosts/` page; the skill keeps the steps and stop conditions | `general-purpose`, sonnet | nothing |
| AX-L5 handoff | the merge rules given one home that `handoff` and `coordinate` link to | `general-purpose`, sonnet | nothing |

### Round 2

One PR, `agent/claude/ax-round2`, carries every round 2 lane.

| Lane | Scope | Agent | Ships |
|------|-------|-------|-------|
| R2-L1 make ready | `make ready` (`tools/agent/ready.py`) commits, checks, pushes, runs `make remote` and opens the PR; `subagent_guard.py` lets that one command through; named agents ship with it; `win_run.sh` waits for a free remote slot | `tool-fixer`, opus | nothing |
| R2-L2 changed kind | the root `AGENTS.md` and agent-doc map changes count as docs in `changed_kind.py`; `check.sh` says why a run is full; tests of its path choice | `tool-fixer`, opus | nothing |
| R2-L5 overlap | `make orient` lists files changed in two or more worktrees or PRs (`orient_overlap.py`) | `tool-fixer`, opus | nothing |
| R2-L6 dash rows | `tools/agent/dash_rows.py` writes dashboard rows, events and samples stamped from the Mac's clock | `tool-fixer`, opus | nothing |
| R2-L7 make land | `make land PR=N` waits for the check, merges at the head, watches main's push run and lists PRs that must merge main | `tool-fixer`, opus | nothing |
| Owner rulings | `AGENTS.md` to about 900 words (habits to `tools/AGENTS.md`, the LCOS bridge to `jmri/AGENTS.md`); the 1,500-word cap on every skill and agent file; skills name `make ready` and `make land`; the session cap starts at 8 and is flexible; review fixes in one push | `general-purpose`, opus | nothing |

## Round 3

| Lane | What | Agent | Waits on |
|------|------|-------|----------|
| R3-L1 GitHub gate | `make ready` runs `make remote` only when a changed path feeds a check that reads private files (`changed_kind.py --private`, today the AnyRail plan), else opens a draft PR that `make land` marks ready once `check` passed (owner, 2026-11-28); changed paths read NUL-separated and the remote clone fetches `origin/main`; `make land` holds a one-slot merge lock across sessions; `make orient` prints the queue holder from `Coordinator:` lines | `tool-fixer`, opus | nothing |

## Done when

Every lane PR has merged, the new sweep has run once on the Mac, and this page says done.

## Rounds 4 and 5 (2026-11-28)

The 7.5 rescore found Memory 6.5 and Housekeeping 5.5; the owner asked to fix both before stopping.

| Lane | Scope | PR |
|------|-------|----|
| R4-L1 Housekeeping | the sweep removes clean worktrees with nothing beyond `origin/main`, PR or not (7 days for `make wt`, 1 hour for `agent-*`); progress files archive after 1 day; orient ignores stale page copies | #1386 |
| R4-L2, R4-L3 Memory | the rules in 26 memory files moved to the skills, `AGENTS.md` files and wiki pages they govern; memory cut to 14 files | #1382, #1383 |
| R5-L1 Land queue | `make land` takes a FIFO ticket and returns; a background job merges in order with no wait limit; `make land-status`, `make land-wait` (GitHub's merge queue needs an organization-owned repo) | #1388 |
| R5-L2 Dashboard sync | `dash_rows.py sync-prs` marks rows from GitHub, so a merge shows without a message; the feed sorts past midnight | #1389 |

Rescore after these: 8.5 (see [report-cards](../report-cards.md#agent-experience)).


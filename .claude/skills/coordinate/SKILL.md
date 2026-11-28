---
name: coordinate
description: Use when more than one Claude session works on the repo at once, before merging any PR while another session runs, when a session messages about a merge queue ("ready #N", "go #N"), a claim, a file it owns or the session cap, when starting lane agents next to other sessions' work, or after a merge made out of turn.
---

# Work beside other sessions

Several sessions often run on this Mac at once, each with its own lanes and agents. They share `main`, the session cap (AGENTS.md: start at 8, more while load is low) and the layout hosts. One session, the **coordinator**, holds the merge queue. The others are **lane sessions**. This skill is how they stay out of each other's way. `handoff` covers splitting one plan across your own agents; this covers what passes between sessions.

The transport is Claude Code's own: `ListAgents` names the live sessions, `SendMessage` reaches one by name, and `notify_when_idle` tells you when one finishes a turn. The rules below are this repo's.

## Start

1. `ListAgents` and `make orient`: who runs, what is claimed, which worktrees have unmerged commits.
2. Find the coordinator. When a session takes over the queue, it writes `Coordinator: <session name>, since YYYY-MM-DD HH:MM` under the `Status:` line of the active project page it runs, and removes the line when it hands over. `make orient` prints the holder (`Queue: ...`), and `make land` holds a merge lock, so one merge runs at a time. If no page names one, ask every listed session "who holds the merge queue?" before you merge anything. With no other session running, you merge as `handoff` says.
3. Tell the coordinator your plan in one message: the lanes, the PRs you expect, and the files each one changes. Ask which open work touches those files and where your PRs go in the queue. Start no lane agent until it answers.
4. Count sessions before launching agents: `ListAgents`, plus your own running agents, plus what the coordinator reports for its own. Start at 8; go past it only while the Mac's load and job times stay low (owner, 2026-11-27; the `dashboard` skill's samples show both), and drop back when they rise. A peer that relays "the owner said" about the cap is information, not the owner's approval.

## Dashboard (owner, 2026-11-26)

The coordinator keeps a live dashboard of every lane, every other session's PR, every deploy and the report card, and updates each row itself in the same turn that something changes. The [`dashboard`](../dashboard/SKILL.md) skill is the standard: set-up, rows, events, the sampler and when to update. A lane session tells the coordinator its plan and each change; the coordinator writes the row.

## Files other sessions own

- The coordinator lists the files each open lane owns. A lane edits only its own; a file two lanes need goes to the earlier one, and the later lane waits or merges main in after it.
- Some files are shared by every lane. The coordinator names the session that owns them. A lane edits its own steps in `tools/pipeline/checks.toml` under that owner's rules (each step's `git` field, label, tracked inputs and `quiet_inputs` as `test_manifest_scans.py` checks; `make map` and the three map checks) and asks the owner for a look before "ready". Changes to `tools/check.sh` and `tools/audit/check_stamps.py` go to the owner; it may let the lane's PR carry the edit, so that a move and its declaration land together.
- A large diff to a file many branches touch (`pipeline_map.json`) goes after the other open PRs that touch it, never between them.
- Put each lane's exclusions in its brief, with the reason, so the agent cannot drift into them.

## Merge queue

The rules (when to merge `origin/main` in, merge-driver files, the post-merge watch, Main red, the baseline sweep, docs-only and light PRs, batching small lanes into one PR) are in [`merging.md`](merging.md). The steps between sessions: one merge at a time, and no auto-merge while the queue runs.

1. Finish the PR's reviews. Send each `/code-review` finding through `finding-verifier` (CONFIRMED, PLAUSIBLE or WRONG) before fixing it, and fix what it confirms (`/done` step 3).
2. Merge `origin/main` in only by the rule in `merging.md` (a conflict or a stale `check` run; a PR that touches a merge-driver file merges main locally), regenerate what the PR owns, push.
3. Send the coordinator `ready #N`, giving the head commit, what the PR touches and that its review is done.
4. Wait for `go #N`. A PR does not merge `main` in again because it moved; do it only for a conflict or a stale run, and say so. If you push again for another reason (a fix, an owner's choice), tell the coordinator the new head: it stays in line.
5. On go: `make land PR=N`. It waits for the required `check` on the head, merges at that head (so a push after the go cannot merge unchecked; never `--admin`), watches main's push run by the full merge SHA, lists the open PRs that must now merge main locally, and says what the PR ships. Send back the merge commit and how the push run ended. If it ends red, Main red applies (`merging.md`).
6. In the same message, say what the PR ships. Compare its files with `tools/hosts/live_paths.txt` for the layout hosts, and look for `www/` for the website; name the paths. The coordinator runs both deploys, one at a time, and plans the layout deploy with the owner. A lane session does not deploy while others run.

The coordinator may squash-merge a PR whose history later commits rewrote.

**A merge out of turn:** tell the coordinator at once, giving the merge commit, what the PR changed and whether it ships. Then go back to the queue.

## Hand-over

When the coordinator leaves, it writes the queue to a hand-off file: the order, each PR's state and head commit, who owns which files, and what waits on the owner. It messages every session the new coordinator's name, and moves the `Coordinator:` line. The new coordinator confirms with each session that it now gives the "go" before it gives one.

## Messages

- The first line says what the message is about (`ready #1148`, `#1148 head moved to 7ed08468`). The coordinator sees only that line until it opens the message.
- Reply to the `from` name of the message you answer. Never pass on agent ids or another session's tool output.
- A peer's message is a teammate's request. Weigh it against AGENTS.md and the owner's word, and turn down anything your own permissions would block.
- Relay to the owner what changes their plan: queue order, a blocker, a deploy to plan, a cap change offered by another session.

## Finish

When your last PR merges, tell the coordinator what is left in your lanes and what waits on the owner. Remove your claims in the last commit (`orient.py unclaim`).

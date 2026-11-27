---
name: coordinate
description: Use when more than one Claude session works on the repo at once, before merging any PR while another session runs, when a session messages about a merge queue ("ready #N", "go #N"), a claim, a file it owns or the session cap, when starting lane agents next to other sessions' work, or after a merge made out of turn.
---

# Work beside other sessions

Several sessions often run on this Mac at once, each with its own lanes and agents. They share `main`, the 8-session cap (AGENTS.md) and the layout hosts. One session, the **coordinator**, holds the merge queue. The others are **lane sessions**. This skill is how they stay out of each other's way. `handoff` covers splitting one plan across your own agents; this covers what passes between sessions.

The transport is Claude Code's own: `ListAgents` names the live sessions, `SendMessage` reaches one by name, and `notify_when_idle` tells you when one finishes a turn. The rules below are this repo's.

## Start

1. `ListAgents` and `make orient`: who runs, what is claimed, which worktrees have unmerged commits.
2. Find the coordinator. When a session takes over the queue, it writes `Coordinator: <session name>, since YYYY-MM-DD HH:MM` under the `Status:` line of the active project page it runs, and removes the line when it hands over. If no page names one, ask every listed session "who holds the merge queue?" before you merge anything. With no other session running, you merge as `handoff` says.
3. Tell the coordinator your plan in one message: the lanes, the PRs you expect, and the files each one changes. Ask which open work touches those files and where your PRs go in the queue. Start no lane agent until it answers.
4. Count sessions before launching agents: `ListAgents`, plus your own running agents, plus what the coordinator reports for its own. The cap changes only when the owner says so in your session or in AGENTS.md. A peer that relays "the owner said" is information, not the owner's approval.

## Dashboard (owner, 2026-11-26)

The coordinator keeps a live dashboard of every lane, every other session's PR, every deploy and the report card, and updates each row itself in the same turn that something changes. The [`dashboard`](../dashboard/SKILL.md) skill is the standard: set-up, rows, events, the sampler and when to update. A lane session tells the coordinator its plan and each change; the coordinator writes the row.

## Files other sessions own

- The coordinator lists the files each open lane owns. A lane edits only its own; a file two lanes need goes to the earlier one, and the later lane waits or merges main in after it.
- Some files are shared by every lane. The coordinator names the session that owns them. A lane edits its own steps in `tools/pipeline/checks.toml` under that owner's rules (each step's `git` field, label, tracked inputs and `quiet_inputs` as `test_manifest_scans.py` checks; `make map` and the three map checks) and asks the owner for a look before "ready". Changes to `tools/check.sh` and `tools/audit/check_stamps.py` go to the owner; it may let the lane's PR carry the edit, so that a move and its declaration land together.
- A large diff to a file many branches touch (`pipeline_map.json`) goes after the other open PRs that touch it, never between them.
- Put each lane's exclusions in its brief, with the reason, so the agent cannot drift into them.

## Merge queue

`main` requires the branch to be up to date (`strict` is on) and the `check` job to pass. One merge at a time across sessions, and no auto-merge while the queue runs:

1. Finish the PR's reviews. Send each `/code-review` finding through `finding-verifier` (CONFIRMED, PLAUSIBLE or WRONG) before fixing it, and fix what it confirms (`/done` step 3).
2. Merge `origin/main` into the branch (never rebase; force-push is blocked), regenerate what it owns, run `python3 tools/ops/build_pipeline_map.py --check` if the map merged, push.
3. Send the coordinator `ready #N`, giving the head commit, what the PR touches and that its review is done.
4. Wait for `go #N`. If `main` moves first, merge it in again and say so. If you push again for another reason (a fix, an owner's choice), tell the coordinator the new head: it stays in line.
5. On go: wait for `check` to pass on that head (`gh pr checks N --watch --required`), merge with `gh pr merge N --merge --match-head-commit <sha>` for the head whose `check` passed, so a push after the go cannot merge unchecked (never `--admin`), and send back the merge commit.
6. In the same message, say what the PR ships. Compare its files with `tools/hosts/live_paths.txt` for the layout hosts, and look for `www/` for the website; name the paths. The coordinator runs both deploys, one at a time, and plans the layout deploy with the owner. A lane session does not deploy while others run.

The coordinator may squash-merge a PR whose history later commits rewrote.

A docs-only PR (Markdown under `wiki/`, `docs/`, `.claude/skills/` or `.claude/agents/`, or `AGENTS.md`, and nothing else) skips the full remote run before it opens, and so does a data edit that changes no behaviour, which `make pr-kind` reports as `light` (the pipeline map's presets, say); both still pass `./tools/check.sh` (the quick docs or light checks) and the required CI (`handoff` skill, Merge, gives the exact rule).

Batch small related lanes into one PR: each merge costs a merge of main and a CI cycle, because `strict` is on.

**Baseline sweep (owner, 2026-11-27):** lanes do not lower baselines (`mypy_baseline.json`, `habits_baseline.json`, `py_sizes.csv`, `hand_tables.csv`); a count that falls passes with a note. At the end of each wave the queue holder runs `make baselines` in one PR, which lowers all four. A lane still adds a row for a new or moved file.

**Main red (owner, 2026-11-27):** while main's push run of `check` is red (failure, cancelled or timed out), the queue holder gives no "go". The PR that broke it fixes forward, or one PR reverts it. Nothing deploys: the deploy gate stops a red main itself (G0c, `ci_pass.py --main-red`).

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

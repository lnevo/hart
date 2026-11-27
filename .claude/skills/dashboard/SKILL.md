---
name: dashboard
description: Use when coordinating more than one lane, agent or session (a wave, a hand-off, a merge queue), when the owner asks for status or an ETA, when a lane, PR, merge, deploy or report card changes state, when the dashboard looks stale, or before a /clear while a wave runs.
---

# Live dashboard

The owner follows a wave on one page, not in the chat. The coordinator keeps that page true: every lane, every PR from every session, every deploy, the report card, the host load and how many Claude sessions and agents are running. "you're the coordinator it's your job to keep track and keep me posted through the dashboard" (owner, 2026-11-26).

## Who writes it

- **The coordinator, itself.** Not the lane, not the peer session, not the steward on its own say. A lane or a session in another window may have no dashboard access, may stop, or may forget; its row then goes stale while the owner reads it. When a message changes something, update its row in the same turn as you act on the message.
- A background coordinator agent or steward may write rows too, but the coordinator checks them. A writer with no `ArtifactData` puts the same updates as JSON lines in its progress folder, and the coordinator copies them across.
- Results that change the page (a deploy, a merge, a failed check) come to the coordinator directly. A steward that reports to a background coordinator sends the coordinator a copy too; relays get lost.

## Set up (once per wave)

1. Create it from the Dashboard artifact type: Artifact `quickstart` with intent `other`, then publish with its `type_url`.
2. One `ArtifactData` batch: `dash/meta`, three datasets with `source: {kind: "store", path: …}` (`lanes` at `data/<wave>/lanes`, `events` at `data/<wave>/events`, `samples` at `data/<wave>/samples`), and `files/index.html` with its `{text}` from [`index.html`](index.html).
3. Put the link on the project page under the `Coordinator:` line and give it to the owner once.
4. Start the sampler (below).

## Rows

One lanes doc per item the owner would ask about: {lane, short, scope, status, stage, pr, eta, updated, order}.

- **Every lane**, ids `<wave>-L<n>` (`3-L7`). A lane split in two keeps one row and lists both PRs.
- **Every PR another session sends to the queue**, ids `<wave>-P<pr>` (`3-P1271`), named for the session. Add it when the session first tells you its plan, not when it is ready.
- **The report card** (`<wave>-RC`) and anything else with an ETA the owner waits on.
- `status` is one of queued, running, remote, review, ci, merged, done, blocked or failed. `stage` says what is happening now in one line, with the PR head, the remote result and what it ships. `updated` and every time come from `date +%H:%M`, never from an agent's own clock: agents' stamps ran ahead twice on 2026-11-26.
- Write with `update` and `if_version` on a row, `set` for a new one.

## Events

One events doc {at, text} for each merge (with its merge commit), deploy (host, exit code, Build counts or stamp), owner ruling, blocker, and the end of the wave. Ids `e<wave>-HHMM`.

## When to update

On every message that changes a lane or PR: it starts, passes or fails its gates, starts or ends a remote run, opens a PR, is ready, merges, deploys, changes its ETA or is blocked. Before telling the owner anything, read the rows you are about to describe and fix any that do not match GitHub (`gh pr view N --json state,mergeCommit,headRefOid`). The owner's "status" or "eta" then gets the link and one line.

## Samples

`samples` docs hold {at, mac_load1, mac_cpus, win_load1, win_cpus, win_remote_runs, sessions, subagents, claude_total}, one every 2 minutes.

- Run [`sampler.sh`](sampler.sh) `<out.jsonl>` under a Monitor in 30-minute windows; whoever holds it re-arms it when the window ends. It prints `SYNC HH:MM` every 10 minutes; on each, write the new lines as docs `sHHMM`.
- The sampler counts sessions (claude processes on this Mac) and subagents (task outputs written in the last 3 minutes) itself. Do not depend on `ListAgents` for counts: a steward has no `ListAgents`, and from 19:10 to 22:53 on 2026-11-26 no counts were written at all.
- If counts are missing for a stretch, fill them from file times: a session runs from its transcript's first write to its last (`~/.claude/projects/*/*.jsonl`), an agent from its task output's first write to its last. Mark them estimates.
- The owner raises the session cap while the load stays under the CPU counts (AGENTS.md, memory note on parallel timing); the samples are how you see it, and job times against earlier runs are how you see slowdown.

## Before a /clear and at the end

- Before a /clear: the steward that takes over gets the dashboard link, the sampler's output file and Monitor, and this skill. The project page keeps the link.
- At the end: final events, every row merged, done or moved to a later wave with a reason, the sampler stopped, and the wave page set to `Status: done`.

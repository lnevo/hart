---
name: dashboard
description: Use when coordinating more than one lane, agent or session, when the owner asks for status or an ETA, when a lane, PR, deploy or report card changes state, or before a /clear.
---

# Live dashboard

The owner follows a wave on one page, not in the chat. The coordinator keeps that page true: every lane, every PR from every session, every deploy, the report card, the host load and how many Claude sessions and agents are running (owner, 2026-11-26).

## Who writes it

- **The coordinator owns every row and checks it.** A lane or a session in another window may have no dashboard access, may stop or may forget, and its row then goes stale while the owner reads it. When a message changes a lane or PR, update that row in the same turn.
- A steward or background coordinator may write rows too, and the coordinator checks them against GitHub (see When to update). A writer without `ArtifactData` appends `dash_rows.py` op lines (`row 3-L7 status=ci stage=remote`, `event "Merged #1371"`; no `updated` or `at`, which the helper stamps) to `.claude/progress/<topic>.dash.jsonl`, one op per line, and the coordinator runs each line through `dash_rows.py` at the next `SYNC` (a `row` with `--if-version` from the row's last read).
- Results that change the page (a deploy, a merge, a failed check) come to the coordinator directly. A steward that reports to a background coordinator sends the coordinator a copy.

## Set up (once per wave)

1. Call `Artifact` with action `quickstart` and intent `other`. When the result says to start from the Dashboard type, publish with the `type_url` it gives and a title.
2. Write one `ArtifactData` batch with these documents. `<wave>` is the wave's number on its `wiki/projects/` page, as in the row id `3-L7`.
   - `dash/meta` with `{title}`, the page's title (`Wave 3 Dashboard`).
   - Three datasets, each with `source: {kind: "store", path: "data/<wave>/<name>"}`: `lanes`, `events` and `samples`.
   - `files/index.html`, whose `{text}` is [`index.html`](index.html). Before writing it, set its header for this wave: the subtitle, the start time, the wave page link, the `Coordinator:` line and the timeline chip.
   The template's layout is the owner's default (2026-11-27): a two-row header, the tiles, the timeline, one row with the two charts and the updates feed at the same height, then the lanes table at full width; keep it unless the owner asks for another.
   The page shows the time of the last data refresh and a Refresh button.
   It opens in dark mode (owner, 2026-11-27); a reader's own Auto or Light choice is kept in their browser.
3. Add the link to the wave's page in `wiki/projects/`, on the line under `Coordinator:`, and give it to the owner once.
4. Start the sampler (see Samples).

## Rows

One lanes doc per item the owner would ask about, with these fields:

- `lane`: the name shown on the row; `short`: the short name on the card; `scope`: what the lane covers.
- `status`: one of queued, running, remote, review, ci, merged, done, blocked or failed.
- `stage`: one line on what is happening now, giving the PR head commit, the remote run result and what the lane ships.
- `pr` is the PR number, or every PR number of a lane split in two. `eta` and `updated` are HH:MM. `order` is the sort key.

Rows to keep:

- **Every lane**, ids `<wave>-L<n>` (`3-L7`). A lane split in two keeps one row and lists both PRs.
- **Every PR another session sends to the queue**, ids `<wave>-P<pr>` (`3-P1271`), named for the session. Add it when the session first tells you its plan, not when it is ready.
- **The report card** (`<wave>-RC`) and anything else with an ETA the owner waits on.

Rows, events and samples are written only through `tools/agent/dash_rows.py`. The helper stamps every time from this Mac's clock; never type one. `row` is an `update` and needs `--if-version` from the row's last read; `new-row` is a `set` and needs lane, status, stage, eta and order. Do not use a time an agent reports.

```
python3 tools/agent/dash_rows.py <scratchpad>/dash/out --wave 3 --if-version 3-L7=4 \
  row 3-L7 status=ci pr='[1271,1280]' eta=23:40 'stage=head abc123, remote green' \
  event 'Merged #1271 (merge 0ddc7b8)'
```

It writes one JSON file per document and prints the array the coordinator pastes as the `ArtifactData` `batch` `writes`. `python3 tools/agent/dash_rows.py -h` lists the ops.

## Events

Add one events doc {at, text} for each of these:

- a merge, with its merge commit;
- a deploy, with the host, the exit code, and the Build counts or the stamp;
- an owner ruling;
- a blocker;
- the end of the wave.

Write them with `event "<text>"`. The id is `e<wave>-HHMM`; the helper adds a letter to an id already made in this run or written by an earlier run into the same OUT_DIR (`e3-2330b`), so keep one OUT_DIR per wave.

## When to update

Update on every message that changes a lane or PR: it starts, passes or fails its gates, starts or ends a remote run, opens a PR, is ready, merges, deploys, changes its ETA or is blocked. Before telling the owner anything, read the rows you are about to describe and fix any that do not match GitHub (`gh pr view N --json state,mergeCommit,headRefOid`). When the owner asks for status or an ETA, reply with the link and one line on the lanes that are running or blocked.

## Samples

`samples` docs hold {at, mac_load1, mac_cpus, win_load1, win_cpus, win_remote_runs, sessions, subagents, claude_total}, one every 2 minutes.

- Run `Monitor` on `.claude/skills/dashboard/sampler.sh <scratchpad>/dash/samples.jsonl` with a 30-minute timeout. Whoever holds the Monitor starts it again when it ends.
- The sampler prints `SYNC HH:MM` every 10 minutes. When that line appears, write the lines added since the last sync with `samples <file> --since <last SYNC HH:MM>`; each doc gets id `sHHMM` from its own `at`.
- The sampler counts sessions (claude processes on this Mac) and subagents (task outputs written in the last 3 minutes) itself. Do not use `ListAgents` for counts, because a steward does not have it.
- If counts are missing for a stretch, estimate them from file times. A session runs from the first to the last write of its transcript (`~/.claude/projects/*/*.jsonl`). An agent runs from the first to the last write of its task output. Add `"estimate": true` to those samples docs; the field is stored, and the page does not show it.
- The session cap starts at 8 and is flexible while load is low (owner, 2026-11-27): the samples show the load, and job times against earlier runs show slowdown. Go past 8 only while both stay low, and drop back when they rise.

## Before a /clear and at the end

- Before a /clear, give the steward that takes over the dashboard link, the sampler output file path, the Monitor task id and a pointer to this skill. The project page keeps the link.
- At the end, write the final events. Set each row to merged or done, or move it to a later wave and give the reason. Stop the sampler (`TaskStop` on its Monitor). Set the wave page to `Status: done`. Then add the dashboard to the master dashboard ([`report-cards`](../report-cards/SKILL.md) skill).

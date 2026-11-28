---
name: dashboard
description: Use when coordinating more than one lane, agent or session, when the owner asks for status or an ETA, when a lane, PR, deploy or report card changes state, or before a /clear.
---

# Live dashboard

The owner follows a wave on one page, not in the chat. The coordinator keeps it true: every lane, every session's PRs, deploys, the report card, host load and session and agent counts (owner, 2026-11-26).

## Who writes it

- **The coordinator owns every row and checks it.** A lane or another session may lack dashboard access, stop or forget, and its row goes stale. When a message changes a lane or PR, update that row in the same turn.
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

## Who keeps it, and the owner's reasons

- A hand-off of more than one lane gets a dashboard at the start, unasked: "I want this to be a coordinator task so all subagents follow it, and future coordinators give me a dashboard so I don't have to keep nagging" (owner, 2026-11-26).
- The coordinator updates every row itself, the same turn a lane or PR changes, peer sessions' PRs and the report card included: "you're the coordinator it's your job to keep track and keep me posted through the dashboard" (owner, 2026-11-26).
- A queued or blocked row names what it waits on right now. Recheck every waiting row when a slot frees, a PR merges or a session starts or stops, and launch what the freed slot allows: "items that have been unblocked are still listing as blocked" (owner, 2026-11-27).

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

It prints the `ArtifactData` `batch` `writes`; `-h` lists the ops.

## Events

Add one events doc {at, text} for each of these:

- a merge, with its merge commit;
- a deploy, with the host, the exit code, and the Build counts or the stamp;
- an owner ruling;
- a blocker;
- the end of the wave.

Write them with `event "<text>"`. The id is `e<wave>-HHMM`; the helper adds a letter to an id already made in this run or written by an earlier run into the same OUT_DIR (`e3-2330b`), so keep one OUT_DIR per wave.

## When to update

Update on every message that changes a lane or PR: it starts, passes or fails its gates, starts or ends a remote run, opens a PR, is ready, merges, deploys, changes its ETA or is blocked.

At every `SYNC`, with the samples, the coordinator syncs PR rows, so a merge by `make land` or another session shows without a message: `list` the lanes with `out_dir` right before the sync, so the pins are fresh, write the listed versions as {doc_id: version} to a file, then run `sync-prs <out_dir>/data/<wave>/lanes --versions <file>`. Run it again before telling the owner anything; check other rows against GitHub (`gh pr view N --json state,mergeCommit,headRefOid`) then too. Asked for status or an ETA, reply with the link and one line on the lanes running or blocked.

## Samples

`samples` docs hold {at, mac_load1, mac_cpus, win_load1, win_cpus, win_remote_runs, sessions, subagents, claude_total}, one every 2 minutes.

- Run `Monitor` on `.claude/skills/dashboard/sampler.sh <scratchpad>/dash/samples.jsonl` with a 30-minute timeout. Whoever holds the Monitor starts it again when it ends.
- The sampler prints `SYNC HH:MM` every 10 minutes. When that line appears, write the lines added since the last sync with `samples <file> --since <last SYNC HH:MM>`; each doc gets id `sHHMM` from its own `at`.
- The sampler counts sessions (claude processes on this Mac) and subagents (task outputs written in the last 3 minutes) itself. Do not count with `ListAgents`: a steward lacks it.
- If counts are missing for a stretch, estimate them from file times. A session runs from the first to the last write of its transcript (`~/.claude/projects/*/*.jsonl`). An agent runs from the first to the last write of its task output. Add `"estimate": true` to those samples docs (stored, not shown).
- The session cap starts at 8 and is flexible while load is low (owner, 2026-11-27): the samples show the load, and job times against earlier runs show slowdown. Go past 8 only while both stay low, and drop back when they rise.

## Before a /clear and at the end

- Before a /clear, give the steward that takes over the dashboard link, the sampler output file path, the Monitor task id and a pointer to this skill. The project page keeps the link.
- The steward takes the deploys, the sampler, the report card and the final report, from a hand-off file in the scratchpad. Models and efforts, as the owner asked ("appropriate models and efforts"): orchestration opus/medium; data-model refactors opus/high; bounded refactors opus/medium; small test or doc fixes sonnet/low; `finding-verifier` low.
- In a wave chain the owner started, rerun the report card at wave end, then start a fresh background coordinator (opus, medium); it parks owner-only items on a "Waits on owner" row instead of stopping.
- A full-page screenshot of the dashboard: dark mode, scale 1, every column visible, stitched by scroll offset, sent as PNG; offer a .zip when it is over 8000 px tall.
- A coordinator delegates ("I think you're doing too much yourself. Please background your tasks", owner, 2026-11-26): background agents do the per-PR work; the coordinator keeps owner decisions, review triage, merges and deploys.
- At the end, write the final events. Set each row to merged or done, or move it to a later wave with the reason. Stop the sampler (`TaskStop` on its Monitor). Set the wave page to `Status: done`. Then add the dashboard to the master dashboard ([`report-cards`](../report-cards/SKILL.md) skill).

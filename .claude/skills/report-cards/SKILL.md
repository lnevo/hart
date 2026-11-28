---
name: report-cards
description: Use when a report card is scored or rescored (project, code, data, website UX, agent experience or a new category), when the owner asks for a report card update, a slippage check or how a score has moved, or when a wave dashboard ends and the master dashboard must take it in.
---

# Report cards and the master dashboard

The owner monitors the project through report cards and asks for updates when things change or at intervals, to catch slippage (owner, 2026-11-28). The scores live in [`docs/report-cards/scores.json`](../../../docs/report-cards/scores.json); the cards' text, measurements and "how to measure again" live in [`wiki/report-cards.md`](../../../wiki/report-cards.md). The master dashboard is one private page that shows every category's latest score and change, each score's history, and every wave dashboard: its URL is `page` in `scores.json`.

## Rescore a category

1. Measure the way the category's "How to measure again" says in `wiki/report-cards.md`. A review by agents goes to the named reviewer that fits (`repo-auditor`, `site-reviewer`), briefed with the files and the last card's measurements, not with a score to confirm. Read from `origin/main` and say which commit; an agent that cannot fetch reads a checkout that may be behind, so check what it missed.
2. Append one score `{date, value, label}` to the category in `scores.json` (dates in order; the label says what changed: `after wave 6`, `after #1377`). Replace its `table` with this rescore's areas and measurements; keep the earlier table only in the wiki. A new category gets an `id`, `title`, `scale` (10, or 4 for grade points), `what`, `wiki` and optional `target`, `link`, `notes`.
3. Update the category's section in `wiki/report-cards.md` (score, date, the table, what was held back) in the same PR.
4. Run `python3 tools/agent/report_cards_page.py slippage`. A line starting `SLIP` is a drop: say it to the owner with the reason (a real regression, or a wider or stricter look than last time) and note it in `notes`.
5. Refresh the master dashboard (below).

A score is a judgment resting on measurements; never raise or keep one without a measurement taken that day.

## Refresh the master dashboard

After every rescore, and when a wave dashboard ends:

1. A new wave dashboard: add it to `dashboards` in `scores.json` with `id`, `title`, `start` (`YYYY-MM-DDTHH:MM` of its first event, Mac time), `store` (its datasets' `data/<wave>` path), `link`, `wiki`, `summary`, and `waves: true` only when its row ids carry wave numbers (`3-L1`).
2. Copy each dashboard's store: for every `dashboards` entry, three `ArtifactData` `list` calls on its `link` for `<store>/lanes`, `<store>/events` and `<store>/samples` with `query.limit` 1000 and `out_dir` `<scratchpad>/rc/dumps`. A finished dashboard does not change, so its earlier copy may be reused within the session.
3. `gh pr list --state merged --limit 1000 --json number,mergedAt > <scratchpad>/rc/merged.json`
4. `python3 tools/agent/report_cards_page.py build --dumps <scratchpad>/rc/dumps --merged <scratchpad>/rc/merged.json --out <scratchpad>/rc/out`
5. Publish `<scratchpad>/rc/out/index.html` with the `Artifact` tool, `url` set to `page`, and `files` mapping `cards.json` and `dash.json` from the same folder. Read the artifact first in a new session. Give the owner the link and the slippage lines.

The page template is [`index.html`](index.html) beside this skill. The build copies it and writes `cards.json` (the master as is) and `dash.json`. Dashboard times have no date: a time earlier than a dashboard's `start` falls on the next day, so a dashboard must run under 24 hours. "PRs merged" counts every PR GitHub merged while the dashboard ran, from any session.

## Update or slippage check

When the owner asks how the cards stand, run `slippage`, read the latest table of each category, and answer with one line per category: score, date, change and the reason for any drop, then the link. Name categories not rescored for more than a week; offer a rescore, do not start a costly one unasked.

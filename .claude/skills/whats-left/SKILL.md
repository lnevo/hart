---
name: whats-left
description: Use when asked what is left, pending, next, or for a to-do or loose-ends list, and at the end of a hand-off.
---

# What's left

Build the list from the repo, not from memory.

1. Read `wiki/STATUS.md` (Owed, In progress, Future goals).
2. Read the active hand-offs in `wiki/projects/`: files with `Status: active`. If none carries that line, use "Active projects" in `wiki/home.md`.
3. Run `gh pr list` for open PRs and `git worktree list` for work in progress.
4. Read `wiki/not-pending.md` and drop every item it excludes. Do not mention what you dropped.
5. Answer in five groups, one line per item, each with its source (file or PR number):
   - In progress
   - Next
   - Waiting on the owner
   - Future goals (only items the page allows there)
   - Scheduled later: items that cannot start before a set date, such as a re-measure on a given day. Give the date and sort by it. Once the date has come (`date +%F`), the item moves to Next.

List each item once. When an item has agent and owner parts, give it one line in the first group that fits and name both parts there.

If an item has no source you can point to, leave it out. When the owner gives a new "never list this" rule, add a row to `wiki/not-pending.md` in the same PR.

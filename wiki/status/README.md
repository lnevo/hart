# Live status, one file per entry

The status page is built from this folder ([ADR-038](../decisions/ADR-038-one-file-per-status-entry.md)).
`make status` (`python3 tools/ops/status_counts.py`) writes `wiki/STATUS.md`, which is gitignored; the session-start
hook and `make wt` build it, so it is there to read in every checkout. `check.sh` and CI build it in memory
(`status_counts.py --check`).

## Sections

| Folder | Heading | What goes there |
|---|---|---|
| [`now/`](now/) | Now | What is active, waits on the owner or is blocked, in a few lines |
| [`current/`](current/) | Current state | How the railroad, its data and its tooling are today; the Counts line is added at build time |
| [`owed/`](owed/) | Owed | Work owed, in order: each file opens with an `order: N` line, lowest first |
| [`in-progress/`](in-progress/) | In progress | Work under way that is not owed |
| [`future/`](future/) | Future goals | Goals with no date |

## An entry

- One file, `<section>/<slug>.md`, named from its bold lead or first words, holding the bullet's text without
  its `- `. The page lists an unordered section's entries by file name.
- At most 60 words (owner, 2026-11-25): the fact, the owner and date, and a link to the detail. The check fails a
  longer one; move the detail to the linked page or ADR.
- Links are relative to the entry file (`../../decisions/ADR-038-one-file-per-status-entry.md`), so they work here
  on GitHub; the build rewrites them for `wiki/STATUS.md`.
- When an entry is removed or replaced, its old text goes to [`STATUS_LOG.md`](../STATUS_LOG.md) as before.
- A branch from before the split that edits `wiki/STATUS.md` gets a modify/delete conflict when it merges `main`:
  move the edit into the entry file and run `git rm wiki/STATUS.md`.

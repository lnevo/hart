# ADR-038 — One file per STATUS entry

- **Status:** Proposed
- **Date:** 2026-11-25
- **Deciders:** lnevo
- **Amends:** ADR-036, point 4 (`wiki/STATUS.md` leaves the committed list)

## Context

`wiki/STATUS.md` is the file most merges touch. In the 7 days to 2026-11-25, 154 of the 467 merges into `main` changed it. 117 of those edited an existing entry, 34 only added one and 3 only removed one. The file merges with git's union driver (`.gitattributes`), which keeps both sides of a change. When two branches edit the same entry, both versions stay. #1120 removed one such double, and #1124 adds a check (`status_counts.py --check`) that catches near-duplicates after the merge. Both deal with the result, not the cause: every PR edits one shared file.

The file has also grown past its own rule ("one or two sentences"). It is 3,719 words in 79 bold entries, and four entries run over 600 characters.

`wiki/STATUS_LOG.md` does not have the problem. It is append-only, so the union merge is correct for it.

## Decision

1. **Each entry is one file.** The source is `wiki/status/<section>/<slug>.md`, with the sections `now`, `current`, `owed`, `in-progress` and `future`. A file holds the bullet text only. Owed is ordered, so a file there opens with an `order:` line. Two PRs collide only when they change the same entry, and then git shows a real conflict instead of keeping both.
2. **`wiki/STATUS.md` is built, not committed.** `make status` (`tools/ops/status_counts.py`, renamed when it is extended) writes it from the folder and adds the Counts line from `tables.xml` and traininfo at build time. The session-start hook builds it, so agents and skills that read it by path still find it in every checkout and worktree. It is gitignored, and `check.sh` and CI build it in memory and check it.
3. **Readers on GitHub read the folder.** `wiki/status/README.md` says what each section holds and how to build the page. The 54 tracked files that name `wiki/STATUS.md` are rewritten to `wiki/status/` (or to a section folder where they point at one part) with `tools/ops/move_path.py`.
4. **An entry is at most 60 words** (owner, 2026-11-25). The check fails a longer one; the detail goes to the linked page or ADR. `STATUS_LOG.md` is exempt.
5. **`STATUS_LOG.md` stays one committed file with the union merge.** When an entry file is removed or replaced, its old text goes to the log as now.
6. **Migration is one PR.** A script splits today's file into entries, and the built page must match today's file byte for byte, apart from the Counts line. The same PR moves the `.gitattributes` line, the `/done`, `whats-left` and AGENTS.md wording, the hooks, the stamps declarations (`check_stamps.py`), the `checks.toml` entry and the pipeline map node.

## Consequences

- Parallel PRs stop doubling entries, and #1124's near-duplicate check can go once the folder is the source.
- A branch from before the move that edits `wiki/STATUS.md` gets a modify/delete conflict when it merges `main`. It moves its edit into the entry file and runs `git rm wiki/STATUS.md`. The migration PR should land when `make orient` shows few branches with STATUS edits; today three have them.
- On GitHub there is no single STATUS page any more, only the folder. A reader who wants one page runs `make status`, or a later step adds the page to the website build.
- The Counts line stops causing churn: it is computed when the page is built, not committed.
- 6 of the 85 entries are over 60 words today (4 in Current state, 1 in Owed, 1 in Future goals). The migration PR shortens them and moves their detail to the linked pages first, in its own commit.

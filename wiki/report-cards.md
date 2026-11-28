# Report cards

Five report cards in one place: the project as a whole, the code, the data, the website's UX and the agent experience. Each is a reviewer's judgment resting on the measurements beside it. Recommendations on these cards are kept for the next review; they are not owed work and are not listed in `wiki/status/`.

The owner monitors the project through these cards and asks for updates when things change or at intervals, to catch slippage (owner, 2026-11-28). Every score is also kept in [`docs/report-cards/scores.json`](../docs/report-cards/scores.json), and the master dashboard (its link is `page` there) shows each category's latest score, its change and its history beside every wave dashboard. The [`report-cards`](../.claude/skills/report-cards/SKILL.md) skill says how to rescore, check for slippage and refresh the page.

## Project overall

The scores are a reviewer's judgment, and each one rests on the measurements in the table. Overall: 7.5 (2026-10-31, first pass), 8 (2026-10-31, after the gates), 8.5 (2026-11-22), 9 (2026-11-27, after the six code-quality waves).

| Area | 10-31 | 11-22 | 11-27 | Measured on 2026-11-27 |
|---|---|---|---|---|
| Knowledge and decisions | 9 | 9 | 9.5 | 40 ADRs (31 on 11-22) and 20 pipeline pages. Status is one file per entry (ADR-038). Wiki cells are capped at 80 words. The 11-27 audit found 2 broken links. |
| AI instructions | 9 | 9 | 9.5 | `AGENTS.md` is 65 lines and 980 words (109 lines on 11-22), held by the 70-line, 1,000-word check. There are 11 skills and 10 named agents. |
| Workflow | 8 | 9 | 9 | 1,815 commits, 856 merges and 1 revert since 11-22. There is one cross-session merge queue (`coordinate` skill). The median green CI run is about 6 minutes (about 2.5 on 11-22). |
| Verification | 7 | 8.5 | 9 | About 7,000 test functions in 416 test files (about 3,950 on 11-22). The habits and mypy counts are ratcheted. The last 100 CI runs were 84 passed, 1 failed and 14 cancelled (81, 7 and 11 on 11-22). |
| Organization | 8 | 8 | 8.5 | Scripts over 1,000 lines fell from 11 to 3, and one of them is parked. `signal_coordinator.py` is 648 lines and `build_device_map.py` 520. The code report card is B+ (3.30), up from B- (2.86). `railroad_facts.py` (1,286) and `devices.py` (1,154) are still large, across 841 Python files. |
| Subagents | 6.5 | 7.5 | 8.5 | `general-purpose` was 140 of 527 chosen launches (27%) for 2026-11-22 to 11-27, down from 68%. It was 54% of every launch. The leaders were `finding-verifier` (185), `tool-fixer` (58) and `schematic-builder` (39). |

Held back on 2026-11-27:
- **Verification:** the local `./tools/check.sh` failure in a fresh worktree on the Mac (unit-cats `No module named 'PIL'` under Homebrew Python, and `test_check_stamps`, whose nested audit run runs unit-cats) was one cause: the stamp-audit hook hid Homebrew's sitecustomize. LE-L12 (#1351, [wave-loose-ends](projects/wave-loose-ends.md)) fixed it; both jobs pass in a fresh subagent worktree under Homebrew Python 3.13. The group D split of `signal_coordinator.py` was accepted without a live test.
- **Organization:** the repo keeps growing faster than it gets simpler.
- **Subagents:** the 2026-11-27 rescore is the re-measure: `general-purpose` was 27% of chosen launches (target under 50%), so the 2026-12-05 count is dropped (owner, 2026-11-27).

How to measure again:
- Count commits since the last rescore with `git rev-list --count --since=…` and `--merges`.
- Count test functions with `git grep -c "def test_"`, outside `archive/`, `external/` and `reference/`.
- Get CI outcomes from `gh run list --limit 100`.
- Run `agent_launch_count.py --since … --until …` and use its first count.
- Take the report card from [code-quality-wave](projects/code-quality-wave.md).
- The Python file and test counts were not taken exactly as on 11-22, so treat those as approximate.

## Code quality

Line-weighted average over the graded source files, parked code left out. Owner, 2026-11-27: "leave parked code out of the report card. It shouldn't count against the grade: not in the line-weighted average, not in the C/D counts, not in 'files read'. Show parked files apart (listed, not graded) so they don't vanish from view." Parked means everything under `jmri/layouts/hart/parked/` plus scripts that serve only the parked features (`hartlib.parked.PARKED`: nx, dispatcher, uss), such as `gen_ctc_track_plan.py`, `uss_switch_only_columns.py`, `nx_contract.py`, `reconcile_dispatcher_stations.py` and `ctc_logic_smoke.py`, each confirmed from its callers. A mixed file (`check_bean_comments.py`: live `main()` plus parked USS rules) is graded. Every card brief excludes parked files from the stats and adds a "Parked, not graded" list. Detail per wave, the owner's rulings and the files still at C+ are on [code-quality-wave](projects/code-quality-wave.md); the card with every file is https://claude.ai/artifact/2feCxg41LpAFfoP3e6Z8nE ("After wave 6 (final)").

| | Start (11-26) | Wave 1 | Wave 2 | Wave 3 | Wave 4 | Wave 5 | Wave 6 (11-27) |
|---|---|---|---|---|---|---|---|
| Average | 2.868 (B-) | 3.039 | 3.130 | 3.197 | 3.224 | 3.260 | 3.301 (B+) |
| C and D files | 63 | 32 | 15 | 1 | 1 | 2 | 2 |
| A-range files | 8 | 18 | 133 | 157 | 167 | 189 | 200 |
| Files read | 70 | 110 | 469 | 488 | 493 | 515 | 526 |

The final card covers 534 source files and 123,997 lines; the margin over B+ is 117 grade-point-lines. A cleanup must not lower the card: check fix PRs against the grade habits in `AGENTS.md` before merge (copied helpers, dates in comments, `from None`, `sys.exit` in library code), or have the files graded before merge. On 2026-11-27 the loose-ends round took the average from 3.301 to 3.298, and the fixes after it (#1361 pipefail, #1362 deploy gate) ended at 3.297, because each added copied shell blocks, dated text and long history comments and the regrade ran only after the merge. The owner stopped it: "we're backtracking now." Do not open a fix-the-fix round just to recover grade points without asking the owner first.

## Data

The data review of 2026-11-25 set seven priorities for a long-term data plan; [ADR-039](decisions/ADR-039-data-masters-in-git.md) took them on, and the [data-masters](projects/data-masters.md) lanes did phase 1. Rescored on 2026-11-27 at `c948929a`: about 8 of 10, against roughly 4 before ADR-039 (the first review gave no number).

| # | Recommendation (2026-11-25) | State on 2026-11-27 |
|---|---|---|
| 1 | A catalogue by kind of record: key, master, copies, outside tools | Done. `docs/data/entities.csv` has 43 kinds, each with which side wins during a session. |
| 2 | Column sidecars for every master, validated in `check.sh` | Mostly done. 29 sidecars; 20 check references into other files (35 in all). The `data-schemas` step in `checks.toml` runs `check_data.py`: 29 of 29 pass in 0.15 s. Hand-kept JSON masters have schema checks (L11). |
| 3 | Stable keys, assigned once, not tied to row order or public names | Done. `industry_id` and spots, train symbols, station and control point ids, block `id`; locos keyed on `roster_id`; `occupancy_bindings.csv` retired (L12); turnout control points come from `hartlib.places` (L15). |
| 4 | Drift reports: repo masters against STS, Operations Pro and JMRI | Phase 2, not started (owner, 2026-11-25). `make orient` shows what waits on a host to be ingested. |
| 5 | No spreadsheet as an input | Done. v86 is output only; the signal split, v85 and the industry routing matrix are archived. `tools/wiring/node_grid_svg.py` still draws the site's node grid from the owner's grid workbook (outside git, mapped as an unstructured input): a drawing, not records. |
| 6 | A read-only SQLite built from the masters | Phase 2, not started. |
| 7 | A database as master only when several people edit at once | Not done, as intended. `serve_portal.py`'s edit API for `archive.json` and `gallery.json` is the case to watch. |

Beyond the seven: the DecoderPro roster became a repo master (N8, #1220), and the places and devices follow-ups merged (N1, #1216).

Held back on 2026-11-27:
- Masters with no sidecar, so a bad row fails no check: the car master `ops/hart-ops/data/image_metadata.csv`, `wiring.csv`, `schematic/lcos_nodes.csv` and `schematic/sheets.csv`.
- Phase 2 has not started. The checks prove the masters agree with each other, not with what STS, Operations Pro and JMRI hold, which is where a session's data goes wrong.

If the data card is revisited, in this order:
1. Sidecars for the car master, `wiring.csv`, `lcos_nodes.csv` and `sheets.csv`.
2. Phase 2 drift reports per kind of record, starting with cars (`bin/cars compare` exists) and locos, then the direction each field flows.
3. The read-only SQLite from the masters, for questions across files and the site build (built, not committed: ADR-036).

How to measure again:
- Rows in `docs/data/entities.csv`; sidecars with `git ls-files '*.columns.csv'`, and the rows with a `refs` value.
- `python3 tools/ops/check_data.py`.
- Spreadsheet readers with `git grep -l -E 'load_workbook|read_excel' -- ':!archive' ':!*test*'`; a reader that only compares its own output (`write_inventory.py --check`) does not count.
- Each `entities.csv` master checked for a sidecar or a schema check.

## Website UX

First formal pass on 2026-11-28 at `8515ccc7`: about 7 of 10 (6.8). Earlier site reviews (11-14, 11-22) left follow-up PRs but no score. Three `site-reviewer` agents with the UX lens split the site: shared navigation and the hub pages; the railroad content pages (layout, roster, history, library and the rest); the operator and behind-the-scenes pages (crew, docs, ai, behind, guides, build, exam, play, helix). Each slice scored the eight areas; the score is their mean.

| Area | Nav and hubs | Content | Crew and behind | Score | Measured on 2026-11-28 |
|---|---|---|---|---|---|
| Navigation and wayfinding | 7 | 6 | 6 | 6.5 | Every section is 1 click from home, the deepest page is 3. 4 of the 5 library articles over 1,600 words have no contents list or heading ids. A crew sheet is 4 taps from any page but home. 16 pages have no route from home, 9 of them real content. |
| Layout and readability | 7 | 7 | 7 | 7 | 113 of 120 pages have one h1. None scrolls sideways at 375 px (53 crew-slice pages measured in headless Chrome). |
| Mobile | 6 | 7 | 7 | 6.5 | Viewport meta on every portal page except the redirect stubs and the Publication Standards export. Small tap targets: 117 under 32 px on `ap/index`, the layout map's 146 hotspots at the default fit. |
| Accessibility | 7 | 6 | 7 | 6.5 | 0 of 210 static images lack alt. Skip link, focus styles and menu ARIA are in place. Header, nav and crew sheets exist only after JS runs: 1 `<noscript>` in the source pages. The exam and lineage tabs have no arrow-key handling. |
| Clarity for a first-time reader | 7 | 6 | 6 | 6.5 | The home page and its four doors explain themselves. The layout, roster and NVL crew sheet open on CP, Digicon, MQTT, POHC, SM-03 and similar with no gloss. All three guides open on a parked notice. |
| Consistency across pages | 6 | 6 | 6 | 6 | Nav comes from one source (`data/site.json`). 52 pages have no description and share one generic sentence. Crew is "Crew sheets", "Session paperwork" and "Publications" in different places. |
| Weight and speed | 8 | 8 | 9 | 8.5 | Home is about 0.2 MB and paints in 0.09 s. `behind/layout-docs` loads 9 MB of images (lazy). `no-cache` on every asset. |
| Links and errors | 8 | 7 | 6 | 7 | 0 dead links on live pages from about 1,200 checked. `ai/construction.html` links the unpublished `helix/build-status.html` (404). The guides show repo paths and shell commands a reader cannot open. `/library/` is a 404. |

Held back on 2026-11-28:
- Nothing was checked on a real phone or with a screen reader, and colour contrast was not measured. Mobile and accessibility rest on CSS, markup and one headless run.
- Links inside `data/*.json` and links built by JS at runtime were not scanned.

If the UX card is revisited, in this order:
1. A static fallback where JS builds the page: the header's home and section links, the crew sheets and the primer (`briefing/`, the "Start here" page), each with a `<noscript>` line pointing to the PDF.
2. A one-sentence description on the 52 pages without one.
3. Contents lists and h2 ids on the long library articles, crew sheets, `build/` and the guides, using the `.jump` pattern from `crew/industries`.
4. A short gloss or glossary link on the first screen of `layout/`, `roster/`, `history/` and the crew sheets.
5. One name for the crew hub in the nav, title and home page, and a shorter path to a sheet from the Operations menu.
6. Dead and private links: `build-status.html` from `ai/construction.html`, repo paths in `guides/`, `/library/` to `/articles/`, the raw `library/opspro-showcase-guide.md`, and a check in `check_portal_build.py` that fails on a link to a `SKIP_FILES` path.

How to measure again:
- Brief three `site-reviewer` agents with the UX lens on the same three slices, asking each for the eight areas scored with one measurement apiece.
- Pages without a description: `git grep -L 'name="description"' -- 'www/*.html'`, leaving out `scripts/` and `docs/html/`.
- `<noscript>` count: `git grep -l '<noscript' -- 'www/*.html'`.
- Overflow at 375 px with headless Chrome against local `www/`; live weight and status with GET and HEAD only.

## Agent experience

How sessions and subagents work in the repo. 8.5 on 2026-11-27 (a review before the [cleanup](projects/ax-cleanup.md)); 7.5 on 2026-11-28 at `b09d1de4`, after #1377, from a `repo-auditor` scoring six areas.

| Area | 11-28 | Measured on 2026-11-28 |
|---|---|---|
| Instructions | 8.5 | Root `AGENTS.md` 64 lines and 916 words; five folder `AGENTS.md` files add 585 words; no `CLAUDE.md`. |
| Skills and agents | 8 | 11 skills of 201 to 1,214 words, none over the 1,500 cap; `handoff` and `coordinate` pass 1,500 with their reference file loaded. 10 agent files, 320 to 747 words. |
| Memory | 6.5 | 38 files and 10,857 words (49 files on 11-27). The remote-run, timing and coordinator files repeat `AGENTS.md` and the skills; two files are over 1,000 words. |
| Session start | 8.5 | The start hook prints nothing in 0.07 s. `make orient` is about 40 lines, 25 of them overlap lines while many lanes run. |
| Shipping and merging | 8 | `make ready` and `make land`, with tests; #1377 lets a draft PR without private reads pass on GitHub's check and adds a merge lock. |
| Housekeeping | 5.5 | 43 worktrees, 29 of them `agent-a*`; nothing prunes those. 39 progress files, 16 older than a day; the prune rule keeps a file while its topic has a worktree. |

The 11-27 costs: memory 49 to 38 files, overlap left (partly); one line per worktree at session start to none (fixed); two skills over 2,000 words to none over 1,500 (fixed); 37 stale progress files to 39 live ones (not fixed). The 11-28 look was wider than the 11-27 one (worktrees, memory overlap), so part of the drop is the wider look, not a regression.

Held back on 2026-11-28:
- The lock and the GitHub gate of #1377 were read, not run. Most memory files were not opened for staleness.

If the card is revisited, in this order:
1. Prune `agent-a*` worktrees whose branch merged or never got a commit, and detached worktrees under temp folders.
2. Drop memory files that repeat `AGENTS.md` or a skill; split the two files over 1,000 words.
3. Shorter overlap in `make orient` (a count per folder instead of one line per file).
4. Archive progress files of a merged topic even while a worktree of that name remains.

How to measure again:
- Brief one `repo-auditor` with the six areas above and the last measurements, reading `origin/main`.
- `git worktree list | wc -l` and `| grep -c agent-a`; `ls .claude/progress | wc -l` and `find .claude/progress -maxdepth 1 -type f -mtime +1 | wc -l`.
- `wc -w` on each `SKILL.md`, `AGENTS.md` and memory file.


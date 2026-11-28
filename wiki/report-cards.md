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

Scores: 6.8 (2026-11-28, first formal pass at `8515ccc7`), 7.3 (2026-11-28, after the [UX round](projects/ux-round.md), live at `5c392d9f`), 7.6 (2026-11-28, after part 2, live at `2f3c6cce`, nine areas). Three `site-reviewer` agents with the UX lens split the site into navigation and hubs, the railroad content pages, and the crew and behind-the-scenes pages; each slice scores eight areas. Content and value is a ninth area, scored once for the whole site per audience (owner, 2026-11-28). The card is the mean of the nine, each area rounded to a half.

| Area | First | After the round | After part 2 | Measured after part 2 (2026-11-28) |
|---|---|---|---|---|
| Navigation and wayfinding | 6.5 | 6.5 | 7.5 | Slices 8, 6.5, 7.5. A crew sheet is 3 taps from any page at both widths, 1 from the crew index. Plants, railroads, layout and photos have no jump list; the desktop header has no Crew sheets link. |
| Layout and readability | 7 | 7.5 | 7.5 | Not re-measured after part 2 except the crew pages (0 of 24 scroll sideways at 375 px). |
| Mobile | 6.5 | 7.5 | 7.5 | Not re-measured. Crew pages: 45 block tap targets under 32 px on 7 sheets; footer links 19 px on every page. |
| Accessibility | 6.5 | 6.5 | 8 | Slices 8.5, 7.5, 7.5. Skip link and `main#main` on 89 of 94 pages; crew sheets readable with JS off; 7 tablists pass arrows, Home, End and the exam deck keys. Wiring and tables-file tabs have no tabpanels; three pages' table scrollers are unlabelled. |
| Clarity for a first-time reader | 6.5 | 6.5 | 6.5 | Not re-measured. Crew sheets still gloss neither GCOR nor "CI-CK1 · Rev D", and show a bare "?" for an unassigned engine. |
| Consistency across pages | 6 | 6.5 | 6.5 | Not re-measured. Crew pages 24 of 24 have title, description, h1 and skip link. |
| Weight and speed | 8.5 | 8 | 8 | Not re-measured. Crew pages load 70 to 277 KB. |
| Links and errors | 7 | 9 | 9 | Not re-measured. 0 dead links in a 94-page crawl. |
| Content and value | | | 8 | Rechecked after #1398: 8 of 8 corrections live, 0 thin pages, 3 small conflicts left (Route 23 wording, the island-end phrase, the Kosmos start year). Visitor 7, crew member 8.5, model railroader 8, historian 8.5. |

The 7.3 pass summed live image weight per page and the first did not, so Weight and speed fell without a page getting heavier. Over the eight areas alone, part 2 scores 7.56.

Held back on 2026-11-28 (after part 2):
- Nothing was checked on a real phone or with a screen reader, and colour contrast was not measured.
- `about/` is blank without JavaScript ("About HART Loading…"), and plants, railroads, layout and articles show one line.
- The home page lede needs the year American Steel & Wire opened (owner to give it). Route 23 now reads "Coraopolis–Sewickley … across Neville Island" on four pages; "across Neville Island" was added in the brief, not by the owner, and is unconfirmed.

If the UX card is revisited, in this order:
1. `about/` and the lineage pages rendered at build time, as the crew sheets and primer are.
2. Tabpanels on the wiring and tables-file tabs; labelled, focusable scrollers on `crew/industries`, `behind/tables-file` and `behind/jmri-additions`.
3. Tap targets to 40 px on map cards, colour chips, the door links and the footer; the layout map at a readable zoom on phones.
4. First-screen gloss on photos, articles, railroads, the crew sheets (GCOR, the sheet code, "Engine assigned by the Yardmaster" for "?") and exam/play.
5. Jump lists on helix, `behind/jmri-additions`, `behind/tables-file`, plants and railroads; the build cut plans and Publication Standards on the site template.
6. Image weight: `behind/layout-docs` and `ai/clinic` photos resized, WebP logos, sizes on lineage logos and hub thumbnails.

How to measure again:
- Brief three `site-reviewer` agents with the UX lens on the same three slices against the live site, asking each for the eight areas scored with one measurement apiece.
- Content and value: one `site-reviewer` with the first-time reader and historian lens, site-wide, scored per audience (first-time visitor, crew member, model railroader, local historian), with claims checked against sources and conflicts between pages counted (owner, 2026-11-28).
- Pages without a description: `git grep -L 'name="description"' -- 'www/*.html'`, leaving out `scripts/` and `docs/html/`.
- With JS off: fetch the live HTML and read what shows.
- Overflow at 375 px with headless Chrome (a 375 px iframe or device emulation; say which); live weight and status with GET and HEAD only, summing image bytes per page. Keyboard: CDP key events on every `role="tablist"` and table scroller.

## Agent experience

How sessions and subagents work in the repo. 8.5 on 2026-11-27 (a review before the [cleanup](projects/ax-cleanup.md)); 8.5 on 2026-11-28 at `27e6f052` after #1388, refreshed in place to 8.3 at 04:20 on `06ddaddc` after #1392, #1396, #1397 and #1399, from a `repo-auditor` (the owner: one point per day; the 7.5 point of the same day was removed in #1390).

| Area | 11-28 02:25 | 11-28 04:20 | Measured on 2026-11-28 at 04:20 |
|---|---|---|---|
| Instructions | 8.5 | 8.5 | Root `AGENTS.md` 64 lines and 916 words; five folder `AGENTS.md` files hold 1,315 words, unchanged; no `CLAUDE.md`. |
| Skills and agents | 8 | 7.5 | 12 skills of 201 to 1,494 words; `dashboard` 1,494, `handoff` 1,354 and `coordinate` 1,210 leave no headroom (the cap failed #1399's check at 1,542). `make land` is still described in four places. A `tool-fixer` got past `subagent_guard` by splitting file names into a shell variable. |
| Memory | 9 | 9 | 15 files and 3,723 words; `hosts-and-network` at 1,191 words is the one file over 1,000. |
| Session start | 8.5 | 8.5 | `orient.py --short` 11 lines in 0.86 s (3.8 s before); 3 `Coordinator:` warnings, all from copies in old worktrees, and one stale worktree path. |
| Shipping and merging | 8.5 | 8.5 | 155 land, queue, triage, guard and housekeeping tests pass. `make land` re-targets a moved head, keeps one log per ticket and writes `events.log`; `make triage` runs the verifiers headless. Subagents cannot commit or push, so the coordinator applied two fix patches by hand; `/code-review` stays a session step. |
| Housekeeping | 7.5 | 8 | 17 worktrees (19), 3 `agent-a*` (7); 24 progress files, none older than a day (38 and 17); the hourly launchd job runs, and its first run deleted 176 merged local branches. |

The drop from 8.5 is a stricter look, not a regression: skill headroom and the guard bypass were measured this time.

Held back on 2026-11-28 04:20:
- The SessionStart hook and `make land-wait` were not timed; memory was counted, not read for overlap; the `git -c core.fsmonitor=...` route past the guard was not reproduced.

If the card is revisited, in this order:
1. Close the `subagent_guard` gaps (split shell variables, `git -c` config) and decide how a subagent hands back a commit.
2. Trim `dashboard`, `handoff` and `coordinate` under about 1,300 words, with one `make land` description in `merging.md` that the others link to.
3. Fix the `gh pr merge` match in `.claude/hooks/worktree_sweep.py`, which also fires on a quoted grep pattern.
4. Split `hosts-and-network` in memory.

How to measure again:
- Brief one `repo-auditor` with the six areas above and the last measurements, reading `origin/main`.
- `git worktree list | wc -l` and `| grep -c agent-a`; `ls .claude/progress | wc -l` and `find .claude/progress -maxdepth 1 -type f -mtime +1 | wc -l`.
- `wc -w` on each `SKILL.md`, `AGENTS.md` and memory file; `python3 tools/ops/orient.py --short` timed; the land, queue, triage, guard and housekeeping tests in `tools/audit/tests`.

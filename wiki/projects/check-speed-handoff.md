# Quicker local check.sh for small changes: hand-off (2026-11-24)

Status: done (2026-11-24)

Three changes that make `./tools/check.sh` quicker on the Mac for a small change, a wiki or ADR edit above all. A full run is already split well (368 s, bound by 2685 s of job time on 8 cores since #1075); this plan is about the runs that skip most jobs. About 3 PRs.

## What a small change costs today (measured 2026-11-24 at ce1f6bc1, the Mac, no other session running checks)

| `check.sh` run | Wall | Jobs run | Jobs skipped |
|---|---|---|---|
| Nothing changed | 62 s | 8 | 203 |
| One line added to an ADR | 110 s | 39 | 183 |

- **With nothing changed**, the jobs that ran add up to 42 s: `unit-hosts test_redeploy_commit` (24 s), `unit-hart-ops` (7 s), `unit-hosts test_pi_ssh_scripts` (5 s) and five of a few seconds each. The rest of the 62 s is the stamp check of every job, one `check_stamps.py current` process each, at most 8 at once (`MAX_JOBS`), and the start-up; not timed apart yet.
- **An ADR edit** reran, besides those: `static` (34 s), `unit-portal` (39 s), `unit-guards test_check_stamps` (38 s), `unit-hosts test_deploy_stage` (36 s), `unit-guards test_pipeline_map` (26 s), `unit-guards layout-editor` (16 s), `public-text` (16 s) and about 25 shorter jobs.
- **Why each reran is not known yet.** `static` and `public-text` are declared on every file (`EVERYTHING` in `tools/audit/check_stamps.py`), and `unit-portal` on the site folders, `wiki/` among them (`SITE`), so those follow from their declarations. The layout-editor job, `test_deploy_stage` and `test_check_stamps` do not obviously read the wiki. `check_stamps.py why <job>` run from a plain shell answers "the code, command, interpreter, plugin or environment changed" for every job, so it must be run in check.sh's environment to mean anything.
- **CI already has a docs-only path:** `tools/ci/changed_kind.py` says "docs" when every changed path is a `.md` file outside `.claude/`, `AGENTS.md`, `CLAUDE.md` and `docs/pipeline-map/`; the workflow then runs only the quick docs checks (`.github/workflows/check.yml`, "Quick docs checks", the pipeline map among them since #1075).

## Items

| # | Item | Agent and model | Edits | Expected gain |
|---|---|---|---|---|
| 1 | Docs-only path in local `check.sh` | `general-purpose`, default model | `tools/check.sh`, a new test in `tools/audit/tests/` | an ADR or wiki edit from 110 s to about 10 s (not timed) |
| 2 | Find why each job reran on the ADR edit, and narrow what it is stamped on | `general-purpose`, default model | `tools/audit/check_stamps.py` (`BY_KIND`, `LISTED_ONLY`), its tests | fewer jobs on every small change, docs or not |
| 3 | Cut the no-change overhead | `general-purpose`, default model; step 3a is read-only | step 3b: `tools/check.sh`, `tools/audit/check_stamps.py` | part of the 62 s; the longest always-run job takes 24 s, so most of it is not test time |

**Order.** 1, 2 and 3a run at the same time: 1 edits `check.sh` only, 2 edits `check_stamps.py` only, and 3a only measures. 3b edits both files, so it starts after 1 and 2 merge, from the numbers 3a reports. Load: each agent runs its full `check.sh` through `make remote`, and its timings on the Mac one at a time (a second session's checks slowed every job about three times on 2026-11-24).

### 1. Docs-only path in local check.sh

Goal: when every path the branch changes is docs by `tools/ci/changed_kind.py`, `check.sh` runs the same quick docs checks as CI and stops, saying so on its first line.

- The changed paths: the branch against its merge base with `origin/main`, plus uncommitted and untracked files (the portal job already diffs against `origin/main`; reuse that, do not add a second way). No paths at all is "full", as in `changed_kind.py`.
- One list of quick docs checks for CI and `check.sh`: move it out of `check.yml` into a script both call (for example `tools/ci/docs_checks.sh`), so the two cannot drift. The workflow's step keeps its name.
- `FULL=1` and `CI` take the normal path, as now. No new variable to force the docs path.
- Tests: a docs-only branch takes the quick path; a branch with one `.py`, one `.claude/` file, `AGENTS.md` or a `docs/pipeline-map/` file does not; an untracked `.md` counts; no merge base (a shallow clone) takes the full path with the reason printed.
- Done when an ADR edit's `check.sh` is timed on the Mac and the time is in this page.
- Timed 2026-11-24 19:39 on the Mac, one line added to an ADR, load average 6.3: 13.3 s on the docs-only path, against 110 s before (10.9 s at 19:26, before the unit tests that read Markdown joined the docs checks; the 13.3 s run also had a third one, since dropped, of 0.2 s). The run used a copy of `check.sh` that diffs against HEAD, since this branch's own commits are not on `origin/main` yet; every other line is the branch's.

### 2. Narrow what reruns on a wiki edit

Goal: for each job that reran on the one-line ADR edit, the reason, and a narrower stamp where the job does not read the wiki.

- Reproduce in a scratch worktree: add a line to a wiki page, run `check.sh`, and list the jobs that ran. For the reason, run `check_stamps.py why <job>` with check.sh's stamp environment (`CHECK_STAMPS_DIR` and the rest that `check.sh` sets), or add a `--why` line to the job's log; `CHECK_AUDIT=DIR FULL=1 tools/check.sh` then `check_stamps.py audit-report DIR` shows what each job read.
- Narrow only from evidence: a job that read a wiki file keeps it. A job that fell back to its declaration because it ran bash or git keeps a declaration; narrow the declaration only to folders the audit shows it reads.
- `static` stays one job on every file (owner, 2026-11-24). `public-text` stays on every file unless the audit shows a clear split.
- Tests: `tools/audit/tests/test_check_stamps.py` already checks that each job's declaration covers what the audit saw it read; extend it to any new or narrowed entry.
- Report a table: job, reran on the wiki edit (yes or no, before and after), reason, change made.

**Results (2026-11-24, 834b73d6 plus the change).** A one-line edit to `wiki/decisions/ADR-001-layout-identity.md`, uncommitted, in a worktree, after a no-change run; the reason from `check_stamps.py why` in check.sh's environment, the reads from `CHECK_AUDIT=DIR FULL=1 tools/check.sh` on the Windows box. 15 stampable jobs ran before the change and 11 after; 6 of the 11 run with nothing changed (item 3). The Mac was loaded (load average 12 to 17, other agents' runs), so the wall times (120 s before, 100 s after) are not a fair comparison; time it again on a quiet Mac.

| Job | Reran before | After | Reason | Change |
|---|---|---|---|---|
| `static` | yes | yes | ran bash, so its declaration (every file) is in the key; it also reads 34 ADRs | none (owner: stays whole) |
| `public-text` | yes | yes | read the ADR | none: it reads the wiki itself |
| `unit-guards test_pipeline_map` | yes | yes | read the ADR (the agent-doc lane) | none |
| `unit-guards test_agent_docs_map` | yes | yes | read the ADR | none |
| `unit-guards test_agent_docs_cells` | yes | yes | read the ADR | none |
| `unit-portal` | yes | no | ran node, so its declaration (`SITE`, with `wiki/`) was in the key; its Python read `www/`, `docs/` and listed `ops/`, and its node scripts read only `www/` | declared on `CODE`, `www/`, `docs/`, `ops/` |
| `unit-hosts test_deploy_stage` | yes | no | ran bash and `git clone`, declared on every file; the deploy copies from `jmri/`, `cats/`, `tools/` and one CSV in `docs/jmri/`, and its Python read only `CODE` | declared on `CODE` and `docs/jmri/` |
| `unit-guards test_check_stamps` | yes | no | ran bash (a check.sh of the sample jobs), declared on every file | declared on the sample jobs' declarations and `.gitmodules` (`RUNS_JOBS`, `AUDIT_SAMPLE` in `check_stamps.py`) |
| `unit-guards test_hart_tables_writers` | yes | no | ran `git status` (it only compares the tree before and after), declared on `wiki/` | declared on `wiki/STATUS.md`, the one wiki file it reads |
| `unit-hosts test_redeploy_commit`, `test_pi_ssh_scripts`, `test_win_run`, `test_patch_windows_mqtt`, `unit-jmri test_ctc_signal_heads`, `unit-guards test_public_text` | yes | yes | run with nothing changed too: no stamp recorded, or a key that differs every run | none here (item 3) |

Why the first measurement counted 39 is not checked. A likely cause, unverified: the stamp store is shared, and another worktree's run had replaced some stamps just before; `unit-guards layout-editor` and 14 `unit-jmri` files ran in this item's own no-change run while another agent's check.sh ran, and not on the ADR edit. `check_stamps.py audit-report DIR -v` now works (it printed the usage line before).

### 3. Cut the no-change overhead

**3a, measure (read-only, alongside 1 and 2).** Time a no-change `check.sh` on the Mac by phase: start-up before the first job, the stamp checks (one `check_stamps.py current` per job), the jobs that always run, and the wait for the last job. Say why each of the 8 jobs ran with nothing changed (traced reads of a file that changes every run, an untraceable program, or no stamp at all).

**3a results (2026-11-24, the Mac, 834b73d6, load average 8 to 18).** A no-change `check.sh` took about 65 s:

| Part | Time | Why |
|---|---|---|
| 202 `check_stamps.py current` processes, 8 at once | about 55 s (2.2 s each loaded, 0.8 to 1.4 s alone) | one process per job |
| in each: parse `filehash.json` (40 MB, 200,257 entries, 44,540 paths still there) 2 or 3 times | 0.31 s | a new cache per call |
| in each: walk all of `tools/` to hash 3 literal files | 0.27 s (0.85 s for a job declared on every file) | a literal pattern walked from its folder |
| in each: 14 git processes, `plugin_state` twice | 0.38 s | nothing shared between jobs |
| in each: the `--save` snapshot | about 0.4 s | |
| all 202 in one process (prototype, shared caches) | 7.4 s | the same 8 jobs not current |
| jobs that always ran | 6 real ones and 2 placeholders | check.sh recorded no stamp when the output showed `skipped=` |

**3b, cut (after 1 and 2 merge).** Act on 3a. Likely candidates, to be confirmed by it: check every job's stamp in one `check_stamps.py` process instead of one per job; let `test_redeploy_commit` (24 s) and the other always-run jobs be stamped if what makes them always run can be declared. Byte-identical results: the same jobs run and skip as before, for the same changes. Done when a no-change run is timed before and after.

**3b results (2026-11-24, PR from `agent/claude/check-overhead-cut`).** `check.sh` now queues every job, checks all their stamps in one `check_stamps.py current-batch` process (one hash cache; git, the plugin state, the walks and the snapshots worked out once), and starts only the jobs that run. A batch that fails runs every job, records nothing and says why; a job whose own check raises runs alone and loses its stamp. A unit job whose tests skipped now records its stamp: the trace hook logs each skipped test's id and reason (they go in the key) and every `shutil.which` lookup (looked up again at compare time), and the key gained the user site-packages, `CHECK_AUDIT`, `UPDATE_GOLDEN`, the user id, the roster-sync submodule for `test_pi_ssh_scripts`, and HEAD, `origin/main` and their merge base for `test_redeploy_commit`. `tools/audit/tests/test_check_stamps.py` compares the batch's verdict, reason and snapshot with each job checked alone for no change, an edit to a read file, an edit only a declaration covers, a missing stamp, a plugin change and an unstampable checkout. Timed on the Mac in one worktree with a private stamp folder, each run after the 1-minute load fell under 12 (it rose to between 17 and 32 during the runs, other work on the Mac):

| Run | Wall | Ran | Skipped |
|---|---|---|---|
| No change, before (main, 33d4b68a), three runs | 54 s, 65 s, 54 s | 8 | 196 |
| No change, after (86254ac9), two runs | 7.4 s, 7.5 s | 1 (the `unit-hart-ops` placeholder) | 203 |
| One line added to an ADR, after | 27 s | 7 (`static` 21 s, `public-text`, four guard tests, the placeholder) | 197 |

The six jobs that always ran now record, and stay current on a no-change run: `test_ctc_signal_heads`, `test_patch_windows_mqtt`, `test_win_run`, `test_public_text`, `test_pi_ssh_scripts` and `test_redeploy_commit`. `test_redeploy_commit` still reruns whenever HEAD, `origin/main` or the shared `git worktree list` changes (its tests replay that command), so it reruns after any commit and often while other worktrees come and go. Not done: pruning `filehash.json` (parsed once per run now, 0.3 s). Every stamp, the panel steps' too, is new once after this change (the hook changed).

## Result (2026-11-24, fresh main after #1082, the Mac, load 9 to 15)

| `check.sh` run | Before | After | Jobs run after |
|---|---|---|---|
| Nothing changed | 62 s | 7 s | 1 (the hart-ops placeholder) |
| One line added to an ADR | 110 s | 14 s, the docs-only path | the quick docs checks |

Merged: #1078 (item 1), #1080 (item 2), #1082 (item 3b); item 3a measured only. The first run after #1082 on each host runs every job once (the trace hook changed every key: 258 s here), and the next no-change run still ran 31 jobs (62 s) before settling at 7 s; why that second run did not skip is not checked.

**Left, not in this plan** (the first two closed in #1084, below; the third left as it is):
- `check_stamps.py audit-report` lists 7 jobs that read folders outside their declarations: test_agent_docs_cells, test_agent_docs_map, test_ai_speak, test_helix_stl_index, test_pipeline_map, test_public_text, test_status_merge (traced reads, so their stamps hold them; nothing gates on the report).
- `test_deploy_stage` stages from a clone of the committed HEAD while its stamp hashes the working tree, so committing an edit already in the tree does not rerun it.
- `test_redeploy_commit` reruns whenever a worktree is added or removed (its key holds `git worktree list`).

## Loose ends closed (2026-11-24, #1084)

- **Why the second no-change run ran 31 jobs:** in a fresh worktree the panel check (`build_panels.sh`, in `static`) makes `.cache/panel-stamps` about 10 s into the run. The quick `unit-jmri` jobs that list the root passed before that and recorded a root listing without `.cache`, so the next run reran them ("listed . changed"); the jobs running at that moment recorded nothing ("not stamped: . changed while the job ran"). Reproduced with a private `CHECK_STAMPS_DIR`: 31 jobs with "listed . changed" and 7 with no stamp. `check.sh` now makes `$ROOT/.cache` before any job starts. The fix is in `check.sh` and not in `traced.listing()`, because `traced.py` is in every `make panels` step's key. The 7 "HEAD, origin/main ... changed while the job ran" of the first measurement did not happen again and are not explained; origin/main moving during a run (another session's merge) would cause them.
- **Measured on the fix (the Mac, private stamp folder, `.cache` removed first, under the timing lock):** warm-up 344 s, no "not stamped" (load 12 at the start, 85 at the end); the next no-change run 22 s, 202 of 204 jobs skipped, 1 run: `test_redeploy_commit`, because a commit in another worktree during the warm-up changed `git worktree list` (the rerun left as it is).
- **The 7 UNCOVERED jobs** now declare what the audit (`CHECK_AUDIT=DIR FULL=1`, Windows) saw them read: `test_agent_docs_cells` `wiki/**/*`; `test_agent_docs_map` `.gitmodules`; `test_ai_speak` `check_ai_speak.DEFAULT_GLOBS` (a test keeps them equal); `test_helix_stl_index` `docs/benchwork/helix/stl/**/*`; `test_pipeline_map` `.gitmodules` and `ops/hart-ops/card_pipeline/**/*`; `test_public_text` `ops/hart-ops/card_pipeline/**/*`; `test_status_merge` `wiki/STATUS.md` and `.gitattributes`. A new audit on the branch reports none. The docs-only guard lists three of them in LEFT_OUT, with reasons; none was added to `docs_checks.sh`.
- **`test_deploy_stage`** keys on HEAD (`REFS_OF`), so committing an edit already in the tree reruns it. Any other commit reruns it too (36 s), and a pull request CI run never skips it.

## Owner decisions (2026-11-24)

| # | Question | Answer |
|---|---|---|
| 1 | Should the docs-only path be automatic, or only on request? | Automatic, the same rule CI uses; `FULL=1` still runs everything |
| 2 | Should a docs-only local run record a pass that `/done` and the merge gate count? | No: it is a quick check, and CI runs on every PR |
| 3 | Should `static` (36 read-only checks, one stamped job, about 34 s) be split so an edit reruns only the checks that read it? | No, leave it whole. A docs-only branch skips it (item 1); the quick docs checks cover its checks that read the wiki |

## Not in this plan

- More parallel jobs: a full run is bound by total job time on 8 cores, so it is `make remote`'s job.
- Faster tests inside a job, beyond the always-run ones in 3b.

# Night plunge: loose ends in one hand-off (2026-11-26)

Status: active
Coordinator: hart-6d, since 2026-11-26 01:54 (from hart-95; the owner chose a split: hart-95 keeps lanes N1 to N4 until their PRs are open)

The owner's call on 2026-11-26 at 01:45: every loose end from the what's-left list goes on this page and runs tonight, except the items that stay in `wiki/STATUS.md`. Those are the main and upper station maps, finalize wiring, the owner's parts of the session #4 punch list, the benchwork-finished question (pipeline-coverage lane C), the future goals, and the dated items (the agent re-count on 2026-12-05, the old Pi card until 2026-12-23).

## Lanes

| Lane | Job | Owns | Source | Agent, review |
|---|---|---|---|---|
| N1 Places readers | `hartlib.places` `table()` and `names()` read the lists beside a copied master, as `switch_places` does since L15; station and control point names unique per level; one error type for facts problems (`FactsError` against `DevicesError`); `railroad_facts` `station_group_rows` names its `cp_id` consistently; a stricter turnout id check in `devices.check_rows`. Outputs stay byte-identical | `tools/hartlib/src/hartlib/{places,railroad_facts,devices}.py` and their tests | [data-masters](data-masters.md), Open for the owner | `schematic-builder`, opus; `/code-review high`; `make panels CHECK=1` unchanged; layout deploy |
| N2 Pipeline tool fixes | `pipeline_map_coverage.py`'s entry-file scan: a comment line ending in `\`, an apostrophe in an unquoted word, every `PYTHONPATH` entry; `unit-jmri` and the edit hook's 20 s budget (section E row 7); a manifest loader check that no output has writers in two manifests (found in #1187); the deploy-stage test that leaves files in the live checkout | `tools/ops/pipeline_map_coverage.py`, `tools/pipeline/`, `.claude/hooks/check_after_edit.py`, `tools/hosts/tests/` | [pipeline-coverage](pipeline-coverage-handoff.md) Follow-ups, the agent experience session's report | `general-purpose`, opus; `/code-review medium` |
| N3 Python size sweep | split the five files between 90 percent of their limit and the limit, with no change in behaviour: `pom_guard.py`, `test_gen_ctc_track_plan.py`, `hart_pub_helpers.py`, `test_pipeline_manifest.py`, `test_panelpro_wrappers.py`. `reconcile_dispatcher_stations.py` is parked and stays | those five files and their new parts, `tools/audit/py_sizes.csv` | `check_py_sizes.py` warnings | `general-purpose`, opus; `/code-review medium`; layout deploy if `pom_guard.py` ships |
| N4 Map view split | `tools/ops/pipeline_map_view.js` (1417 lines) into parts under the 800-line limit, the map drawing unchanged | `tools/ops/pipeline_map_view*.js`, the map page that loads it | the agent experience session's report | `general-purpose`, opus; `/code-review medium`; site deploy |
| N5 Archive and stale notes | archive the 2026-11-08 speed-matching scripts (`runner/step_runner.py`, `runner/move_to.py`, `analyze_profile.py`, `propose_table.py`) and the two `STRR_*.py` with their exclusions, through `move_path.py`; correct the stale lines: STATUS "Generated, then the owner's" (its left items are done on [naming-layers](naming-layers-handoff.md)), cleanup-streamline section A, the #1149 deploy owed on pipeline-coverage (shipped by every deploy since) | `docs/jmri/speedmatching/`, `archive/`, `wiki/status/`, those project pages | [pipeline-coverage](pipeline-coverage-handoff.md) lane C, [cleanup-streamline](cleanup-streamline-handoff.md) A | `general-purpose`, sonnet; docs and moves, no review |
| N6 Punch list designs | drafts of item 4 (control point signs sized for a stick in the benchwork), item 5 (the big crew board in sign-up order) and item 6 (mock signals for the interlocking gaps) for the owner to choose from | new files under `docs/ops/session4/` | [punch list](../../docs/ops/SESSION4_PUNCH_LIST.md) items 4 to 6 | `general-purpose`, sonnet; owner approves each look before anything is published |

N1 to N5 run at once; N6 starts when one of them ends. The cap is 8 sessions with subagents. Heavy checks run through `make remote`, one or two at a time.

## Owner's parts

- Group D (the split signal and panel-status scripts): the coordinator runs `make panelpro-test` on the Mac; the live try of the lamp clicks, the SML button and a quit release needs the owner ([health round 2](health-round2-handoff.md) section 1, step 4).
- L7 roster typo ids: the owner's yes on the Mac STS copy ([data-masters](data-masters.md)).
- The data-masters questions still on working values ([data-masters](data-masters.md), Open for the owner).
- Worktree removals: `naming-step5-tests` needs `git worktree remove --force` (cleanup-streamline A); `data-masters-coord` holds an uncommitted claim line on `data-masters.md`.
- 3D station maps: the Barn frame measurements ([`docs/benchwork/station_maps_3d/`](../../docs/benchwork/station_maps_3d/README.md)).
- N6: pick a design for each of items 4 to 6.

## Rules

- Merges go through hart-6d's queue: "ready #N", merge only on "go #N" (`coordinate` skill). The coordinator runs every deploy.
- Lane agents write status lines to `.claude/progress/night-<lane>.md`; this page changes only in the coordinator's commits.

## Done when

Every lane is merged or handed back with a reason, the deploys are done, and this page is `Status: done`.

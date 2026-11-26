# Night plunge: loose ends in one hand-off (2026-11-26)

Status: done (2026-11-26)

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
| N7 Data-masters answers | the owner's answers 1 to 3 on 2026-11-26: full colour key names, the TT-23 site wording, the YM-01 NONE row on the site legend; the docx overrides go | `ops/hart-ops/data/crew.json`, `ops/hart-ops/publications/`, `www/data/crew.json` | [data-masters](data-masters.md), Open for the owner | run by hart-95 |

Merged on 2026-11-26: N5 #1209, N4 #1211, N3 #1213, N2 #1214, N1 #1216, and hart-c4's #1215. The site was deployed at 02:31, and the Pi and Windows got 9424352cc at 02:38 (both stamps clean). N6 is draft #1212, waiting on the owner's picks. Later the same night: N7 #1219 (site deployed), N6 #1212 (picks applied), N8 #1220 (the DecoderPro roster as a repo master; deployed --pi --win at 099faf422 with the owner's yes, roster already current on every host), #1221 and #1222 (canonical links and the bare-domain redirect; site deployed), and N8b #1223 (the old roster sync archived). Nothing is in progress. The owner's open items moved to `wiki/status/now/waits-on-the-owner.md` and the session #4 punch list entry.

N1 to N5 run at once; N6 starts when one of them ends. The cap is 8 sessions with subagents. Heavy checks run through `make remote`, one or two at a time.

## Owner's parts

Settled on 2026-11-26: group D is taken as good without the live try (owner, in hart-95, about 02:35); L7 was done by #1173 on 2026-11-25 with no STS write; the owner removed the leftover worktrees; the data-masters questions are answered (lane N7 for three, phase 2 for the roster, [data-masters](data-masters.md)); the Barn 3D plate keeps its placeholders until the owner sends the frame measurements, and is rebuilt to them before any print ([`docs/benchwork/station_maps_3d/`](../../docs/benchwork/station_maps_3d/README.md)). N6 (02:55 to 03:00): control point signs option A (plate), crew board option B (columns), no mock signals (punch-list items 6 and 8 not wanted).

Nothing is left for the owner on this page.

## Rules

- Merges go through hart-6d's queue: "ready #N", merge only on "go #N" (`coordinate` skill). The coordinator runs every deploy.
- Lane agents write status lines to `.claude/progress/night-<lane>.md`; this page changes only in the coordinator's commits.

## Done when

Every lane is merged or handed back with a reason, the deploys are done, and this page is `Status: done`.

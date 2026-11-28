# docs/jmri

Reference notes for JMRI work on the layout: block lengths, the MQTT startup race, the CS-105 roster sync and the speed-matching record.

| Document | What it is for | State |
|----------|----------------|-------|
| `TRACK_LENGTHS.md` | Generated table of track and spur lengths per block; change `block_lengths.csv`, not this page | Current, regenerated |
| `MQTT_STARTUP_RACE.md` | The MQTT connection drop at PanelPro start: a stock JMRI 5.16 race, reproduced on a bare profile; repro in `tools/jmri/mqtt_race_repro/` | Current |
| `CS105_ROSTER_SYNC.md` | Copying the JMRI roster into the TCS CS-105 command station so UWT-100 throttles show every loco | Current |
| `speedmatching/` | Speed matching of CSX 2121 and CSX 2738: `RUNBOOK.md` (how), `RERUN_PLAN.md` (plan), `POM_GUARD.md` (CV write guard), `DASHBOARD.md` (live view), `ANYRAIL_LENGTHS.md` (block lengths) | Tools current; the 2026-11-13 re-run is done |
| `speedmatching/profile-2026-11-08/` | First measured profile and the CV changes programmed that day | Historical, superseded by 2026-11-13 |
| `speedmatching/profile-2026-11-13/` | Result of the re-run: profiles, match, stop tests, loop 2 placement | Latest results |
| `speedmatching/prompts/` | Two generic AI-agent prompts for block lengths and speed matching | Reusable |
| `speedmatching/README.md` | The STRR club scripts and procedure the work started from; not run on the layout as they are | Reference |

The living status of speed matching is in `wiki/projects/speedmatching.md`.

## make panelpro-test and traininfo

`make panelpro-test` loads the repo's `tables.xml` in real PanelPro, but the smoke script reads `preference:dispatcher/traininfo/`, which is `dispatcher/traininfo` under `JMRI_UserFiles` on the Mac. After a change that renames blocks, transits or traininfo files, rsync the repo's traininfo into that folder first (the deploy's Mac step does the same). Otherwise the run fails with hundreds of "references missing transit" and "lacks ordered route" lines that are not real; read those two as a stale-profile signal first (seen on the 2026-11-07 track-name swap, ADR-017: the first run failed, the second passed with the same bundle). The expected counts are in `jmri/layouts/hart/scripts/panel_counts.json`.

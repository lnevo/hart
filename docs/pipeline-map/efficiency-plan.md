# Pipeline efficiency plan (2026-11-21)

Plan to cut panel rebuilds and full workflow runs, based on logged step timings, reviewed by the owner on 2026-11-21.

This plan works through what the pipeline map shows. The goal is fewer panel rebuilds and fewer full workflow runs. The owner reviewed every topic on 2026-11-21. The plan runs alongside the ADR-030 work and waits for it where the two touch the same files.

## What the timings show

Logged `make panels` steps (149 runs): schematic 21 s average, Layout Editor cut-over 14 s, device map 3 s, CATS 2 s, the rest under 1 s, so a full rebuild takes about 40 s. A full `check.sh` takes 2 to 5 min, SML discovery about 3 min in PanelPro, and `panelpro-test` 2 to 3 min. The hours come from repeated loops, not from the steps: a stale input or a by-hand step found after a rebuild, a check and an approval, then a Store split and another rebuild. The plan cuts the loops.

Heavy checks run on the Windows box (`make remote`). `panelpro-test`, SML discovery and deploys stay on the Mac. Layout changes must come out byte-identical (`tables.xml`, desks, Layout Editor panel, approved fingerprints), so they need no new approvals.

## Topics

| Topic | What | Weight | State |
|---|---|---|---|
| T1 | Outputs the map showed with no reader: 12 were missing links, 8 are end products, 2 were wrongly labelled as outputs | S | Done (#853) |
| T2 | Two writers drawn for one output: map errors and different jobs, no real duplicate code | S | Done (#853) |
| T3 | Move the generated `signal_head_plan.csv` from `docs/` to `jmri/layouts/hart/output/` (host path unchanged) | S–M | Done (#867) |
| T4 | Input stamps on the by-hand steps: `make panels` stops in under a second when SML discovery is stale, and runs the mast builder itself | M | Done (#867) |
| T5 | Skip `make panels` steps whose inputs did not change (same stamps as T4) | S | Done (#867) |
| T6a | Device master as two files: `devices_generated.csv` (scripts) and `devices_field.csv` (the owner's cells and Store-added devices), merged by `hartlib.devices` ([ADR-029 amendment](../../wiki/decisions/ADR-029-tables-xml-is-an-output.md)). Step 0 routes every reader through `hartlib.devices` | L | Step 0 done (#869); the two-file split waits |
| T6b | Generated sections of `plan_overrides.json` move to `plan_generated.json` | M | After T6a |
| T7 | Wiring one way: unfrozen wiring is a proposal in the generated rows; `make wiring-freeze` is the only writer into `wiring.csv` | M | After T6a |
| T8a | Site build in stages; the photo stages are reused when their inputs are unchanged (build 7.8 s to 2.9 s) | M | Done (#854 tests, #861) |
| T8b | Deploy as gate, stage, then ship per host, so every check runs before anything ships (#855 tests found four gates that run after shipping starts) | M–L | Done (#873; first real deploy should watch the Windows probe) |
| T9a | The deploy keeps a changed Pi Store or Operations session in the pull folder and stops | M | Done (#887) |
| T9b | `tools/schematic/template_edit.py`: memories, clock and settings without a Store | M | Done (#862) |
| T10a | `bin/cars compare` checks the STS seed copies; `bin/cars seed-copy` refreshes them | S | Done (#852) |
| T10b | `bin/cars compare` field differences against Operations Pro and the STS seed | S–M | Done (#860) |
| T10c | `bin/cars sync` sends corrected fields of existing cars, dry run and backup first | M | Later; the first live run needs the owner's yes |

Also done on 2026-11-21: the schematic film is built by `evolution.py --site` (#857), and every panel film runs at one pace, 0.4 s a frame with a 2 s final hold (`hartlib.film_pace`, #858).

## Order

T3, T4, T5, T8b and T9a are done (2026-11-21). Still to do, in this order because they touch the same files: the T6a split (step 0 is done, #869), T6b, then T7. Then one `panelpro-test`, a deploy if a shipped file changed, and one pipeline map update for everything above.

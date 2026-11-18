# Hand-off, 2026-11-18: STS on the Pi, then the STS helpers cleanup

For a fresh agent session. Two jobs, in this order. Read `AGENTS.md`, then this page, then
[`sts-helpers-cleanup.md`](sts-helpers-cleanup.md) (findings and the step plan). Load the `sts-live`
skill before touching the Pi STS, and `sts:sts-api` before any API call.

## State when this was written

- Live STS on the Pi: `http://RPi-JMRI.local:8980`, stack `live`, session 5. It still runs the
  sts-docker and sts-plugins commits from before 2026-11-18.
- Merged but not on the Pi: sts-docker `0b644ac` (lnevo/sts-docker#19, branch `active`) and
  sts-plugins `a2884b4` (lnevo/sts-plugins#6, `main`); hart moved its pointers in hart #652.
  - Core STS no longer names HART. Session dump names come from the plugin manifest key
    `session_backup_prefix`; hart_layout sets `hart_session`, so HART keeps
    `hart_session_pre{N}` / `hart_session_post{N}`. Without the plugin the prefix is `session`.
  - `railroad_name` / `railroad_initials` fall back to `Railroad` / `RR`. HART's database sets
    both ("HART Railroad, ..." and "HART"), so its printouts should not change.
  - Staging jobs come only from the plugin's `staging_jobs` hook or config. HART's hook returns
    STG-SCULLY and STG-DEMMLER, the only `STG-` jobs in its database.
  - The `weigh_ck1` legacy step id moved from track_scale into hart_layout.
- The Mac UAT stack (localhost:8980) was not running. Start it with
  `(cd external/sts-docker && docker compose up -d)`; `tools/ops/sts_compose.sh` is gone (hart #652).
- Known flaky: sts-docker's browser test on `generate.php` (`#ship_tbl .shipment-select` checked)
  failed once on #19 and passed on rerun.

## Job 1: put #19 and #6 on the Pi

The owner approves every STS change on the Mac UAT copy before it reaches the Pi (ADR-020). You
prepare and check; the owner says yes; then you deploy.

1. Start the Mac stack (command above). If its data is older than the Pi's, refresh it from the Pi
   as the `sts-live` skill says (`make sts-pull`, then restore on the Mac). Confirm
   `/sts/api/v1/health` says `uat`.
2. Check on the Mac, and write down what you saw:
   - The session overview lists the `hart_session_pre{N}` / `hart_session_post{N}` backups for
     the current session, and Lock Backup (no backup selected) locks both pre and post.
   - Session restart for session N offers `hart_session_pre{N}` first.
   - A switch list and a waybill print "HART Railroad" in the header, not "Railroad".
   - The `hart_session` workflow's Create Backup steps still show their `hart_session_*`
     prefixes, and a new Create Backup step defaults to `hart_session_post`.
   - The staging jobs list (switch-list index, wheel report) still treats STG-SCULLY and
     STG-DEMMLER as staging.
3. Report to the owner and wait for an explicit yes.
4. Run `tools/hosts/pi_sts_update.sh` (it pulls sts-plugins before sts-docker, the order this
   change needs). Then `tools/hosts/pi_sts_update.sh --status` and the live health check. Do not
   write to the live STS.
5. Record the result in `wiki/STATUS.md` (the STS helpers line) and in `sts-helpers-cleanup.md`.

If any check fails, stop and report; do not deploy. A fix goes through a new sts-docker or
sts-plugins PR, the same UAT check, and the owner's yes.

## Job 2: the STS helpers cleanup

Follow the step plan in [`sts-helpers-cleanup.md`](sts-helpers-cleanup.md): step 1 (stack guard,
main session, Opus, medium effort) and step 2 (dead code and `--ck1-test`, one agent, Sonnet, low
effort) in parallel, then step 4 (design in the main session, then an agent for the move).

Changes since the plan was written:
- sts-plugins moved to `a2884b4`. Only `plugins/hart_layout/plugin.php`, `plugins/track_scale/plugin.php`
  and `tests/check_generic_plugins.sh` changed; `hart_warm_start.php` line numbers in the plan still
  hold, but check them before editing.
- sts-docker moved to `0b644ac`; `bin/check_plugin_boundary.sh` now also catches `hart`, `hart_` and
  `STG-` and scans the generated catalog. Anything step 4 moves into sts-docker must pass it.
- Step 1 is the urgent one: on the Pi the guard passes for any script, simulations included.

Each step is a PR in the submodule repo, reviewed with `/code-review medium` before its merge, then one
hart PR for the pointers. Agents test only in a sandbox stack (8981). Any STS change that reaches the
Pi goes through Job 1's UAT check and the owner's yes again.

## Report when done

PR links, the UAT observations, the owner's go, the Pi `--status` output, what is left in sts-helpers.

# Checks and the Windows compute box

How `./tools/check.sh` decides what to run, and how heavy jobs go to the Windows box instead of the Mac.

## check.sh

Run `./tools/check.sh` before any commit that changes tables or signals. CI runs it on every PR, without the portal build.

- **Portal build.** It is skipped when the branch changes no site input. `PORTAL_CHECK=1` runs it anyway.
- **Job stamps.** Each job runs under a trace hook (`tools/audit/traced.py`) that records the files its Python processes opened, probed and listed. A job whose recorded reads are unchanged since its last pass prints `<job>: current, skipped` and is not run again, so an edit re-runs only the jobs that read the file. A job that ran bash, node or a writing git falls back to the folders `tools/audit/check_stamps.py` declares for it. `python3 tools/audit/check_stamps.py why <job>` says why a job ran. Stamps are in `<main checkout>/.cache/hart/check-stamps`, shared by every worktree and by `make remote`. `make panels` steps are stamped the same way (`python3 tools/schematic/panel_stamps.py why <step>`).
- `FULL=1` runs everything and records the stamps; with `CI` set nothing is skipped or recorded, except in the two CI modes below. `CHECK_ONLY=<regex>` runs only the jobs it matches.
- **CI skips what main covered.** Main's push run runs every job with `CHECK_RECORD_TO` and saves the stamps of the jobs that passed in the Actions cache, keyed on its commit. A pull request run restores the stamps for its merge base and runs `check.sh` with `CHECK_SKIP_FROM`: a job whose inputs are byte-identical to that pass prints `<job>: current on main <sha>, skipped`, and every other job runs. `tools/ci/stamp_gate.py` runs everything, and logs why, when the stamps are missing or for another main commit, the runner image, Python, git or bash differs (not the image build number, which varies between runners), the plugin pin changed, the change touches `check.sh`, `check.yml` or the stamp code, the pull request has the `full-ci` label, or one of its commit messages has `[full-ci]` (add the label, then re-run the job). Jobs that cannot be stamped (skipped tests, `SKIPPED` output, `static` and `portal`, which hold HEAD) always run. A weekly scheduled run checks main in full.
- **No plugin, no pass.** `check.sh` and `make panels` set `SCHEMATIC_REQUIRED=1` unless it is already set, as CI does: a schematic check that cannot load the schematic-maps plugin fails instead of printing SKIPPED. `SCHEMATIC_REQUIRED=0` lets those checks skip. A job that still printed SKIPPED (the owner's plan file is not on the machine, say) is named on one line at the end of the output.
- Logged times: a warm local run takes about 40 s, a full run 2 to 5 min. Grep earlier output (`--- job (Ns)`) before re-running just to time it.

## make remote

`make remote CMD="./tools/check.sh"` (or `tools/hosts/win_run.sh -- <cmd>`) runs a pushed branch on the Windows box's WSL. `.wslconfig` there caps it at 8 of the box's 16 threads, and each run gets its own worktree, so several at once are fine.

- Use it for a full `check.sh`, test suites and panel rebuilds. Iterate on single tests locally.
- A command with `$` in it goes through `tools/hosts/win_run.sh -- bash -c '...'`, because make expands `$`.
- Exit 3 means the operating flag is set and the box is down: run it on the Mac.
- Never use it for `panelpro-test`, screenshots or deploys.
- When the Mac is busy (load above about 8, or several sessions running checks), run `make remote` in the background beside Mac work, and have subagents run their full checks and suites through it.
- The Mac has 8 cores. Keep CPU-heavy local work to about 2 jobs at a time per session.

# Checks and the Windows compute box

How `./tools/check.sh` decides what to run, and how heavy jobs go to the Windows box instead of the Mac.

## check.sh

Run `./tools/check.sh` before any commit that changes tables or signals. CI runs it on every PR, without the portal build.

- **Portal build.** It is skipped when the branch changes no site input. `PORTAL_CHECK=1` runs it anyway.
- **Job stamps.** Each job runs under a trace hook (`tools/audit/traced.py`) that records the files its Python processes opened, probed and listed. A job whose recorded reads are unchanged since its last pass prints `<job>: current, skipped` and is not run again, so an edit re-runs only the jobs that read the file. A job that ran bash, node or a writing git falls back to the folders `tools/audit/check_stamps.py` declares for it. `python3 tools/audit/check_stamps.py why <job>` says why a job ran. Stamps are in `<main checkout>/.cache/hart/check-stamps`, shared by every worktree and by `make remote`. `make panels` steps are stamped the same way (`python3 tools/schematic/panel_stamps.py why <step>`).
- `FULL=1` runs everything and records the stamps; with `CI` set nothing is skipped or recorded. `CHECK_ONLY=<regex>` runs only the jobs it matches.
- Logged times: a warm local run takes about 40 s, a full run 2 to 5 min. Grep earlier output (`--- job (Ns)`) before re-running just to time it.

## make remote

`make remote CMD="./tools/check.sh"` (or `tools/hosts/win_run.sh -- <cmd>`) runs a pushed branch on the Windows box's WSL. `.wslconfig` there caps it at 8 of the box's 16 threads, and each run gets its own worktree, so several at once are fine.

- Use it for a full `check.sh`, test suites and panel rebuilds. Iterate on single tests locally.
- A command with `$` in it goes through `tools/hosts/win_run.sh -- bash -c '...'`, because make expands `$`.
- Exit 3 means the operating flag is set and the box is down: run it on the Mac.
- Never use it for `panelpro-test`, screenshots or deploys.
- When the Mac is busy (load above about 8, or several sessions running checks), run `make remote` in the background beside Mac work, and have subagents run their full checks and suites through it.
- The Mac has 8 cores. Keep CPU-heavy local work to about 2 jobs at a time per session.

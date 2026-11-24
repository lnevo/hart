# ADR-025 — An operating flag guards the Pi and Windows while the layout is in use

- **Status:** Accepted
- **Date:** 2026-11-18 (recorded 2026-11-19)
- **Deciders:** lnevo
- **Amended:** 2026-11-23: the layout deploy scripts check the flag themselves (below).

## Context

Agents deploy to the Pi and Windows, quit and start PanelPro on the Pi and update the live STS. Nothing told an agent that the owner was operating or that a speed-matching run was on the layout.

The first version (commit `4b4c2f65`, 2026-11-18) also blocked table and Operations pulls and the Mac's PanelPro. The owner narrowed it the same day to what reaches the Pi and Windows (commit `5615d0e0`).

## Decision

One flag file on the Mac, `~/.hart_operating`, says the layout is in use. `tools/hosts/operating.sh` sets, clears and prints it, and `.claude/hooks/main_guard.py` reads it.

**Who sets and clears it**
- The owner asks an agent to set it when they start operating (`operating.sh on [reason]`) and to clear it when they are done (`off --owner`). An agent passes `--owner` only when the owner says the session is over.
- Sending a speed-matching job sets it (`jmri/layouts/hart/scripts/speedmatch/drop_job.sh`, `on --by speedmatch`). The agent clears that flag with `off` once the run's log ends. `drop_job.sh` clears it itself if the job does not start.
- An owner `on` takes over a speed-matching flag, so the session is not cleared with the run. Any other second `on` keeps the first.

**What the hook blocks while it is set**
- a deploy to the Pi or Windows, including `make redeploy`;
- `pi_quit_panelpro.sh`, `pi_start_panelpro.sh` and `pi_sts_update.sh`;
- an ssh command to either host that touches JMRI, PanelPro, CATS, java, the STS docker, a kill or a reboot;
- under the owner's flag, a new speed-matching job.

**What stays open**
- Mac-only work: table pulls, the Mac install, the Mac's PanelPro and `make panelpro-test`.

## Consequences

- The flag is a file on the Mac, where the agents run. The hook guards agent commands; since 2026-11-23 the layout deploys also check it themselves (amendment below). A person or a process on the Pi or Windows is not stopped by it.
- Windows is guarded as well as the Pi because it runs the LCOS bridge.
- A deploy needed during a session waits until the flag is cleared.
- Tests: `tools/hosts/tests/test_operating.py` and `tools/audit/tests/test_guards.py`. `HART_OPERATING_FLAG` and `HART_GUARD_OPERATING` exist for them.
- The day-to-day commands are in the [`operating-flag` skill](../../.claude/skills/operating-flag/SKILL.md).

## Amendment 2026-11-23: the layout deploys check the flag themselves

An architecture review found the flag stopped only agent commands, so a deploy run from a terminal during a session went through. The owner chose to guard the layout deploys only.

- `tools/hosts/sync_hart_package.sh` with `--pi`, `--win` or `--all`, and `tools/hosts/redeploy_commit.sh` with those flags, call `operating.sh guard` before anything is read or sent. While the flag is set they stop (exit 3); an unreadable flag counts as set.
- `HART_DEPLOY_WHILE_OPERATING=1` is the owner's override. `redeploy_commit.sh` passes it to the older commit's deploy.
- `--dry-run`, `--check-only`, `--stage-only` and the Mac-only install stay open.
- `pi_quit_panelpro.sh`, `pi_start_panelpro.sh`, `pi_sts_update.sh` and ssh commands stay guarded by the hook only.
- Tests: `tools/hosts/tests/test_operating.py` and `OperatingFlagRefusal` in `tools/hosts/tests/test_deploy_gates.py`.

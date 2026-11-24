---
name: operating-flag
description: Use when the owner says they are operating or done operating, when a speed-matching job is dropped on the layout or its run ends, when a hook blocks a Pi or Windows action because the operating flag is set, or when asked to run tools/hosts/operating.sh.
---

# Operating flag

The flag says the layout is in use. `tools/hosts/operating.sh` keeps it in `~/.hart_operating` on the Mac, where the agents run.

## Commands

| Do | Command |
|---|---|
| Set it when the owner says they are operating | `tools/hosts/operating.sh on [reason]` |
| Clear it when the owner says they are done | `tools/hosts/operating.sh off --owner` |
| Read it | `tools/hosts/operating.sh status` (exit 0 when set, 1 when clear) |
| Deploy anyway (owner only) | `HART_DEPLOY_WHILE_OPERATING=1` before the deploy: `sync_hart_package.sh` and `redeploy_commit.sh` to the Pi or Windows refuse on their own while the flag is set (ADR-025 amendment) |
| Set it for a speed-matching job | `tools/hosts/operating.sh on --by speedmatch [reason]`; a job drop sets it |
| Clear it after a speed-matching run | `tools/hosts/operating.sh off`, once the run's log ends |

An agent clears only a flag it set (`--by speedmatch`). Clearing the owner's takes `--owner`, which an agent passes only when the owner says the session is over. An owner `on` takes over a speed-matching flag, so the session is not cleared with the run. Any other second `on` keeps the first.

## What it blocks

While it is set, the guard hook (`.claude/hooks/main_guard.py`) blocks what reaches the Pi and Windows:

- host deploys (`sync_hart_package.sh`, `make redeploy`)
- `pi_quit_panelpro.sh` and `pi_start_panelpro.sh`
- `pi_sts_update.sh`
- ssh commands there that touch JMRI, CATS, java, docker or a reboot
- new speed-matching jobs, when the owner set the flag

Mac-only work stays open: tables pull, Mac install, the Mac's PanelPro, `make panelpro-test`.

## Sources

- `tools/hosts/operating.sh`, `.claude/hooks/main_guard.py`
- `wiki/STATUS.md` (Operating flag, 2026-11-18), `docs/jmri/speedmatching/RUNBOOK.md` (`drop_job.sh`)

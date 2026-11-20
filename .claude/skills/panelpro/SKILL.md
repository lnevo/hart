---
name: panelpro
description: Use when PanelPro must be quit or started on the Mac (after a Store is pulled, or before asking the owner to approve a panel) or on the Pi (around a deploy or make ops-pull), or when asked to run pi_quit_panelpro.sh or pi_start_panelpro.sh.
---

# Quit and start PanelPro

## On the Mac

Once any Store is pulled (`make tables-pull`), quit and relaunch it yourself as needed. The operating flag guards only the Pi and Windows, so the Mac's PanelPro stays open to you.

- Quit: `osascript -e 'tell application "PanelPro" to quit'`. Never answer a Store dialog.
- Start: `open -a /Applications/JMRI/PanelPro.app`.
- Before asking the owner to approve a panel, install that exact `tables.xml` in `~/JMRI_UserFiles` and relaunch.

## On the Pi

Blocked while the operating flag is set (see the `operating-flag` skill).

- Before a Pi deploy: `tools/hosts/pi_quit_panelpro.sh --for-deploy`. It uses PanelPro's own Quit and answers No to the Store prompt. The deploy starts PanelPro again, also if the deploy fails.
- By hand: `tools/hosts/pi_start_panelpro.sh`.
- A plain quit (no `--for-deploy`, as before `make ops-pull`) leaves PanelPro closed.

## Sources

- `tools/hosts/pi_quit_panelpro.sh` (exit codes in its header), `tools/hosts/pi_start_panelpro.sh`
- The `deploy` skill (Layout hosts)

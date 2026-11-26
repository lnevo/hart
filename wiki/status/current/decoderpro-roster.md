order: 705
**DecoderPro roster ([ADR-039 amendment](../../decisions/ADR-039-data-masters-in-git.md), 2026-11-26):** the repo is the master, in `jmri/layouts/hart/roster/` (17 locos); the deploy installs it on every host. A Pi deploy stops while a programming session is unpulled; `make roster-pull` brings it in. `locos.csv`'s DCC addresses come from it (`check_roster.py`).

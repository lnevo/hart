order: 590
**Pi PanelPro and deploys (2026-11-13):** quit it with `pi_quit_panelpro.sh --for-deploy` before a Pi deploy; the deploy starts it again, also when it fails. A plain quit stays closed; `HART_PI_RESTART=0` skips the restart.

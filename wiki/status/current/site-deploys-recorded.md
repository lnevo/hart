order: 725
**Website deploys recorded and current (owner, 2026-11-25, [ADR-040](../../decisions/ADR-040-site-deploys-recorded-current-one-at-a-time.md)):** `deploy_hartrailroad.sh` stops when the checkout lacks `origin/main`, runs one at a time under a lock, counts pages and share cards in its drop check, and records the commit, branch and time it shipped; `make orient` shows them.

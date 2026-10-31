# Live status

Updated 2026-10-31. Dated history is in [`STATUS_LOG.md`](STATUS_LOG.md).

## Current state

- **Layout:** `hart`. Masts are stock Basic (ADR-011). JMRI loads `jmri/layouts/hart/output/tables.xml` (ADR-008).
- **Counts:** 45 masts (23 real, 22 virtual), 103 sections, 746 transits, 39 NX pairs, 38 SML sources with 98 destinations, 1,548 traininfo files.
- **Desks:** CATS CTC `HOLD_ONLY` by default; USS is the alternate. Never both.
- **Website:** public at www.hartrailroad.com from `www/`.
- **Build:** helix complete. Main level resumes after Thanksgiving.

## Owed

- Deploy `sync_hart_package.sh --all` when the hosts are online.
- Railroad test of Basic signals: force a real Stop and read back Approach, Clear, Clear, in both directions and through a diverging route.
- Run `tools/ops/sync_desktop_data.py` and settle the first-run conflicts.

## Next


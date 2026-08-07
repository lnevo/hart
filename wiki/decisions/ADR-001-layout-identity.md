# ADR-001 — Layout identity is `hart`

- **Status:** Accepted
- **Date:** 2026-08-07
- **Deciders:** lnevo

## Context

Work proceeded under linear3 → linear4 → linear5 → linear6 names. linear6 holds the best live connectivity and positions but is not registered in `layout_paths.py`.

## Decision

The next-generation layout project is named **`hart`**.

- Paths: `jmri/layouts/hart/`
- Env: `JMRI_LAYOUT=hart`
- Outputs: `hart_blocked.xml`, `hart_prod.xml` (panel-only evolution; tables/profile unchanged)

linear6 remains a **frozen reference** for connectivity/positionability (`reference/linear6_baseline.xml`), not the active `JMRI_LAYOUT`.

## Consequences

- All new pipeline work targets `hart`.
- Docs (`AI_CONTEXT`, README) list hart as the active next-gen layout.
- Agents must not treat linear6 as the writable production target.

## Alternatives considered

- Keep `linear6` as the registered name — rejected; name does not match the railroad (HART) and implies a disposable experiment.
- New name `neville` / `linear7` — rejected in favor of `hart`.

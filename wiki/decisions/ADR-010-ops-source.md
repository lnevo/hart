# ADR-010 — Ops source of record

- **Status:** Accepted. Amended 2026-10-31: documents moved from hart-ops to `docs/`.
- **Date:** 2026-10-31
- **Deciders:** lnevo

## Decision

Every document we create lives in root `docs/`, which is its source of record. Publications are in `docs/ops/`, and build documents and their generators are in `docs/benchwork/`, and `docs/INDEX.md` lists every document, newest first. Only docs specific to one package stay with it, such as the car-card print archive in `external/hart-ops/docs/print`.

`external/hart-ops` remains the source for car data and holds the scripts that generate publications. The Desktop folders are working copies until the final epic retires them.

The website does not hold copies: `www/scripts/published-files.json` names each published file and its source, and the build copies them.

## Consequences

- ADR-013 defines the workflow for adding a car, building its card, and populating STS and Operations Pro.

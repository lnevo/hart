# ADR-010 — Ops source of record

- **Status:** Accepted
- **Date:** 2026-10-31
- **Deciders:** lnevo

## Decision

`external/hart-ops` is the source of record for car cards, waybills, publications and industry routing. The Desktop folders are working copies until the final epic retires them.

## Consequences

- There is no authoritative workflow for editing cars yet. Operations Pro, STS and hart-ops each hold different fields, and need reconciling.
- A defined workflow should cover adding a car, building its card, and populating STS and Operations Pro.

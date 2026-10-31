# ADR-008 — One tables file

- **Status:** Accepted. Supersedes ADR-003's "panel XML only" scope and consolidation D3.
- **Date:** 2026-10-31
- **Deciders:** lnevo

## Context

`tables/new_tables.xml` began as a hand-edit working copy. `jmri/layouts/hart/output/tables.xml` is what JMRI loads and what deploy ships, and it holds the USS CTC data. Keeping both meant two files to keep in step, and deploy edits could reach only one.

## Decision

1. `jmri/layouts/hart/output/tables.xml` is the only tables file. The path stays, because the Mac profile loads it.
2. JMRI and PanelPro edit it, git tracks it, and the Mac is the master for the hosts.
3. In PanelPro, Store to that path. Run scripts with PanelPro and CATS closed.
4. Deploy stops if a profile copy changed since the last deploy.
5. Older table files are in `archive/tables/`.

## Consequences

- Git branches take over the staging role of the working copy.
- `hart_prod.xml` is retired to `archive/layouts/`. The panel lives in `tables.xml`, and script `--sync-output` flags no longer do anything.

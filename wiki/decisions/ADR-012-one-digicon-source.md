# ADR-012 — One Digicon source, two desks

- **Status:** Accepted
- **Date:** 2026-10-31
- **Deciders:** lnevo

## Context

The CATS panels had grown to six files. `HART.xml`, `HART_Master` and `HART_Master4` began as working copies, so the owner could save changes while an agent worked on another file, the same way `new_tables.xml` did before ADR-008. Only three files did real work, and `HART_Master4_wired.xml` was identical to `HART_Master.xml`.

The copies had also drifted. The desks held edits that the source did not, so a rebuild would have undone them, and the 2026-10-31 Basic signal change never reached the desks.

## Decision

1. `cats/panels/HART_Digicon.xml` is the Designer save and the only panel to edit.
2. `python3 cats/scripts/wire_digicon.py` writes `HART_CTC.xml` and `HART_ABS.xml`, the CATS CTC and CATS ABS desks. Both are `HOLD_ONLY`.
3. Nobody edits a desk by hand. A desk change goes in `wire_digicon.py` or `HART_Digicon.xml`.
4. Git branches take over the working-copy role.
5. The old panels, the Gate 1 generators and their documents are in `archive/`.

## Consequences

- Launchers are one CTC and one ABS on each host, with no Master or hold names.
- Deploy removes `HART_Master*.xml` and the old launchers from the Pi and Windows.
- Until that deploy runs, the hosts keep the old panels and do not have the Basic aspect mapping.

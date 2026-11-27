# Decisions

| ADR | Subject | Status |
|---|---|---|
| [001](ADR-001-layout-identity.md) | Layout identity | Accepted |
| [002](ADR-002-naming-contract.md) | Naming contract | Accepted, amended 2026-08-20 by 005 |
| [003](ADR-003-jmri-config-isolation.md) | JMRI config isolation | Superseded by 008 |
| [004](ADR-004-cats-ctc.md) | CATS CTC | Accepted, amended 2026-10-31 |
| [005](ADR-005-public-equipment-names.md) | Public equipment names | Accepted, amends 002 |
| [006](ADR-006-co-1980-signals.md) | Signal rulebook trial | Superseded by 011 |
| [007](ADR-007-repository-layout.md) | Repository layout | Accepted, amended 2026-10-31, 2026-11-09, 2026-11-12 and 2026-11-18, and by 019 |
| [008](ADR-008-tables-ownership.md) | One tables file | Accepted, amended by 014 |
| [009](ADR-009-website-hosting.md) | Website hosting | Accepted |
| [010](ADR-010-ops-source.md) | Ops source of record | Accepted, amended 2026-10-31 and by 019 |
| [011](ADR-011-basic-signals.md) | Stock Basic signals | Accepted |
| [012](ADR-012-one-digicon-source.md) | One Digicon source, two desks | Accepted, amended for the CATS cut-over |
| [013](ADR-013-car-repository.md) | One car repository | Accepted, amended by 015 and 019 |
| [014](ADR-014-jmri-user-files.md) | JMRI_UserFiles on every host | Accepted, amends 008, amended 2026-11-18 |
| [015](ADR-015-operations-files-in-repo.md) | Operations Pro files in the repo | Accepted, amends 013, amended by 019 |
| [016](ADR-016-sts-refreshes-jmri-operations.md) | STS refreshes JMRI Operations | Accepted |
| [017](ADR-017-princess-track-name-swap.md) | Princess track names swapped | Accepted |
| [018](ADR-018-staged-intake-workflow.md) | Staged intake for cars and locomotives | Accepted, amended 2026-11-12 |
| [019](ADR-019-hart-ops-in-hart.md) | hart-ops moves into the hart repo | Accepted, amends 007, 010, 013 and 015 |
| [020](ADR-020-live-sts-on-the-pi.md) | Live STS runs on the Pi | Accepted, amended 2026-11-11 and 2026-11-12 |
| [021](ADR-021-shared-library-and-switch-facts.md) | Shared library and switch facts | Accepted, amended 2026-11-14 and 2026-11-18 |
| [022](ADR-022-timetable-direction-follows-route.md) | Timetable direction follows the route | Accepted, amended 2026-11-14 |
| [023](ADR-023-generated-outputs-side-by-side.md) | Generated panels and pages sit beside the ones they replace | Accepted |
| [024](ADR-024-signals-by-rule.md) | Signal masts are placed by rule on every level | Accepted |
| [025](ADR-025-operating-flag.md) | An operating flag guards the Pi and Windows while the layout is in use | Accepted |
| [026](ADR-026-anyrail-5-3c-master-plan.md) | AnyRail plan 5.3c is the master plan | Accepted |
| [027](ADR-027-staging-from-its-device-map.md) | Staging is built from its device map | Accepted |
| [028](ADR-028-main-upper-virtual-devices.md) | Main and upper levels run on virtual devices named by identity | Accepted |
| [029](ADR-029-tables-xml-is-an-output.md) | `tables.xml` is an output of one device master and a template | Accepted |
| [030](ADR-030-level-is-a-column.md) | The level is a column: one file per fact for every level | Accepted |
| [031](ADR-031-signal-rule.md) | Signals by rule, with prototype mileposts and line codes | Superseded by ADR-024 (2026-11-23) |
| [032](ADR-032-pi-os-trixie-64-bit.md) | The layout Pi runs 64-bit trixie, built from the repo | Accepted |
| [033](ADR-033-generated-then-owner.md) | Generated values, then the owner's, then frozen wiring | Accepted |
| [034](ADR-034-jmri-mqtt-race-overlay.md) | JMRI's MQTT race fix as an overlay until JMRI ships it | Accepted |
| [035](ADR-035-backups.md) | What is backed up, where and how often | Accepted |
| [036](ADR-036-generated-views-not-committed.md) | Generated views are built where they are used, not committed | Accepted |
| [037](ADR-037-one-step-manifest.md) | One step manifest for the checks and the panels build | Accepted |
| [038](ADR-038-one-file-per-status-entry.md) | One file per STATUS entry | Accepted, amends 036 |
| [039](ADR-039-data-masters-in-git.md) | One master per kind of record, kept in git | Accepted |
| [040](ADR-040-site-deploys-recorded-current-one-at-a-time.md) | Website deploys are recorded, current and one at a time | Accepted |
| [041](ADR-041-baselines-lowered-at-wave-end.md) | Baselines are lowered at the end of each wave | Accepted |

Older consolidation decisions are in git history, and ADR-007 records what became of them.

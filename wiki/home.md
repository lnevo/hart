# HART wiki home

Chat is a scratchpad. Decisions that count live here.

| Area | Path |
|------|------|
| Projects | [`projects/`](projects/) |
| Decisions (ADRs) | [`decisions/README.md`](decisions/README.md) |
| Agent / git conventions | [`AGENTS_GIT.md`](AGENTS_GIT.md) |
| Repo layout | [ADR-007](decisions/ADR-007-repository-layout.md) |
| All documents | [`../docs/INDEX.md`](../docs/INDEX.md) |
| Website | [`../www/README.md`](../www/README.md) |
| Pipelines | [`pipelines/README.md`](pipelines/README.md) |
| Pipeline map | [`../docs/pipeline-map/pipeline_map.json`](../docs/pipeline-map/pipeline_map.json) |

**Active projects:** [CATS integration](projects/cats-integration.md) · [level unification](projects/level-unification-handoff.md) · [source-data exceptions](projects/source-data-exceptions-handoff.md) · [web server migration](projects/web-server-migration.md) · [3D station maps](../docs/benchwork/station_maps_3d/README.md)  
**Parked or done:** [speed matching](projects/speedmatching.md) (parked) · [project health hand-off](projects/project-health-handoff.md) (done). Each page in `projects/` opens with a `Status:` line.  
**Public names:** [ADR-002](decisions/ADR-002-naming-contract.md) · [ADR-005](decisions/ADR-005-public-equipment-names.md) · [ADR-011](decisions/ADR-011-basic-signals.md) · [`devices.csv`](../jmri/layouts/hart/data/devices.csv)
**Active layout:** `jmri/layouts/hart/` · `JMRI_LAYOUT=hart`  
**CTC path:** [`cats/`](../cats/) ([CATS](http://cats4ctc.wikidot.com/) Digicon-style; source [Kb0oys/cats](https://bitbucket.org/Kb0oys/cats/src/master/))  
**Digicon system overview (desks + LCOS signals):** [`../docs/ctc/HART_DIGICON_SYSTEM.md`](../docs/ctc/HART_DIGICON_SYSTEM.md)  
**Parked (helix-join release, November 2026):** the USS CTC machine, the Dispatcher System and Entry/Exit (NX) are not in the active panel; data kept in `jmri/layouts/hart/parked/`. The CATS desks stay live.  
**Dispatcher desks:** [CATS](../docs/ctc/DISPATCHER_GUIDE_CTC.md) · parked: [USS](../jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md), [auto](../jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md) · [LE / Dispatcher hoops](../jmri/layouts/hart/parked/DISPATCHER_LAYOUT_HOOPS.md) · [Digicon schematic](../docs/ctc/DIGICON_SCHEMATIC.md)   · [Track lengths](../docs/jmri/TRACK_LENGTHS.md)
**Wiring / LCOS inventory:** [`../docs/wiring/README.md`](../docs/wiring/README.md)  
**Live status:** [`STATUS.md`](STATUS.md)  
**Not pending (never list these):** [`not-pending.md`](not-pending.md)

## For agents

- **What writes or reads a file:** query [`../docs/pipeline-map/pipeline_map.json`](../docs/pipeline-map/pipeline_map.json), the graph of every source, generator and output. Each node has `id`, `path`, `kind`, `status` and `desc`; each edge runs `from` a node `to` the node it feeds. A file's writers are the nodes with an edge into it; its readers are the nodes its edges lead to.
- **Routes and aspects:** CATS owns routes (`HART_CTC.xml`, `HOLD_ONLY`); JMRI Signal Mast Logic owns aspects (stock Basic appearances, ADR-011). `cats/` is the CTC overlay only.
- **Gitignored data:** `media/`, `ops/car-cards/`, `docs/wiring/bench/`, and the STS database and backups. Git does not protect these.
- **Older context:** linear4 and NextTrain history is in [`../archive/docs/AI_CONTEXT_history.md`](../archive/docs/AI_CONTEXT_history.md).

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
| Report cards (project, code, data, website UX, agent experience) and the master dashboard | [`report-cards.md`](report-cards.md) |
| Pipeline map | [`../docs/pipeline-map/pipeline_map.json`](../docs/pipeline-map/pipeline_map.json) |

**Active projects:** [agent experience cleanup](projects/ax-cleanup.md) (round 3) · [cleanup and streamlining](projects/cleanup-streamline-handoff.md) · [every script in the pipeline](projects/pipeline-coverage-handoff.md) · [speed matching](projects/speedmatching.md) · [data masters](projects/data-masters.md) · [CATS integration](projects/cats-integration.md)  
**Parked or done:** [LE spur names beside their tracks](projects/le-spur-labels.md) (done 2026-11-27) · [leftovers after the loose ends](projects/leftovers-round.md) (done 2026-11-27) · [loose ends after the waves](projects/wave-loose-ends.md) (done 2026-11-27) · [health round 2](projects/health-round2-handoff.md) (done 2026-11-27) · [MQTT race upstream](projects/mqtt-race-upstream-handoff.md) (done 2026-11-26: merged for JMRI 5.19.2) · [generated, then the owner's](projects/naming-layers-handoff.md) (done 2026-11-25) · [one bean and row process for every level](../archive/history/wiki/projects/builder-merge.md) (done in the naming-layers plan 2026-11-25) · [schematic solver on any plan](../archive/history/wiki/projects/one-band-solver.md) (done 2026-11-23: 37 of 38 sample plans draw) · [level unification](../archive/history/wiki/projects/level-unification-handoff.md) (done 2026-11-23; step 7 under Owed in STATUS). Each page in `projects/` opens with a `Status:` line.  
**Public names:** [ADR-002](decisions/ADR-002-naming-contract.md) · [ADR-005](decisions/ADR-005-public-equipment-names.md) · [ADR-011](decisions/ADR-011-basic-signals.md) · [`devices_field.csv`](../jmri/layouts/hart/data/devices_field.csv) and [`devices_generated.csv`](../jmri/layouts/hart/data/devices_generated.csv) (the device master, ADR-029)
**Active layout:** `jmri/layouts/hart/` · `JMRI_LAYOUT=hart`  
**CTC path:** [`cats/`](../cats/) ([CATS](http://cats4ctc.wikidot.com/) Digicon-style; source [Kb0oys/cats](https://bitbucket.org/Kb0oys/cats/src/master/))  
**Digicon system overview (desks + LCOS signals):** [`../docs/ctc/HART_DIGICON_SYSTEM.md`](../docs/ctc/HART_DIGICON_SYSTEM.md)  
**Parked (helix-join release, November 2026):** the USS CTC machine, the Dispatcher System (with its occupancy lamps, stations and yard throats) and Entry/Exit (NX) are not in the active panel; data kept in `jmri/layouts/hart/parked/`. The CATS desks stay live.  
**Dispatcher desks:** [CATS](../docs/ctc/DISPATCHER_GUIDE_CTC.md) · parked: [USS](../jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md), [auto](../jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md) · [LE / Dispatcher hoops](../jmri/layouts/hart/parked/DISPATCHER_LAYOUT_HOOPS.md) · [Digicon schematic](../docs/ctc/DIGICON_SCHEMATIC.md)   · [Track lengths](../docs/jmri/TRACK_LENGTHS.md)
**Wiring / LCOS inventory:** [`../docs/wiring/README.md`](../docs/wiring/README.md)  
**Live status:** [`status/`](status/), one file per entry; `make status` builds `wiki/STATUS.md` (ADR-038)  
**Not pending (never list these):** [`not-pending.md`](not-pending.md)

## For agents

- **What writes or reads a file:** query [`../docs/pipeline-map/pipeline_map.json`](../docs/pipeline-map/pipeline_map.json), the graph of every source, generator and output. Each node has `id`, `path`, `kind`, `status` and `desc`; each edge runs `from` a node `to` the node it feeds. A file's writers are the nodes with an edge into it; its readers are the nodes its edges lead to.
- **Routes and aspects:** CATS owns routes (`HART_CTC.xml`, `HOLD_ONLY`); JMRI Signal Mast Logic owns aspects (stock Basic appearances, ADR-011). `cats/` is the CTC overlay only.
- **Gitignored data:** `media/`, `ops/car-cards/`, `docs/wiring/bench/`, and the STS database and backups. Git does not protect these.
- **Older context:** linear4 and NextTrain history is in [`../archive/history/docs/AI_CONTEXT_history.md`](../archive/history/docs/AI_CONTEXT_history.md).

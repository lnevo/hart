# JMRI layouts

One subdirectory per layout. The only active layout is **hart** (`export JMRI_LAYOUT=hart`); see
[`hart/README.md`](hart/README.md). The earlier layouts (mac, linear3 to linear6, new) are in `archive/data/layouts/`.

## hart

```
layouts/hart/
  anyrail/      AnyRail export of the plan (geometry snapshot)
  ctc/          USS CTC machine files (parked)
  data/         layout facts: switches, switch legs, public names, schematic data
  dispatcher/   Dispatcher System traininfo and guide (parked)
  operations/   Operations Pro files (ADR-015)
  output/       tables.xml, the one tables file (ADR-008)
  parked/       the parked features' data and the scripts that serve them
  scripts/      hart's build, check and maintenance scripts
```

See [`wiki/home.md`](../../wiki/home.md).

## Starting a new layout

There is no supported path for a layout other than hart. The AnyRail scripts that turned an export into a blocked
panel are retired in `archive/code/jmri-scripts/` ([`wiki/pipelines/jmri-anyrail.md`](../../wiki/pipelines/jmri-anyrail.md)),
and hart's new levels come from the schematic (`make panels`).

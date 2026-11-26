# ADR-037 — One step manifest for the checks and the panels build

- **Status:** Accepted
- **Date:** 2026-11-25
- **Deciders:** lnevo

## Context

The pipeline's steps are written down by hand in several places: `tools/check.sh` and `tools/ci/docs_checks.sh` list the checks; `build_panels.sh`, its header, the wiki table, `test_build_panels.STEPS` and `panel_stamps.STEPS` list the panels steps; `pipeline_map.json` draws both. Checks exist to catch the copies disagreeing (map coverage, the stamps audit), and they have drifted anyway: 13 of the 35 checks have no edge to `check.sh` in the map, 11 more have one with no job name, the five panels guards have no edges, and three copies still say the masts step writes the device master, which stopped at naming-layers step 12. A read-only design study measured this; it is in [`docs/pipeline-map/build-graph-design.md`](../../docs/pipeline-map/build-graph-design.md).

## Decision

1. One manifest in TOML under `tools/pipeline/` (`checks.toml`, later `panels.toml`), read by a stdlib loader, `tools/pipeline/manifest.py`. TOML because `tomllib` is in Python 3.11 and later (the Mac, CI and the Windows box run 3.12 or 3.13), it keeps comments, and its blocks merge line by line.
2. `check.sh`, `docs_checks.sh`, the make panels step list and the map's script nodes and check edges are generated from it. A load error or an empty list fails the run.
3. The read trace stays what decides a skip. Declared inputs are checked against the trace (a warning first, then a failure in the weekly full run); they never replace it.
4. Unit-test jobs and the map's hand-kept file, host and human nodes stay out of the manifest; `pipeline_map.json` stays a committed source with generated lanes.
5. The migration goes in stages that each merge alone and leave everything green (design, section 5). The panels stage (`tools/schematic/`) waits until the naming-layers work (ADR-033) is closed and unclaimed.

## Consequences

- A new check or panels step is written once. The registration checks shrink, and the regex scan of `check.sh` and `build_panels.sh` in map coverage goes.
- Splitting today's single `static` job into one job per check (stage 4b) lets an unchanged check skip after a commit and in CI, which it cannot today.
- Each job's stamp key must hold its own manifest entry, so that a changed command reruns that job; stage 2 tests this.
- The stage that converts the map's script nodes is a large JSON diff; it lands when `make orient` shows few open map changes.

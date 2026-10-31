# ADR-013 — One car repository

- **Status:** Accepted
- **Date:** 2026-10-31
- **Deciders:** lnevo

## Context

Operations Pro, STS and hart-ops held different cars and fields, because not every car has been photographed. No defined workflow added a car to all of them. Roster-only cars lived in `OperationsCarRoster.xml`, which was both an input to and an output of the roster build.

## Decision

1. `external/hart-ops/data/image_metadata.csv` is the one car repository, and holds the whole fleet. A car with no photo has a blank `source_image`.
2. A car starts from a photo or from a set of questions, through `bin/cars`.
3. STS, Operations Pro and any future inventory tool are fed from the repository.
4. `data/car_queue.csv` tracks which new cars still need a card, STS or Operations Pro.
5. An added car keeps a fixed STS id, recorded in `seed/inputs/sts_added_cars.csv`. Roster order sets the other ids, so inserting a car would otherwise renumber the cars after it and break their photos.
6. Publishing adds cars to Operations Pro and never replaces the roster, so session state survives.

## Consequences

- Differences between the tools are reported by `bin/cars compare`. Resolving them is later work.
- Corrections to existing cars do not yet reach STS or Operations Pro.

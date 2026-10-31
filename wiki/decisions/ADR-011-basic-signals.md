# ADR-011 — Stock Basic signals

- **Status:** Accepted. Supersedes ADR-006.
- **Date:** 2026-10-31
- **Deciders:** lnevo

## Context

Basic-enhanced has one aspect for "the next signal is Approach": Advanced Approach, which flashes. With that aspect disabled, JMRI had nothing valid to show and displayed Stop. That Stop forced an Approach behind it, then another false Stop, so Stop and Approach alternated back up the line behind any real Stop.

## Decision

1. Use stock **Basic** for every mast: homes `two-searchlight`, dwarfs and dispatcher virtuals `one-low`.
2. No aspects are disabled.
3. Panel icons use the `default` image set. These are the same AAR-1946 drawings as before.
4. Mast user names, heads and SML pairs do not change.

## Consequences

- Behind a Stop, signals read Approach, then Clear.
- Lamps are unchanged: Clear G/R, Approach Y/R, Diverging Clear R/G, Diverging Approach R/Y, Stop R/R. Dwarfs: Clear, Approach, Stop.
- Diverging Clear speed is Medium, not Limited.
- Changing mast type again means rewriting SHSM system names in tables.
- Needs a test on the railroad: force a real Stop and read the signals back.

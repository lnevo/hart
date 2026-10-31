# ADR-009 — Website hosting

- **Status:** Accepted. Supersedes consolidation D9.
- **Date:** 2026-10-31
- **Deciders:** lnevo

## Decision

The website is public at www.hartrailroad.com. `www/` is its source and `www/scripts/deploy_hartrailroad.sh` publishes it.

## Consequences

- Review pages and `www/review-data/` stay local and are never published.
- The STS web and scale interface is separate from the website. It runs on the Mac. Moving it to the Pi is an optional, low-priority goal.

order: 160
**One file per STATUS entry (owner, 2026-11-25, [ADR-038](../../decisions/ADR-038-one-file-per-status-entry.md)):** each entry is its own file under `wiki/status/`, ordered by its `order:` line and at most 60 words ([README](../README.md)); `make status` and the session-start hook build `wiki/STATUS.md`, which is not committed.

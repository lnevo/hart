# Archive

Retired files, kept for reference. Nothing in this folder runs: no build, deploy or host uses it, and `ruff`, the data checks and the pipeline map skip it.

The files are grouped by kind:

| Folder | Holds |
|---|---|
| [`code/`](code/README.md) | Retired scripts and tools |
| [`data/`](data/README.md) | Retired data: old layouts, panels, tables, wiring workbooks, exports and site files |
| [`history/`](history/README.md) | Finished hand-offs, old wiki pages, prompts and notes |

A file comes here when the live tree no longer needs it ([ADR-007](../wiki/decisions/ADR-007-repository-layout.md)). Search it with `rg --no-ignore <term> archive`, because `.ignore` hides it from ripgrep.

On 2026-11-26 the folder was regrouped into these three parts, and files that were byte-identical to another archived file were removed. Each affected layout and panel README lists what went and which copy is kept.

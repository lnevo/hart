# HART consolidation — objective

**Charter:** Build a validated, browsable, refactored HART railroad software tree under `consolidation/` — without changing live operational sources on disk.

When this tree is complete (versions current, scripts clean, validators green), it becomes the **authoritative** workspace. Until then we keep building; live layout and Desktop/HART stay read-only.

## Success criteria

1. **Live inventory** — every pipeline documents what it reads/writes today (`LIVE_SOURCES.md`).
2. **Proposed SoR** — draft canonical artifacts under `sor/`.
3. **Draft runbooks** — pipeline guides under `wiki/pipelines/` with SoR tables.
4. **Read-only validators** — `validators/run_all.sh` checks live state; reports go to `audits/`.
5. **Recorded decisions** — `DECISIONS_RECORDED.md` locks consolidation defaults.
6. **Human navigation** — open [`index.html`](index.html); F-root files at [`html/archive/f-root-index.html`](html/archive/f-root-index.html).
7. **Backlog tracking** — [`BACKLOG.md`](BACKLOG.md) lists build progress.

## Non-goals (infrastructure)

- MQTT broker, Pi/Windows layout hosts, Windows COM bridge — documented, not packaged.
- Optional raw Car Cards `Images/` (~982 MB) — use `DESKTOP_MIRROR_RAW=1` if needed.
- Editing live `jmri/`, `cats/`, `tables/`, or moving/slimming live Desktop/HART during build.

## Lead engineer role

Review live code and docs as **read-only references**. Write improvements, audits, ADRs, and refactored script **copies** only under `consolidation/`. Flag gaps; do not patch live workflows during the build.

## Related

- [`AGENTS.md`](AGENTS.md) — mandatory agent instructions
- [`BACKLOG.md`](BACKLOG.md) — build checklist
- [`manifest.yaml`](manifest.yaml) — pipeline registry

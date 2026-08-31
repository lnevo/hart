# Decisions recorded — 2026-08-31

Approved by owner. Consolidation work proceeds under these locked defaults until explicitly revised.

| ID | Approved | Decision | Notes |
|----|----------|----------|-------|
| **D1** | Y | Parallel workspace | All writes under `consolidation/` until promotion |
| **D2** | Y (modified) | **Single names SoR: `public_name_map.csv`** | Device Map authority; audit then retire `block_display_names.csv` if redundant |
| **D3** | Y | Tables merge order | `new_tables.xml` → scripts → `output/tables.xml` → `hart_prod.xml`; no blind copy |
| **D4** | Y | Wiring SoR | Git `docs/wiring/` canonical; Desktop bench = export mirror |
| **D5** | Y (modified) | No eternal one-shot cleanups | Retired logic → `unused-modules/`; stronger pre-promotion review |
| **D6** | Y | MQTT live roster | Non-empty `track/signalmast/<packed>`; verify no static allow-lists |
| **D7** | Y | Meta-repo | `hart` hub; LCOS, STS, helpers as siblings; submodules later |
| **D8** | Y | BOM excluded | PCBWay out of consolidation scope |
| **D9** | Y (modified) | Local HTML portal now | Pi-hosted portal with STS/mimic/JMRI later (low priority) |
| **D10** | Y (modified) | LCOS as-is | Working published version moves into consolidation review; minimal change |
| **D2f** | Y | Virtual stub masts = **A** | 17 Dispatcher stubs map-only; no signalmast beans — [`audits/proposed-virtual-masts.md`](audits/proposed-virtual-masts.md) |
| **D2a** | Y | Retire `block_display_names.csv` | After notes merge + consumer promotion; snapshot in `sor/names/` only |
| **D2b** | Y | Migrate block_display `notes` → map | Draft: `scripts/merge_block_display_notes_into_map.py` → `sor/names/public_name_map_merged.csv` |
| **D2c** | Y | phase02 reads map | Draft: `scripts/check_hart_phase02_from_map.py`; promote to live on next batch |
| **D2d** | Y | All consumers together | phase02 + `refresh_bean_comments` + bootstrap + README + ADR-002 in one promotion |
| **D2e** | Y | No `role` column | Derive OS via `layer=block` + `proposed.startswith("OS ")` |
| **ADR-set** | Y | Consolidation ADRs accepted | validation tiers, hygiene, SoR, tables merge — `wiki/decisions/README.md` |
| **P3a** | Y | Create **hart-ops** repo | Car Cards, publications, Industries — migration plan in `cross-repo/hart-ops/` |
| **P3b** | Y | Submodules | Stage `consolidation/external/` — [`cross-repo/SUBMODULE_MANIFEST.yaml`](cross-repo/SUBMODULE_MANIFEST.yaml) · hart-ops pin pending repo |
| **P4a** | Y | Archive ingest | Selective class-F → `docs/archive/` plan (consolidation draft; not live until promotion) |
| **D10b** | Y (closed) | LCOS bridge | No pending LCOS actions; event 125/pacing considered done or out of scope |
| **D11** | Y | Car roster single SoR | `image_metadata.csv` → Merged → Operations export; STS filtered subset — [`wiki/decisions/ADR-car-roster-single-sor.md`](wiki/decisions/ADR-car-roster-single-sor.md) |
| **D12** | Y | Bench freeze | No Pi deploy, no Desktop/HART edits, no live `hart` edits during consolidation; cutover = separate project |

## Follow-up work unlocked

See [`NEXT_ROUND.md`](NEXT_ROUND.md).

## Supersedes

Checkbox sections in [`DECISIONS_PENDING.md`](DECISIONS_PENDING.md) — use this file as the active record.

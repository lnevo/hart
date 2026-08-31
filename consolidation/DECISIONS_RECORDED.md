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

## Follow-up work unlocked

See [`NEXT_ROUND.md`](NEXT_ROUND.md).

## Supersedes

Checkbox sections in [`DECISIONS_PENDING.md`](DECISIONS_PENDING.md) — use this file as the active record.

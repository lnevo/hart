# D2 promotion — checklist

**Principle approved (2026-08-31):** [`public_name_map.csv`](../../../jmri/layouts/hart/data/public_name_map.csv) is the **single** names SoR. See [`ADR-names-single-sor.md`](ADR-names-single-sor.md).

**Sub-decisions D2a–e approved 2026-08-31 (all Option A).** Drafts live under `consolidation/` only. Live edits happen **only when you explicitly request promotion** for a named item.

---

## Already settled

| Item | Evidence |
|------|----------|
| Map is Device Map authority | Owner confirmed; `sync_public_name_map.py` |
| OS names for phase02 | `propose_os_from_map.py` — **23/23** legacy OS rows derivable from map |
| Live equipment names on beans | 862 userNames; 23 signalmasts all in map |
| Generator order | `sync_public_name_map` → `apply_public_names` → `refresh_bean_comments` → exports |

---

## D2a — Retire `block_display_names.csv`

**Approved: Option A** — delete live file after consumer migration; keep snapshot in `consolidation/sor/names/` only.

26 note strings handled by D2b merge (see merge script output).

---

## D2b — Migrate block_display `notes` into map

**Approved: Option A** — copy into map `notes`, then retire block_display.

| Target | Example block_display note | Map row to enrich |
|--------|------------------------------|-------------------|
| Yard throats | `hidden throat; same occupancy as Track S-1` | `Track S-1 West/East` block rows |
| Crossover | `Crossover leg` | OS Switch 23a/23b/35a/35b rows |
| EH | `occupancy Block 13-7 / M2S1306` | Track EH-1 row |
| Yard plate | `West Yard plate; access Switch 3 only` | Track W-1/W-2 |

Draft: `consolidation/scripts/merge_block_display_notes_into_map.py` → `sor/names/public_name_map_merged.csv`.

---

## D2c — `check_hart_phase02.py` reads map

**Approved: Option A** — promote on next live batch.

Draft (validator): `consolidation/scripts/check_hart_phase02_from_map.py` · `validators/check_phase02_from_map.sh`.

OS filter: `layer=block` + `proposed.startswith("OS ")` + existing `secondary_ok` for 23b/35a/7b.

---

## D2d — Other live consumers (one batch)

**Approved: Option A** — all together on promotion:

| File | Change on promotion |
|------|---------------------|
| `check_hart_phase02.py` | OS from map (`names_from_map.os_public_names_from_map`) |
| `refresh_bean_comments.py` | Remove `block_display_names.csv` from target list |
| `bootstrap_hart_from_linear6.py` | Remove DISPLAY_CSV path (bootstrap done) |
| `jmri/layouts/hart/README.md` | Single map SoR wording |
| Live `wiki/decisions/ADR-002` | Point only to map |

---

## D2e — Map schema

**Approved: Option A** — no `role` column; use `layer` + `cp` + `notes`.

---

## D2f — Virtual stub masts (related)

**Approved: Option A** — 17 Dispatcher stub masts stay **map-only**; no signalmast beans. See [`audits/proposed-virtual-masts.md`](../audits/proposed-virtual-masts.md).

---

## Live promotion (on explicit request only)

When you ask to promote D2, apply in this order to **live** paths:

1. Apply `public_name_map_merged.csv` → live `public_name_map.csv`
2. `sync_public_name_map` / `apply_public_names` if map edited
3. Promote phase02 + refresh_bean_comments + bootstrap + README + ADR-002
4. Delete `block_display_names.csv`; keep `consolidation/sor/names/` snapshot
5. `bash consolidation/validators/run_all.sh` green
6. Update live wiki STATUS + README

---

## Approval record

| ID | Decision | Approved | Notes | Date |
|----|----------|----------|-------|------|
| D2a | Retire block_display | Y | After merge + promotion | 2026-08-31 |
| D2b | Notes migration | Y | Draft merge script | 2026-08-31 |
| D2c | phase02 from map | Y | Draft validator green | 2026-08-31 |
| D2d | Other consumers | Y | One batch on promotion | 2026-08-31 |
| D2e | Map schema | Y | No role column | 2026-08-31 |
| D2f | Virtual stubs = A (map-only) | Y | Document-only | 2026-08-31 |

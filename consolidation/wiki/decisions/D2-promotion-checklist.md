# D2 promotion — decisions still needed

**Principle already approved (2026-08-31):** [`public_name_map.csv`](../../../jmri/layouts/hart/data/public_name_map.csv) is the **single** names SoR. See [`ADR-names-single-sor.md`](ADR-names-single-sor.md).

**Not yet promoted to live** — items below need your approval before editing live scripts/files.

---

## Already settled (no further decision)

| Item | Evidence |
|------|----------|
| Map is Device Map authority | Owner confirmed; `sync_public_name_map.py` |
| OS names for phase02 | `propose_os_from_map.py` — **23/23** legacy OS rows derivable from map |
| Live equipment names on beans | 862 userNames; 23 signalmasts all in map |
| Generator order | `sync_public_name_map` → `apply_public_names` → `refresh_bean_comments` → exports |

---

## D2a — Retire `block_display_names.csv`?

**Proposal:** Delete live file after consumer migration; keep last snapshot in `consolidation/sor/names/` only.

| Option | Meaning |
|--------|---------|
| **Approve retire** | Remove file on promotion (recommended) |
| **Keep as export** | Auto-generate read-only index from map (optional script) |

**Gap if retired without migration:** 20 **note strings** live only in block_display `notes` column (throat hints, crossover leg, EH occupancy hints). Track/switch **names** themselves are already in the map.

- [ ] Approve retire after notes migrated (D2b)
- [ ] Approve retire and **drop** standalone notes (accept loss of index-only prose)
- [ ] Keep file as generated export from map

---

## D2b — Migrate block_display `notes` into map?

**Only if you care about preserving index prose** (hidden throat lines, `Crossover leg`, EH occupancy hints).

| Target | Example block_display note | Map row to enrich |
|--------|------------------------------|-------------------|
| Yard throats | `hidden throat; same occupancy as Track S-1` | `Track S-1 West/East` block rows |
| Crossover | `Crossover leg` | OS Switch 23a/23b/35a/35b rows |
| EH | `occupancy Block 13-7 / M2S1306` | Track EH-1 row |
| Yard plate | `West Yard plate; access Switch 3 only` | Track W-1/W-2 |

- [ ] **Migrate** notes into map `notes` column then retire block_display (recommended if ops docs reference them)
- [ ] **Skip** — map comments from Device map are enough; delete block_display

**Consolidation can draft a one-shot merge script** under `consolidation/scripts/` — not live until approved.

---

## D2c — `check_hart_phase02.py` reads map (promotion)

**Proposal:** Replace `block_display_names.csv` read with same filter as `propose_os_from_map.py` (blocks/layer with `OS ` proposed names + existing `secondary_ok` set for 23b/35a/7b).

- [ ] Approve promotion of phase02 change
- [ ] Defer — keep phase02 on block_display until next maintenance window

Draft: `consolidation/scripts/check_hart_phase02_from_map.py` (wrapper, not live yet).

---

## D2d — Other live consumers

| File | Change on promotion | Approval |
|------|---------------------|----------|
| `refresh_bean_comments.py` | Remove `block_display_names.csv` from text-replace path list | [ ] |
| `bootstrap_hart_from_linear6.py` | Remove `--no-display` path / DISPLAY_CSV (hart bootstrap done) | [ ] |
| `jmri/layouts/hart/README.md` | Single map SoR wording | [ ] |
| Live `wiki/decisions/ADR-002` | Point only to map | [ ] |

---

## D2e — Map schema (optional enhancement)

block_display had explicit **`role`** column (`os`, `yard`, `track`, `interchange`). Map uses **`layer`** (`turnout`, `block`, `occupancy`, …).

| Option | Meaning |
|--------|---------|
| **Use layer + cp** | No schema change; phase02 filters `proposed.startswith("OS ")` |
| **Add `role` column to map** | Easier queries; one-time CSV migration |

- [ ] No schema change (recommended)
- [ ] Add `role` column on promotion

---

## D2f — Virtual stub masts (related, not D2 core)

**Approved 2026-08-31: Option A** — 17 Dispatcher stub masts stay **map-only**; no signalmast beans. See [`audits/proposed-virtual-masts.md`](../audits/proposed-virtual-masts.md).

Validator may warn on 17 `Mast*` names; exclude from fail via `notes=virtual` when we tighten the check.

---

## Promotion order (when you approve D2a–d)

1. Optional D2b notes merge into map (live `public_name_map.csv` — **requires promotion approval**)
2. `sync_public_name_map` / `apply_public_names` if map edited
3. Promote phase02 + refresh_bean_comments consumer changes
4. Delete `block_display_names.csv`
5. `bash consolidation/validators/run_all.sh` green
6. Update live wiki STATUS + README

---

## Approval record (D2 sub-decisions)

| ID | Decision | Approved | Notes | Date |
|----|----------|----------|-------|------|
| D2a | Retire block_display | | | |
| D2b | Notes migration | | | |
| D2c | phase02 from map | | | |
| D2d | Other consumers | | | |
| D2e | Map schema | | | |
| D2f | Virtual stubs = A (map-only) | Y | Document-only | 2026-08-31 |

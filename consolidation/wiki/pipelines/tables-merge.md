> **Consolidation draft** — cross-cutting runbook for pipelines **2–7**. Live sources read-only; see [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md). **D12 bench freeze:** document and validate only — no live table edits.

## Source of record

| Kind | Live (read-only) | Consolidation |
|------|------------------|---------------|
| ADR | — | [`ADR-tables-merge-order`](../decisions/ADR-tables-merge-order.md) (D3) |
| Audit | — | [`audits/tables-pipeline.md`](../../audits/tables-pipeline.md) |
| Cleanup ref | `jmri/layouts/hart/scripts/cleanup_uss_ctc_leftovers.py` | [`scripts/cleanup_uss_ctc_leftovers.py`](../../scripts/cleanup_uss_ctc_leftovers.py) |
| Retired one-shots | — | [`unused-modules/tables/`](../../unused-modules/tables/) (D5) |
| Writable source | `tables/new_tables.xml` | documented only — **do not edit live** |
| Deploy bundle | `jmri/layouts/hart/output/tables.xml` | read-only for validators |
| LE monitor | `jmri/layouts/hart/output/hart_prod.xml` | independent LE patches OK |

**Decision D3:** merge order is fixed. **Never** blind-copy between artifacts.

---

# Tables merge — cross-cutting pipeline

JMRI stores layout beans, Signal Mast Logic, USS CTC, CATS paneleditors, and Dispatcher graph data in a **tables bundle**. HART splits that into three files with different roles. Most numbered pipelines (2–7) read or write **`tables/new_tables.xml`**; only specialized sync scripts may patch **`output/tables.xml`** in place.

## Artifact chain

```
tables/tables.xml                    ← legacy snapshot — READ ONLY (agents never edit)
        ↓ (historical baseline only)
tables/new_tables.xml                ← writable working source (live promotion only)
        ↓ pipeline scripts (names, beans, SML, LE patches, …)
jmri/layouts/hart/output/tables.xml ← deploy bundle (LE + SML + CTC + Dispatcher)
        ↓ independent LE-only sync allowed
jmri/layouts/hart/output/hart_prod.xml ← standalone LE monitor (not full bundle)
```

### What lives where

| Section | Typical home | Notes |
|---------|--------------|-------|
| Turnouts, sensors, blocks, heads, masts | `new_tables.xml` → bundle | Pipeline 2–3 |
| `signalmastlogics` (native SML + NX) | `new_tables.xml` → **section sync** | Pipeline 4 — use `sync_hart_sml_to_deployment.py` |
| `<ctcdata>`, USS paneleditor | **`output/tables.xml`** primarily | Pipeline 6 — regen `GUIObjects.xml`, do not wipe |
| Dispatcher stations / traininfo refs | bundle | Pipeline 7 |
| CATS Master hold panels | separate XML under `cats/panels/` | Pipeline 5 — regenerate, never string-replace |

## Hard rules (D3)

1. **Never edit** `tables/tables.xml` with tools.
2. **Never copy** `new_tables.xml` → `output/tables.xml` whole-file (drops `<ctcdata>` / USS).
3. **Never overwrite** `output/tables.xml` with `hart_prod.xml`.
4. **Regenerate** USS `GUIObjects.xml` and CATS hold panels — do not search-replace generated XML.
5. **Do not store** JMRI tables from a CATS session (PanelPro owns the bundle).
6. **One-shot deletes** (D5): document in `unused-modules/tables/`; do not grow immortal delete lists in live cleanup scripts.

## Sync patterns

| Pattern | When | Script |
|---------|------|--------|
| **Section replace** | SML changed in `new_tables.xml` | `sync_hart_sml_to_deployment.py` — replaces `signalmastlogics` only; verifies CTC/panel counts unchanged |
| **`--sync-output`** | LE patch scripts on working source | `apply_le_cleanup.py`, `apply_yard_throat_blocks.py`, `polish_hart_layout_editor.py` — also patch `output/tables.xml` and optionally `hart_prod.xml` **independently** |
| **CTC regen** | USS track diagram change | `gen_ctc_track_plan.py` → `ctc/GUIObjects.xml` + targeted tables writes |
| **Full-file copy (forbidden)** | — | Do not `cp new_tables.xml output/tables.xml` |

## Typical promotion order (live — on explicit request only)

After any tables-affecting change, run in order:

```bash
export JMRI_LAYOUT=hart

# 1 — Names (pipeline 2)
python3 jmri/layouts/hart/scripts/sync_public_name_map.py
python3 jmri/layouts/hart/scripts/apply_public_names.py --apply
python3 jmri/layouts/hart/scripts/refresh_bean_comments.py --apply

# 2 — Signal beans / SML (pipelines 3–4) — regenerate via their scripts, then:
python3 jmri/layouts/hart/scripts/sync_hart_sml_to_deployment.py

# 3 — USS / CTC if touched (pipeline 6)
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --tables jmri/layouts/hart/output/tables.xml

# 4 — Contract audit (Tier A gate)
python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict
bash consolidation/validators/run_all.sh
```

Dispatcher graph (pipeline 7) and CATS Masters (pipeline 5) have their own regen steps — see those guides. They still **consume** the tables bundle; they do not replace the merge rules above.

## Consolidation validators (read-only)

| Check | Script |
|-------|--------|
| Panel contracts | `validators/check_audit_strict.sh` → live `audit_panel_contracts.py --strict` |
| Phase02 layout | `validators/check_phase02.sh` |
| SML invariants (93 dests) | `validators/check_sml_invariants.py` |
| Names snapshot | `validators/check_names_diff.py` |

Run all: `bash consolidation/validators/run_all.sh`

## Related pipelines

| # | Guide | Tables role |
|---|-------|-------------|
| 2 | [public-names](public-names.md) | Bean `userName` + comments |
| 3 | [digicon-signal-beans](digicon-signal-beans.md) | IH / SHSM beans |
| 4 | [native-sml](native-sml.md) | SML + NX; section sync |
| 5 | [cats-masters](cats-masters.md) | Separate hold XML — regen from beans |
| 6 | [uss-ctc](uss-ctc.md) | `<ctcdata>` + USS board |
| 7 | [dispatcher-system](dispatcher-system.md) | Graph / traininfo |

## Do not

- Run CATS CTC and USS CTC simultaneously
- Append one-shot OpenLCB deletes to live cleanup without archiving first — see [`openlcb-leftover-sensors.md`](../../unused-modules/tables/openlcb-leftover-sensors.md)
- Edit tables from consolidation workspace during bench freeze (D12)

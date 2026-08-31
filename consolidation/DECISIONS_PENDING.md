# Decisions pending — batch approval

Review and approve **all sections** in parallel. Consolidation work proceeds with these as defaults until you change them.

---

## D1 — Workspace model

**Proposal:** All consolidation output stays under `hart/consolidation/` until explicit promotion.

- [ ] **Approve** — live sources read-only; promotion is a separate gated step
- [ ] **Reject** — allow direct live edits for doc-only fixes

**Default if silent:** Approve.

---

## D2 — Proposed SoR for names (pipeline 2)

**Recorded 2026-08-31:** **Single authority — `public_name_map.csv`**. Retire `block_display_names.csv` after consumer migration. See [`DECISIONS_RECORDED.md`](DECISIONS_RECORDED.md) and [`wiki/decisions/ADR-names-single-sor.md`](wiki/decisions/ADR-names-single-sor.md).

**Original proposal:** Keep two CSVs with strict scope (per ADR-002 / ADR-005):

| File | Role | Live path | Proposed consolidation copy |
|------|------|-----------|----------------------------|
| `public_name_map.csv` | Apply map: identity, proposed renames, device comments | `jmri/layouts/hart/data/` | `sor/names/public_name_map.csv` (snapshot for diff) |
| `block_display_names.csv` | Live CP/OS/track index (not apply script) | same | `sor/names/block_display_names.csv` |

Generator order: `sync_public_name_map` → `apply_public_names` → `refresh_bean_comments` → export pipelines.

- [ ] **Approve** dual-CSV scope
- [ ] **Merge** into single manifest (specify how): ___________

**Default:** Approve dual-CSV scope.

---

## D3 — Tables XML merge order (pipelines 2–7)

**Proposal:** Documented chain only — no change to live files until promotion.

1. `tables/new_tables.xml` — **writable working source**
2. Pipeline scripts (names, SML, CTC, signal heads, …)
3. Export / sync → `jmri/layouts/hart/output/tables.xml` — **deploy bundle**
4. `hart_prod.xml` — standalone LE monitor artifact (not full CTC bundle)

Never copy `new_tables.xml` over `output/tables.xml` blindly (drops CTC / `<ctcdata>`).

- [ ] **Approve**
- [ ] **Change order:** ___________

---

## D4 — Wiring SoR (pipeline 8)

**Proposal:**

| Location | Role |
|----------|------|
| `hart/docs/wiring/` (git) | **Canonical** for v85 pack and generators |
| `~/Desktop/HART/Wiring Documentation/` | Bench export mirror only |
| `consolidation/sor/wiring/` | Draft snapshots + crosswalk CSVs |

Coordinate merges with wiring agent; consolidation does not edit live `docs/wiring/` without promotion.

- [ ] **Approve**
- [ ] **Desktop bench is co-SoR:** ___________

---

## D5 — Immortal delete lists (pipeline 3 / cleanup scripts)

**Proposal:** One-shot table deletes (e.g. OpenLCB routes 0001–0004) must **not** live forever in `cleanup_uss_ctc_leftovers.py`. Refactored copy in `consolidation/scripts/` separates USS vs Digicon concerns.

- [ ] **Approve** refactor in consolidation copy first; promote after Tier A green
- [ ] **Keep** immortal lists in live script

---

## D6 — MQTT live heads (pipeline 3)

**Proposal:** Live roster = non-empty `track/signalmast/<packed>` from LCOS. No static allow-lists in publisher or bridge. SET/Unheld gated on live mast traffic.

- [ ] **Approve** (matches current direction on branch)
- [ ] **Revert** to include-list model

---

## D7 — Meta-repo shape (deferred — confirm direction)

**Proposal:** `lnevo/hart` as documented hub; sibling repos (`LCOS_ESP32_MQTT_Client`, `sts-docker`, `sts-docker-helpers`); future `hart-ops` for Desktop car cards. Submodules under `external/` when P3 reopens.

- [ ] **Approve** meta-repo (no monorepo)
- [ ] **Prefer** monorepo: ___________

---

## D8 — PCBWay BOM (pipeline 10)

**Proposal:** Out of consolidation scope entirely.

- [ ] **Approve** exclude
- [ ] **Include** in manifest

---

## D9 — HTML browse site

**Proposal:** Self-contained `consolidation/index.html` + `html/` generated from wiki markdown; open locally in browser (no server required).

- [ ] **Approve**
- [ ] **Prefer** hosted wiki / other: ___________

---

## D10 — LCOS follow-ups (pipeline 9)

**Proposal:** Track in `cross-repo/lcos/TIER_B.md`; implement in sibling repo only after approval:

- Periodic event **125** after master RAM wipe
- USB serial ACK / pacing on Windows bridge

- [ ] **Approve** spec-only in consolidation for now
- [ ] **Prioritize** immediate LCOS repo work

---

## Approval record

**Superseded by [`DECISIONS_RECORDED.md`](DECISIONS_RECORDED.md)** — all approved 2026-08-31.

| Decision | Approved (Y/N) | Notes | Date |
|----------|----------------|-------|------|
| D1 | Y | consolidation/ only until promotion | 2026-08-31 |
| D2 | Y | Single SoR: public_name_map.csv; migrate off block_display | 2026-08-31 |
| D3 | Y | Tables merge order | 2026-08-31 |
| D4 | Y | Git wiring canonical | 2026-08-31 |
| D5 | Y | No eternal one-offs; unused-modules/ | 2026-08-31 |
| D6 | Y | Live signalmast roster; audit static refs | 2026-08-31 |
| D7 | Y | Meta-repo | 2026-08-31 |
| D8 | Y | BOM excluded | 2026-08-31 |
| D9 | Y | Local HTML now; Pi hosting later | 2026-08-31 |
| D10 | Y | LCOS working version as-is in review | 2026-08-31 |

# Good morning — start here

## 1. Open the browse portal

**Operator portal (crew / layout browse):** [`ops-portal/index.html`](ops-portal/index.html)

**Engineering consolidation desk (dark SoR / pipelines):**

```
/Users/lnevo/hart/consolidation/index.html
```

**Desktop/HART F-root (124 files):** [`html/archive/f-root-index.html`](html/archive/f-root-index.html) — browse, archive, and skip rows with local `file://` links.

**Product-owner review (Cursor canvases — open beside chat):**

- **Device map (D2):** [hart-device-map-d2-review.canvas.tsx](file:///Users/lnevo/.cursor/projects/Users-lnevo-hart/canvases/hart-device-map-d2-review.canvas.tsx) — live beans only, same as hart-device-map
- **D2 legacy / aliases:** [hart-device-map-d2-legacy.canvas.tsx](file:///Users/lnevo/.cursor/projects/Users-lnevo-hart/canvases/hart-device-map-d2-legacy.canvas.tsx) · CSV: [`sor/names/d2_legacy_match.csv`](sor/names/d2_legacy_match.csv)
- **Industry matrix (16):** [hart-industry-matrix.canvas.tsx](file:///Users/lnevo/.cursor/projects/Users-lnevo-hart/canvases/hart-industry-matrix.canvas.tsx)

Regenerate: `python3 consolidation/scripts/build_review_canvases.py`

Static HTML fallbacks: [`html/review/device-map.html`](html/review/device-map.html) · [`html/review/industry-matrix.html`](html/review/industry-matrix.html)

Categories: pipelines, CATS, MQTT, wiring, LCOS, audits, ADRs, archive, repos, backlog.

## 2. Build status

**Backlog:** [`BACKLOG.md`](BACKLOG.md)  
**Decisions:** [`DECISIONS_RECORDED.md`](DECISIONS_RECORDED.md) (D1–D12)  
**Next work:** [`NEXT_ROUND.md`](NEXT_ROUND.md)

## 3. Validators

```bash
cd /Users/lnevo/hart
bash consolidation/scripts/mirror_all_live.sh   # refresh mirrors + validate
python3 consolidation/scripts/audit_consolidation_paths.py  # path config check
# or validators only:
bash consolidation/validators/run_all.sh
```

**Path config:** copy [`env/consolidation.env.example`](env/consolidation.env.example) → `consolidation.env` and set `CONSOLIDATION_ROOT` when moving machines. All scripts source [`env/load_consolidation_env.sh`](env/load_consolidation_env.sh) automatically.

**Workspace map:** [`WORKSPACE.md`](WORKSPACE.md) · **Gaps:** [`audits/standalone-gaps.md`](audits/standalone-gaps.md)

Tier B manual checklist: [`validators/TIER_B_MANUAL_SMOKES.md`](validators/TIER_B_MANUAL_SMOKES.md) (reference during build)

## 4. Workspace rule

All build work under `consolidation/` — live sources and **`~/Desktop/HART/` read-only**.

Agent rule: `.cursor/rules/consolidation-workspace.mdc`

## 5. Tree at a glance

| Path | Contents |
|------|----------|
| `index.html` | Browse portal |
| `html/archive/f-root-index.html` | **F-root file browser** |
| `BACKLOG.md` | Build checklist |
| `manifest.yaml` | Pipelines + Tier A validators |
| `wiki/pipelines/` | Draft runbooks with SoR tables |
| `wiki/decisions/` | Consolidation ADRs |
| `wiki/archive/INDEX.md` | Desktop taxonomy |
| `wiki/REPOS.md` | Submodule recipe |
| `validators/` | Automated + Tier B smokes |
| `audits/` | Reports + validator logs |
| `sor/` | Names, wiring crosswalk, desktop CSV |
| `cross-repo/` | Submodule pins, hart-ops migration docs |
| `consolidation/external/` | Git submodules + runtime mirrors |
| `WORKSPACE.md` | Complete standalone tree map |

Rebuild portal: `python3 consolidation/scripts/build_site.py`

Regenerate publications (pipeline 15): `bash consolidation/scripts/rebuild_publications.sh`

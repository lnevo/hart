# Cutover — Desktop/HART slim

**Status:** Plan + inventory only; Desktop **unchanged**

## Target end state (future)

```
~/Desktop/HART/
  README.md          → links to hart git, hart-ops, STS, wiring
  (optional symlinks or removed subtrees after class C + archive cutover)
```

## Standalone consolidation data

- `sor/desktop/hart_root_inventory.csv` — root files C/D/E/F
- `sor/desktop/hart_subtree_inventory.csv` — class C subtrees
- `cutover/class-c-migration/` — Car Cards / Industries mirror plan
- `cutover/history-archive/` — F-root plan

## Prerequisites

1. Class C authoritative in hart-ops (standalone mirror ready ✓)
2. History archive disposition finalized
3. Class D root dupes verified against hart-ops publications

**No Desktop deletes during consolidation build.**

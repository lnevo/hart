# ADR — Tables XML merge order (draft)

**Status:** Draft — pending D3 in [`DECISIONS_PENDING.md`](../../DECISIONS_PENDING.md).

## Chain

```
tables/new_tables.xml          ← writable working source
        ↓ pipeline scripts (names, SML, heads, CTC, …)
jmri/layouts/hart/output/tables.xml   ← deploy bundle (LE + SML + CTC + Dispatcher)
        ↓ sync / export
jmri/layouts/hart/output/hart_prod.xml  ← standalone LE monitor (not full bundle)
```

## Rules

1. Never edit `tables/tables.xml` with tools.
2. Never copy `new_tables.xml` → `output/tables.xml` blindly (drops `<ctcdata>` / USS).
3. Never overwrite `output/tables.xml` with `hart_prod.xml`.
4. Regenerate USS `GUIObjects.xml` and CATS hold panels — do not string-replace.

## Consolidation scripts

Refactored copies live in `consolidation/scripts/`; promotion replaces live paths only after Tier A green.

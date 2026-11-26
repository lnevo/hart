# ops/hart-ops/industries

The OPSIG industries list, which moved to [`archive/data/ops-industries/industries.txt`](../../../archive/data/ops-industries/industries.txt) on 2026-11-25 (owner; nothing reads it). The industry routing matrix it once fed, its scripts and notes were retired as legacy on 2026-11-25 (owner) and are in [`archive/data/industry-routing/`](../../../archive/data/industry-routing/); nothing reads them.

## industries.txt

The OPSIG industries database as one tab-separated file, 10,377 rows, no header. Each row is one industry and one flow:

| Column | Holds |
|--------|-------|
| 1 | Year of the source (`50` = 1950, `2004`) |
| 2 | Company |
| 3 | Town |
| 4 | State |
| 5 | Railroad(s) serving it, as the source writes them (some carry a `*`) |
| 6 | `S` ships, `R` receives |
| 7 | Commodity |
| 8 | Product or STCC/SIC code |
| 9 | Volume, where the source gives one |
| 10 | Car type (2004 rows) or the source's short name (older rows) |

Subsets are filters of this file, not separate data. The three cut for the Pittsburgh to Washington, PA, line:

```bash
awk -F'\t' '$4=="PA"' archive/data/ops-industries/industries.txt                          # all Pennsylvania, 1,196 rows
awk -F'\t' '$4=="PA" && $5 ~ /B&O/' archive/data/ops-industries/industries.txt            # Pennsylvania on the B&O, 88 rows
awk -F'\t' '$3=="Washington" && $4=="PA"' archive/data/ops-industries/industries.txt      # Washington, PA, 3 rows
```


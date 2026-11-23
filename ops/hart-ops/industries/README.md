# ops/hart-ops/industries

The OPSIG industries list and the scripts that keep the industry routing matrix in step with it ([pipeline 16](../../../wiki/pipelines/industry-routing.md)).

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
awk -F'\t' '$4=="PA"' industries.txt                          # all Pennsylvania, 1,196 rows
awk -F'\t' '$4=="PA" && $5 ~ /B&O/' industries.txt            # Pennsylvania on the B&O, 88 rows
awk -F'\t' '$3=="Washington" && $4=="PA"' industries.txt      # Washington, PA, 3 rows
```

## Scripts and notes

- `validate_and_update_matrix.py`, `update_railroads.py`, `update_railroad_timelines_era.py`, `fix_railroad_timelines.py`: keep `HART_Industry_Routing_Matrix.xlsx` in step with the list.
- `Supplier_Customer_Analysis.md`: which suppliers and customers in the list fit the layout's industries.
- `SCRIPT_IMPROVEMENTS.md`: open ideas for the scripts.

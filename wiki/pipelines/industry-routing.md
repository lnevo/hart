# Pipeline 16 — Industry routing

Maintain the supplier/customer/commodity matrix that feeds waybills and STS seed.

**Status:** Live on Desktop. `~/Desktop/HART/Industries/`

## Inputs

- `industries.txt`
- Existing `HART_Industry_Routing_Matrix.xlsx`

## Outputs

- `HART_Industry_Routing_Matrix.xlsx` (validated rows: industry, flow, commodity, company, car type)

## Run

```bash
cd ~/Desktop/HART/Industries
python3 validate_and_update_matrix.py
# also: update_railroads.py, update_railroad_timelines_era.py, fix_railroad_timelines.py
```

Notes: `SCRIPT_IMPROVEMENTS.md`, `Supplier_Customer_Analysis.md`. Keep car types in the allowed set (Boxcar, Covered Hopper, Flatcar, Gondola, Hopper, Tank Car, Coil Car). Do not pair food companies with steel commodities.

This matrix is **not** in the hart git repo; sync conceptually with `HART_Spot_Waybills.csv` when lanes change.

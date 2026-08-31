# Signal / CATS CSV snapshots (pipelines 3–5, 8)

Read-only copies of live `cats/data/` SoR files. Refresh:

```bash
python3 consolidation/scripts/snapshot_live_sor.py
```

| File | Live source | Pipeline |
|------|-------------|----------|
| `signal_wiring.csv` | `cats/data/signal_wiring.csv` | 3 |
| `signal_head_plan.csv` | `cats/data/signal_head_plan.csv` | 3 |
| `signal_mast_plan.csv` | `cats/data/signal_mast_plan.csv` | 3 |
| `le_signal_boundaries.csv` | `cats/data/le_signal_boundaries.csv` | 4 |
| `occupancy_bindings.csv` | `cats/data/occupancy_bindings.csv` | 8 |

CATS device map: [`../cats/jmri_devices.csv`](../cats/jmri_devices.csv) (pipeline 5)

Manifest: [`../snapshot_manifest.csv`](../snapshot_manifest.csv)

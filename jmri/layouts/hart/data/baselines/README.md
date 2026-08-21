# Public-name rename baselines (pre-ADR-005)

Captured **2026-08-20** before executing the ADR-005 public equipment name rename. These files are read-only snapshots for regression detection; they do **not** apply any rename.

## Capture

```bash
python3 jmri/layouts/hart/scripts/capture_public_name_baseline.py
```

Defaults:

- Input: `jmri/layouts/hart/output/tables.xml`
- Output: this directory

Optional flags: `--tables PATH`, `--out PATH`.

## Sources

| File | Primary source |
|------|----------------|
| `hardware_identity.csv` | JMRI sensors, turnouts, signal heads/masts, blocks in `tables.xml` |
| `sml_pairs.csv` | Signal mast logic destination pairs |
| `sml_sections.csv` | Auto sections created from SML |
| `ctc_sidi.csv` | CTC code-button SIDI lever signals |
| `ctc_trl.csv` | CTC traffic-locking rules |
| `le_mast_bindings.csv` | Layout Editor turnout/point mast bindings |
| `block_sensors.csv` | Layout block → occupancy sensor map |
| `cats_bindings.csv` | CATS master panel block/signal bindings (best-effort) |
| `counts.txt` | Row counts per CSV + SHA-256 of `tables.xml` |
| `validate_le_signalling.txt` | Mini-discovery dests vs stored SML (PASS, 36 dests) |
| `audit_panel_contracts.txt` | working / deployment / standalone (PASS, drift 0) |
| `check_hart_phase02.txt` | Phase 0–2 (PASS) |
| `validate_cats_panel.txt` | Live masters PASS; stale HART.xml variants fail en-dash |

Also consulted (not written): `cats/panels/HART_Master.xml` (or `HART_Master_ABS.xml`), `cats/data/occupancy_bindings.csv`, `cats/data/le_signal_boundaries.csv`.

## After rename

1. Re-run the capture script into a scratch directory or replace these files intentionally.
2. Diff against this baseline:
   - **`hardware_identity.csv`**: `systemName` values must be **identical** (MQTT / internal ids are frozen).
   - **`userName` values** should match the `proposed` column in `jmri/layouts/hart/data/public_name_map.csv` where a rename applies; unchanged rows should match `current`.
   - **SML / CTC / LE / block / CATS** CSVs: public names in mast, section, destination, and block columns should follow the map; hardware columns (`occupancySensor`, `mqttAddr`, `sensorUserName`) must not change.
3. Compare `counts.txt` SHA-256 only when checking whether the Layout Editor agent touched `tables.xml` structure; user-name edits may not change the hash if element count is unchanged.

## Column notes

- **`hardware_identity` blocks**: `userName` is `blockUserName|occupancySensor` when an occupancy child exists.
- **`ctc_sidi`**: `ltr` / `rtl` are `SIDI_LeftRightTrafficSignals` / `SIDI_RightLeftTrafficSignals` signal names joined with `|`.
- **`ctc_trl`**: `occupancySensors` are `OccupancyExternalSensors` joined with `|`.
- **`cats_bindings`**: parsed from CATS `SEC_EDGE` blocks with `IOSPEC USER_NAME` / `DECADDR`; `secsignal` is sibling signal label text when present. Duplicate edges are deduplicated; some blocks appear on both sides of a section without a signal.

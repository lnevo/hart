# JMRI prefixes for CATS Designer (HART)

From `cats/data/jmri_devices.csv` — enable these connection prefixes in Designer so MQTT devices resolve:

| Prefix | Type | Example |
|--------|------|---------|
| M2S | Sensor | occupancy / feedback (`Block 4-2`, Switch FB…) |
| M2T | Turnout | `M2T408` = Switch 1 |
| IS / ISIS | Sensor | mostly purged; keep `ISCLOCKRUNNING` only |
| IT | Turnout | crossover / internal legs if still used |
| IF$vsm / MQTT masts | Signal | defer until signal ownership decided |

Internal Armstrong samples use `IS`/`IT`. HART live plant uses **M2S/M2T** user+system names — bind by **userName** from the occupancy/turnout CSVs whenever Designer allows.

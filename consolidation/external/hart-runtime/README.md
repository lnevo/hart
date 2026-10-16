# HART layout ops mirror (not a git submodule)

Read-only copy of live `hart/` layout operations tree for **standalone consolidation**.

Refresh:

```bash
bash consolidation/scripts/mirror_hart_runtime.sh
```

## Contents (~55 MB)

| Path | Role |
|------|------|
| `tables/new_tables.xml` | Writable tables chain source |
| `jmri/layouts/hart/` | output, data, dispatcher, ctc, scripts |
| `jmri/scripts/` | phase02, MQTT publisher |
| `cats/data/`, `panels/`, `scripts/` | CATS pipeline artifacts |
| `docs/wiring/` | Wiring doc pack |

Validators use `HART_LIVE_ROOT` → this directory when present.

## Git

Runtime tree is **gitignored**. Only this README and `MIRROR_MANIFEST.txt` are tracked.

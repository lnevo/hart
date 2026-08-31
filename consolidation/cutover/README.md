# Cutover projects — standalone consolidation mirrors

Each project below is documented and **manifested in consolidation only**. Live `hart/`, `~/Desktop/HART/`, and layout hosts are **not modified** by these artifacts.

When the consolidation tree becomes authoritative, cutover executes from these standalone plans — not by editing files in place today.

| Project | Manifest | Consolidation standalone copy |
|---------|----------|------------------------------|
| [Class C migration](class-c-migration/README.md) | [`manifest.yaml`](class-c-migration/manifest.yaml) | `external/hart-ops/` |
| [Names D2 batch](names-d2/README.md) | [`manifest.yaml`](names-d2/manifest.yaml) | `sor/names/` |
| [History archive](history-archive/README.md) | [`manifest.yaml`](history-archive/manifest.yaml) | `sor/desktop/class_f_ingest_manifest.csv` + F-root browse |
| [Desktop slim](desktop-slim/README.md) | [`manifest.yaml`](desktop-slim/manifest.yaml) | inventory CSVs only |
| [Layout hosts](layout-hosts/README.md) | [`manifest.yaml`](layout-hosts/manifest.yaml) | docs + Tier B checklist |
| STS Docker + data | [`../external/sts-docker-data/README.md`](../external/sts-docker-data/README.md) | `external/sts-docker/` + `external/sts-docker-data/` mirror |

**Inventory:** [`sor/desktop/`](../sor/desktop/) · **Central SoR:** [`sor/CENTRAL_SOR.md`](../sor/CENTRAL_SOR.md)

# STS runtime data mirror (not a git submodule)

Local copy of live STS Docker bind-mount volumes for **standalone consolidation cutover**.

| Path | Live source | Container mount |
|------|-------------|-----------------|
| `backups/` | `~/sts/sts-backups` | `/var/www/html/sts/backups` |
| `database/` | `~/sts/sts-database` | `/var/lib/mysql` (via `database/docker/sts/db`) |
| `Rolling Stock photos/` | `~/sts/sts-images` | `/var/www/html/sts/ImageStore/DB_Images/RollingStock/` |

## Refresh (read-only rsync from live)

```bash
bash consolidation/scripts/mirror_sts_docker_data.sh
```

Override sources:

```bash
STS_BACKUPS=~/sts/sts-backups STS_DATABASE=~/sts/sts-database STS_IMAGES=~/sts/sts-images \
  bash consolidation/scripts/mirror_sts_docker_data.sh
```

## Standalone Docker (consolidation workspace)

From repo root:

```bash
cd consolidation/external/sts-docker
docker compose -f docker-compose.yml -f ../sts-docker-data/docker-compose.consolidation.yml --profile build up -d --build
```

Uses `../sts-docker-data/` paths — **does not touch** `~/sts/*`.

## Git

This directory is **gitignored** (runtime data). Only `README.md` and `MIRROR_MANIFEST.txt` pattern are tracked via README; manifest is written by mirror script.

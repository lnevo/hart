# STS runtime data mirror (consolidation)

Mirrors live `~/sts/*` into `consolidation/external/sts-docker-data/`:

| Consolidation dir | Live source | Container mount |
|-------------------|-------------|-----------------|
| `backups/` | `~/sts/sts-backups` | `/var/www/html/sts/backups` |
| `images/` | `~/sts/sts-images` | `.../ImageStore/DB_Images/RollingStock/` |
| `database/` | `~/sts/sts-database` | `/var/lib/mysql` |

Configure mirror sources in [`../../env/consolidation.env.example`](../../env/consolidation.env.example).

## Refresh

```bash
bash consolidation/scripts/mirror_sts_docker_data.sh
```

Rsyncs live data and runs `refresh_sts_docker_compose.sh` to write literal bind paths into [`../sts-docker/docker-compose.yml`](../sts-docker/docker-compose.yml).

## Run

```bash
cd consolidation/external/sts-docker
docker compose up -d --build
```

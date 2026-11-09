# STS data

The live STS data. `tools/ops/refresh_sts_docker_compose.sh` renders `../sts-docker/docker-compose.yml` with mounts relative to it.

| Folder | Container mount |
|---|---|
| `database/docker/sts/db` | MariaDB data directory |
| `backups/` | `/var/www/html/sts/backups` |
| `Rolling Stock photos/` | STS rolling stock images |

`database/` and `backups/` are gitignored. The old `~/sts` copy was retired on 2026-11-09 (ADR-007).

```bash
bash tools/ops/sts_compose.sh up -d
```

# STS data

STS data for the Mac (UAT) stack. `../sts-docker/docker-compose.yml` mounts these folders by relative path. The live STS runs on the Pi (ADR-020).

| Folder | Container mount |
|---|---|
| `database/docker/sts/db` | MariaDB data directory |
| `backups/` | `/var/www/html/sts/backups` |
| `Rolling Stock photos/` | STS rolling stock images |

`database/` and `backups/` are gitignored. The old `~/sts` copy was retired on 2026-11-09 (ADR-007).

```bash
(cd external/sts-docker && docker compose up -d)
```

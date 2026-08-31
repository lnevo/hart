# STS package (consolidation)

**Runtime:** [`../../external/sts-docker/`](../../external/sts-docker/)  
**Helpers:** [`../../external/sts-helpers/`](../../external/sts-helpers/)  
**Data mirror:** [`../../external/sts-docker-data/`](../../external/sts-docker-data/)

## Start (lab)

```bash
bash consolidation/scripts/mirror_sts_docker_data.sh
cd consolidation/external/sts-docker
docker compose -f docker-compose.yml \
  -f ../sts-docker-data/docker-compose.consolidation.yml \
  --profile build up -d --build
# http://localhost:8980/sts/
```

## Seed / sessions (hart-ops wrappers)

```bash
cd consolidation/external/hart-ops
./bin/apply_hart_seed.sh --generate --merge-fleet
./bin/begin_session.sh --run-stg-scully --switchlists
```

Backups resolve from `../sts-docker-data/backups/` when sts-helpers paths are configured.

Runbook: [`../../wiki/pipelines/sts.md`](../../wiki/pipelines/sts.md)

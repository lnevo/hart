# STS package (consolidation)

**Runtime:** [`../../external/sts-docker/`](../../external/sts-docker/)  
**Helpers:** [`../../external/sts-helpers/`](../../external/sts-helpers/)  
**Data:** [`../../external/sts-docker-data/`](../../external/sts-docker-data/)

## Setup

```bash
cp consolidation/env/consolidation.env.example consolidation/env/consolidation.env   # once
bash consolidation/scripts/mirror_sts_docker_data.sh
```

Pipeline script [`refresh_sts_docker_compose.sh`](../../scripts/refresh_sts_docker_compose.sh) writes literal bind paths into `docker-compose.yml` (`backups/`, `images/`, `database/` under `sts-docker-data/`).

## Run

```bash
cd consolidation/external/sts-docker
docker compose up -d --build
```

## Sessions

```bash
source consolidation/env/load_consolidation_env.sh
cd "$STS_HELPERS_ROOT"
./bin/begin_session.sh --run-stg-scully --switchlists
```

Runbook: [`../../wiki/pipelines/sts.md`](../../wiki/pipelines/sts.md)

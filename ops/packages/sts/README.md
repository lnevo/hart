# STS package

**Runtime:** [`../../external/sts-docker/`](../../../external/sts-docker)  
**Helpers:** [`../../external/sts-helpers/`](../../../external/sts-helpers)  
**Data:** [`../../external/sts-docker-data/`](../../external/sts-docker-data/)

## Setup

```bash
cp tools/env/hart.env.example tools/env/hart.env   # once
```

Pipeline script [`refresh_sts_docker_compose.sh`](../../../tools/ops/refresh_sts_docker_compose.sh) writes literal bind paths into `docker-compose.yml` (`backups/`, `images/`, `database/` under `sts-docker-data/`).

## Run

```bash
cd external/sts-docker
docker compose up -d --build
```

## Sessions

```bash
source tools/env/load_env.sh
cd "$STS_HELPERS_ROOT"
./bin/begin_session.sh --run-stg-scully --switchlists
```

Runbook: [`../../wiki/pipelines/sts.md`](../../../wiki/pipelines/sts.md)

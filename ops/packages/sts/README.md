# STS package

**Runtime:** [`../../external/sts-docker/`](../../../external/sts-docker)  
**Helpers:** [`../../external/sts-helpers/`](../../../external/sts-helpers)  
**Data:** [`../../external/sts-docker-data/`](../../../external/sts-docker-data/)

## Setup

```bash
cp tools/env/hart.env.example tools/env/hart.env   # once
```

The Mac (UAT) stack is `external/sts-docker/docker-compose.yml` as committed in sts-docker; its mounts are relative (`../sts-docker-data`, `../sts-plugins/plugins`), so nothing is rendered.

## Run

```bash
(cd external/sts-docker && docker compose up -d --build)
```

## Sessions

```bash
source tools/env/load_env.sh
cd "$STS_HELPERS_ROOT"
./bin/begin_session.sh --run-stg-scully --switchlists
```

Runbook: [`../../wiki/pipelines/sts.md`](../../../wiki/pipelines/sts.md)

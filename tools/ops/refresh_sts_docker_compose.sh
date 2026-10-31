#!/usr/bin/env bash
# Render external/sts-docker/docker-compose.yml with bind paths relative to it, so a
# move of external/ needs no re-render.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../env/load_env.sh
source "${SCRIPT_DIR}/../env/load_env.sh"

TEMPLATE="${SCRIPT_DIR}/templates/sts-docker-compose.yml"
OUT="${STS_DOCKER_ROOT}/docker-compose.yml"
DB_MOUNT="${STS_DATABASE_DIR}/docker/sts/db"

mkdir -p "${STS_BACKUPS_DIR}" "${STS_DATABASE_DIR}" "${STS_IMAGES_DIR}" "${DB_MOUNT}"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "Missing template: $TEMPLATE" >&2
  exit 1
fi

python3 - "$TEMPLATE" "$OUT" "$STS_BACKUPS_DIR" "$STS_IMAGES_DIR" "$DB_MOUNT" <<'PY'
import os
import sys
from pathlib import Path

template_path, out_path, backups, images, db_mount = sys.argv[1:6]
text = Path(template_path).read_text(encoding="utf-8")
compose_dir = Path(out_path).resolve().parent


def relative(path: str) -> str:
    return os.path.relpath(path, compose_dir)


replacements = {
    "@STS_BACKUPS_DIR@": relative(backups),
    "@STS_IMAGES_DIR@": relative(images),
    "@STS_DATABASE_DB@": relative(db_mount),
}
for token, value in replacements.items():
    text = text.replace(token, value)
Path(out_path).write_text(text, encoding="utf-8")
PY

echo "Wrote ${OUT}"
echo "  backups: ${STS_BACKUPS_DIR}"
echo "  images:  ${STS_IMAGES_DIR}"
echo "  db:      ${DB_MOUNT}"

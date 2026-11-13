#!/usr/bin/env bash
# Update the live STS on the Pi (ADR-020): git pull sts-docker and sts-plugins
# there, then rebuild and restart the release stack. Nothing is copied into a
# running container. Data in ~/sts/sts-docker-data is left alone.
#
#   tools/hosts/pi_sts_update.sh            pull and rebuild
#   tools/hosts/pi_sts_update.sh --status   show commits and containers only
set -euo pipefail

source "$(cd "$(dirname "$0")/../env" && pwd)/load_env.sh"  # hosts: environment, hart.env, default
HOST="${PI_HOST:-$HART_PI_SSH}"  # PI_HOST first, as before
MODE="${1:-update}"

case "$MODE" in
  update|--status) ;;
  *) echo "usage: $0 [--status]" >&2; exit 2 ;;
esac

# shellcheck disable=SC2087  # expand MODE locally on purpose
ssh "$HOST" bash -s <<EOF
set -euo pipefail
cd ~/sts/sts-docker
C="docker compose -f docker-compose.yml -f docker-compose.release.yml --profile build"
if [ "$MODE" = update ]; then
  git -C ../sts-plugins pull --ff-only -q
  git pull --ff-only -q
  \$C up -d --build
fi
echo "sts-docker  \$(git log --oneline -1)"
echo "sts-plugins \$(git -C ../sts-plugins log --oneline -1)"
docker ps --filter name=sts-docker --format '{{.Names}}  {{.Status}}'
# The web container answers within a minute of a restart.
code=000
for _ in \$(seq 1 30); do
  code=\$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8980/sts/ || true)
  [ "\$code" = 200 ] && break
  sleep 2
done
echo "STS http \$code"
[ "\$code" = 200 ]
EOF

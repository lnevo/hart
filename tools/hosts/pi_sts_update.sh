#!/usr/bin/env bash
# Update the live STS on the Pi (ADR-020): git pull sts-docker and sts-plugins
# there, then rebuild and restart the release stack. Nothing is copied into a
# running container. Data in ~/sts/sts-docker-data is left alone.
#
#   tools/hosts/pi_sts_update.sh            pull and rebuild
#   tools/hosts/pi_sts_update.sh --status   show commits and containers only
set -euo pipefail

HOST="${PI_HOST:-pi}"
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
EOF

curl -s -m 10 -o /dev/null -w "STS http %{http_code}\n" "http://10.0.0.150:8980/sts/" || echo "STS not answering"

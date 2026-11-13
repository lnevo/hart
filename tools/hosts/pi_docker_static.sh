#!/usr/bin/env bash
# Install or update Docker on the Pi from Docker's static 64-bit binaries
# (ADR-020). The Pi runs 32-bit Raspberry Pi OS on a 64-bit kernel, so apt's
# Docker is 32-bit, and MariaDB publishes no 32-bit ARM image. The static
# aarch64 builds need no 64-bit libraries and leave the 32-bit system alone.
#
#   tools/hosts/pi_docker_static.sh            install or update to the versions below
#   tools/hosts/pi_docker_static.sh --status   show what is installed
#
# Updating: change the versions, run again. Containers with restart policies
# come back when dockerd restarts. Images and volumes are kept. Docker
# publishes no checksum for the static tarball; it is downloaded and unpacked
# before the running daemon is stopped.
set -euo pipefail

source "$(cd "$(dirname "$0")/../env" && pwd)/load_env.sh"  # hosts: environment, hart.env, default
HOST="${PI_HOST:-$HART_PI_SSH}"  # PI_HOST first, as before
DOCKER_VERSION="${DOCKER_VERSION:-29.9.3}"
COMPOSE_VERSION="${COMPOSE_VERSION:-v5.7.1}"
BUILDX_VERSION="${BUILDX_VERSION:-v0.39.0}"
MODE="${1:-install}"

case "$MODE" in
  install|--status) ;;
  *) echo "usage: $0 [--status]" >&2; exit 2 ;;
esac

if [ "$MODE" = --status ]; then
  ssh "$HOST" 'docker version --format "client {{.Client.Version}} {{.Client.Arch}} / server {{.Server.Version}} {{.Server.Arch}}"; docker compose version; docker buildx version; systemctl is-active containerd docker'
  exit 0
fi

# shellcheck disable=SC2087  # versions expand locally on purpose
ssh "$HOST" sudo bash -s <<EOF
set -euo pipefail
[ "\$(uname -m)" = aarch64 ] || { echo "kernel is not aarch64" >&2; exit 1; }
tmp=\$(mktemp -d); trap 'rm -rf "\$tmp"' EXIT
cd "\$tmp"

# Download everything before stopping anything.
curl -fsSLo docker.tgz "https://download.docker.com/linux/static/stable/aarch64/docker-${DOCKER_VERSION}.tgz"
curl -fsSLo docker-compose-linux-aarch64 "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-aarch64"
curl -fsSLo docker-compose-linux-aarch64.sha256 "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-aarch64.sha256"
sha256sum -c docker-compose-linux-aarch64.sha256
curl -fsSLo "buildx-${BUILDX_VERSION}.linux-arm64" "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-arm64"
curl -fsSLo checksums.txt "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/checksums.txt"
grep " \*\?buildx-${BUILDX_VERSION}.linux-arm64\$" checksums.txt | sed 's/ \*/  /' | sha256sum -c -
tar -xzf docker.tgz

systemctl stop docker.socket docker containerd 2>/dev/null || true
# apt's 32-bit Docker (Docker's or Debian's packages), if present, goes first so
# its binaries and units cannot shadow these. Images and volumes stay; armhf
# images left by it can be removed with docker image prune -a.
apt_pkgs=""
for p in docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras docker.io docker-compose containerd runc; do
  if dpkg -s "\$p" >/dev/null 2>&1; then apt_pkgs="\$apt_pkgs \$p"; fi
done
if [ -n "\$apt_pkgs" ]; then
  DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq \$apt_pkgs >/dev/null
  rm -f /etc/apt/sources.list.d/docker.list /etc/apt/keyrings/docker.asc
fi

install -m 0755 docker/* /usr/local/bin/
install -d /usr/local/lib/docker/cli-plugins
install -m 0755 docker-compose-linux-aarch64 /usr/local/lib/docker/cli-plugins/docker-compose
install -m 0755 "buildx-${BUILDX_VERSION}.linux-arm64" /usr/local/lib/docker/cli-plugins/docker-buildx
groupadd -f docker
usermod -aG docker "\${SUDO_USER:-pi}"

cat > /etc/systemd/system/containerd.service <<'UNIT'
[Unit]
Description=containerd container runtime
After=network.target local-fs.target

[Service]
ExecStartPre=-/sbin/modprobe overlay
ExecStart=/usr/local/bin/containerd
Type=notify
Delegate=yes
KillMode=process
Restart=always
RestartSec=5
LimitNPROC=infinity
LimitCORE=infinity
TasksMax=infinity
OOMScoreAdjust=-999

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/docker.socket <<'UNIT'
[Unit]
Description=Docker Socket for the API

[Socket]
ListenStream=/run/docker.sock
SocketMode=0660
SocketUser=root
SocketGroup=docker

[Install]
WantedBy=sockets.target
UNIT

cat > /etc/systemd/system/docker.service <<'UNIT'
[Unit]
Description=Docker Application Container Engine
After=network-online.target containerd.service docker.socket
Wants=network-online.target containerd.service
Requires=docker.socket

[Service]
Type=notify
ExecStart=/usr/local/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
ExecReload=/bin/kill -s HUP \$MAINPID
TimeoutStartSec=0
Restart=always
RestartSec=2
LimitNOFILE=infinity
LimitNPROC=infinity
TasksMax=infinity
Delegate=yes
KillMode=process
OOMScoreAdjust=-500

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now containerd docker.socket docker >/dev/null 2>&1
systemctl restart containerd docker
docker version --format "docker {{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}"
docker compose version
docker buildx version
EOF

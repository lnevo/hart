#!/usr/bin/env bash
# Resolve repo paths and host settings for shell scripts. Source from tools/ops/*.sh:
#   source "$(dirname "$0")/../env/load_env.sh"
# Overrides: copy hart.env.example to hart.env, or export variables before sourcing.

_hart_env_loaded="${_hart_env_loaded:-}"
if [[ -n "$_hart_env_loaded" ]]; then
  return 0 2>/dev/null || exit 0
fi
_hart_env_loaded=1

_env_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export HART_REPO_ROOT="${HART_REPO_ROOT:-$(cd "${_env_dir}/../.." && pwd)}"

# Host settings, read in the same order as tools/ops/lib/hart_hosts.py: the environment
# first, then hart.env, then the default. Older names follow the new one in each list.
_hart_host_names="HART_MQTT_BROKER MQTT_HOST HART_MQTT_HOST HART_MQTT_PORT HART_JMRI_JSON JMRI_JSON
  HART_PI_SSH HART_PI_USERFILES HART_WIN_SSH HART_WIN_SSH_PORT HART_WIN_USERFILES"
for _n in $_hart_host_names; do
  eval "_hart_env_${_n}=\"\${${_n}:-}\""
done

_env_file="${HART_ENV_FILE:-${_env_dir}/hart.env}"
if [[ -f "$_env_file" ]]; then
  # Callers run under set -u; a hart.env line may name a variable that is only set below
  # (STS_BACKUPS_DIR=$STS_DATA_ROOT/backups), so read the file with nounset off.
  case $- in *u*) _hart_nounset=1; set +u ;; *) _hart_nounset= ;; esac
  # shellcheck disable=SC1090
  source "$_env_file"
  [[ -z "$_hart_nounset" ]] || set -u
  unset _hart_nounset
fi

# First non-empty value: each name as the environment had it, then as hart.env set it, then $1.
_hart_pick() {
  local default="$1" n v
  shift
  for n in "$@"; do
    eval "v=\"\${_hart_env_${n}:-}\""
    [[ -n "$v" ]] && { printf '%s' "$v"; return; }
  done
  for n in "$@"; do
    eval "v=\"\${${n}:-}\""
    [[ -n "$v" ]] && { printf '%s' "$v"; return; }
  done
  printf '%s' "$default"
}

# The Pi (RPi-JMRI.local) runs Mosquitto, JMRI and the live STS. On the Pi itself the broker is 127.0.0.1.
export HART_MQTT_BROKER="$(_hart_pick 10.0.0.150 HART_MQTT_BROKER MQTT_HOST HART_MQTT_HOST)"
export HART_MQTT_PORT="$(_hart_pick 1883 HART_MQTT_PORT)"
export HART_JMRI_JSON="$(_hart_pick http://10.0.0.150:12080/json HART_JMRI_JSON JMRI_JSON)"
# ssh to the Pi: a host or ~/.ssh/config alias. PI_HOST is not read here: only the STS and
# Docker helpers honoured it before, and they still put it first themselves.
export HART_PI_SSH="$(_hart_pick pi HART_PI_SSH)"
export HART_PI_USERFILES="$(_hart_pick /home/pi/JMRI_UserFiles HART_PI_USERFILES)"
# ssh to Windows (OpenSSH on port 2222). minipc-e5h6x.local is never the broker.
export HART_WIN_SSH="$(_hart_pick lnevo@minipc-e5h6x.local HART_WIN_SSH)"
export HART_WIN_SSH_PORT="$(_hart_pick 2222 HART_WIN_SSH_PORT)"
export HART_WIN_USERFILES="$(_hart_pick C:/Users/lnevo/JMRI_UserFiles HART_WIN_USERFILES)"
for _n in $_hart_host_names; do
  unset "_hart_env_${_n}"
done
unset _n _hart_host_names

export HART_RUNTIME_ROOT="${HART_RUNTIME_ROOT:-${HART_REPO_ROOT}}"
export HART_LIVE_ROOT="${HART_LIVE_ROOT:-${HART_REPO_ROOT}}"
export HART_OPS_ROOT="${HART_OPS_ROOT:-${HART_REPO_ROOT}/ops/hart-ops}"
export LCOS_BRIDGE_ROOT="${LCOS_BRIDGE_ROOT:-${HART_REPO_ROOT}/external/lcos-bridge}"
export STS_DOCKER_ROOT="${STS_DOCKER_ROOT:-${HART_REPO_ROOT}/external/sts-docker}"
export STS_HELPERS_ROOT="${STS_HELPERS_ROOT:-${HART_REPO_ROOT}/external/sts-helpers}"
export STS_DATA_ROOT="${STS_DATA_ROOT:-${HART_REPO_ROOT}/external/sts-docker-data}"

export STS_BACKUPS_DIR="${STS_BACKUPS_DIR:-${STS_DATA_ROOT}/backups}"
export STS_DATABASE_DIR="${STS_DATABASE_DIR:-${STS_DATA_ROOT}/database}"
export STS_IMAGES_DIR="${STS_IMAGES_DIR:-${STS_DATA_ROOT}/Rolling Stock photos}"

export HART_CAR_CARDS_ROOT="${HART_CAR_CARDS_ROOT:-${HART_REPO_ROOT}/ops/car-cards}"
export HART_CAR_IMAGES_FINAL="${HART_CAR_IMAGES_FINAL:-${HART_CAR_CARDS_ROOT}/car-images/CarImagesFinal}"
export HART_STS_HELPERS="${HART_STS_HELPERS:-${STS_HELPERS_ROOT}}"
export STS_DOCKER="${STS_DOCKER:-${STS_DOCKER_ROOT}}"
export COMPOSE_PROFILES="${COMPOSE_PROFILES:-build}"
export JMRI_LAYOUT="${JMRI_LAYOUT:-hart}"

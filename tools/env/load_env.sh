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

# Host settings, read in the same order as tools/hartlib/src/hartlib/hosts.py: the environment
# first, then hart.env, then defaults.env. Older names follow the new one in each list.
_hart_host_names="HART_MQTT_BROKER MQTT_HOST HART_MQTT_HOST HART_MQTT_PORT HART_JMRI_JSON JMRI_JSON
  HART_PI_SSH HART_PI_USERFILES HART_PI_WEB_HOST HART_WIN_SSH HART_WIN_SSH_PORT HART_WIN_USERFILES"
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

# Defaults: the one copy is defaults.env beside this file (hartlib/hosts.py reads it too).
_hart_defaults="${_env_dir}/defaults.env"
if [[ ! -f "$_hart_defaults" ]]; then
  echo "load_env.sh: missing $_hart_defaults" >&2
  unset _hart_env_loaded  # so a later source, once the file is back, loads everything
  return 1 2>/dev/null || exit 1
fi
# Plain KEY=VALUE lines only (tools/hosts/tests/test_load_env.py holds the file to that, so
# hartlib.hosts reads the same values); a trailing CR or blank is dropped all the same.
_hart_def_keys=""
while IFS= read -r _line || [[ -n "$_line" ]]; do
  _line="${_line%$'\r'}"
  case "$_line" in ''|'#'*) continue ;; esac
  _key="${_line%%=*}"
  [[ "$_key" =~ ^[A-Z_][A-Z0-9_]*$ ]] || continue
  _val="${_line#*=}"
  _val="${_val%"${_val##*[![:space:]]}"}"
  printf -v "_hart_def_${_key}" '%s' "$_val"
  _hart_def_keys="$_hart_def_keys $_key"
done < "$_hart_defaults"
unset _line _key _val
# Every exported host name needs a default; refuse rather than export an empty value.
for _n in HART_MQTT_BROKER HART_MQTT_PORT HART_JMRI_JSON HART_PI_SSH HART_PI_USERFILES HART_PI_WEB_HOST \
          HART_WIN_SSH HART_WIN_SSH_PORT HART_WIN_USERFILES; do
  eval "_v=\"\${_hart_def_${_n}:-}\""
  if [[ -z "$_v" ]]; then
    echo "load_env.sh: $_n has no default in $_hart_defaults" >&2
    for _k in $_hart_def_keys; do unset "_hart_def_${_k}"; done
    unset _hart_env_loaded _hart_def_keys _v _k
    return 1 2>/dev/null || exit 1
  fi
done
unset _v
_hart_default() {
  eval "printf '%s' \"\${_hart_def_$1}\""
}

# Older names follow the new one: MQTT_HOST and HART_MQTT_HOST for the broker, JMRI_JSON.
# PI_HOST is not read: only the STS and Docker helpers honoured it, and they put it first themselves.
export HART_MQTT_BROKER="$(_hart_pick "$(_hart_default HART_MQTT_BROKER)" HART_MQTT_BROKER MQTT_HOST HART_MQTT_HOST)"
export HART_MQTT_PORT="$(_hart_pick "$(_hart_default HART_MQTT_PORT)" HART_MQTT_PORT)"
export HART_JMRI_JSON="$(_hart_pick "$(_hart_default HART_JMRI_JSON)" HART_JMRI_JSON JMRI_JSON)"
export HART_PI_SSH="$(_hart_pick "$(_hart_default HART_PI_SSH)" HART_PI_SSH)"
export HART_PI_USERFILES="$(_hart_pick "$(_hart_default HART_PI_USERFILES)" HART_PI_USERFILES)"
export HART_PI_WEB_HOST="$(_hart_pick "$(_hart_default HART_PI_WEB_HOST)" HART_PI_WEB_HOST)"
export HART_WIN_SSH="$(_hart_pick "$(_hart_default HART_WIN_SSH)" HART_WIN_SSH)"
export HART_WIN_SSH_PORT="$(_hart_pick "$(_hart_default HART_WIN_SSH_PORT)" HART_WIN_SSH_PORT)"
export HART_WIN_USERFILES="$(_hart_pick "$(_hart_default HART_WIN_USERFILES)" HART_WIN_USERFILES)"
for _k in $_hart_def_keys; do
  unset "_hart_def_${_k}"
done
unset -f _hart_default
unset _k _hart_def_keys
unset _hart_defaults
for _n in $_hart_host_names; do
  unset "_hart_env_${_n}"
done
# Kept (not exported) so tools/hosts/redeploy_commit.sh passes exactly these to an old commit.
HART_HOST_NAMES="$_hart_host_names"
unset _n _hart_host_names

# The JMRI profile PanelPro and CATS run on the Pi ("<name>.<id>"; its folder is ~/.jmri/<name>.jmri). The Pi's
# own launch_cats.sh runs without this repo and keeps a copy (tools/hosts/tests/test_host_copies.py).
export HART_PI_PROFILE="${HART_PI_PROFILE:-TCS_MQTT.3f32a166}"

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
# One layout (hartlib.paths pins it); a stale value from an old archive README is replaced.
if [[ -n "${JMRI_LAYOUT:-}" && "$JMRI_LAYOUT" != hart ]]; then
  echo "load_env.sh: JMRI_LAYOUT=$JMRI_LAYOUT replaced by hart (the only layout)" >&2
fi
export JMRI_LAYOUT=hart

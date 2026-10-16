#!/usr/bin/env bash
# Resolve consolidation workspace paths for shell scripts.
# Source from any consolidation/scripts/*.sh:
#   source "$(dirname "$0")/../env/load_consolidation_env.sh"
#
# Override: copy consolidation.env.example → consolidation.env and edit CONSOLIDATION_ROOT
# or export variables before sourcing.

_consolidation_env_loaded="${_consolidation_env_loaded:-}"
if [[ -n "$_consolidation_env_loaded" ]]; then
  return 0 2>/dev/null || exit 0
fi
_consolidation_env_loaded=1

# Auto-detect consolidation root from this file unless preset.
if [[ -z "${CONSOLIDATION_ROOT:-}" ]]; then
  _env_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
  CONSOLIDATION_ROOT="$(cd "${_env_dir}/.." && pwd)"
fi
export CONSOLIDATION_ROOT

# User overrides (optional local file — not committed).
_env_file="${CONSOLIDATION_ENV_FILE:-${CONSOLIDATION_ROOT}/env/consolidation.env}"
if [[ -f "$_env_file" ]]; then
  # shellcheck disable=SC1090
  source "$_env_file"
fi

_hart_repo="${HART_REPO_ROOT:-$(cd "${CONSOLIDATION_ROOT}/.." && pwd)}"
export HART_REPO_ROOT="$_hart_repo"

# --- Consolidation runtime paths (defaults under CONSOLIDATION_ROOT) ---
export HART_RUNTIME_ROOT="${HART_RUNTIME_ROOT:-${CONSOLIDATION_ROOT}/external/hart-runtime}"
export HART_LIVE_ROOT="${HART_LIVE_ROOT:-${HART_RUNTIME_ROOT}}"
export DESKTOP_DATA_ROOT="${DESKTOP_DATA_ROOT:-${CONSOLIDATION_ROOT}/external/desktop-data}"
export HART_OPS_ROOT="${HART_OPS_ROOT:-${CONSOLIDATION_ROOT}/external/hart-ops}"
export LCOS_BRIDGE_ROOT="${LCOS_BRIDGE_ROOT:-${CONSOLIDATION_ROOT}/external/lcos-bridge}"
export STS_DOCKER_ROOT="${STS_DOCKER_ROOT:-${CONSOLIDATION_ROOT}/external/sts-docker}"
export STS_HELPERS_ROOT="${STS_HELPERS_ROOT:-${CONSOLIDATION_ROOT}/external/sts-helpers}"
export STS_DATA_ROOT="${STS_DATA_ROOT:-${CONSOLIDATION_ROOT}/external/sts-docker-data}"

export STS_BACKUPS_DIR="${STS_BACKUPS_DIR:-${STS_DATA_ROOT}/backups}"
export STS_DATABASE_DIR="${STS_DATABASE_DIR:-${STS_DATA_ROOT}/database}"
export STS_IMAGES_DIR="${STS_IMAGES_DIR:-${STS_DATA_ROOT}/images}"

export HART_CAR_CARDS_ROOT="${HART_CAR_CARDS_ROOT:-${DESKTOP_DATA_ROOT}/car-cards}"
export HART_CAR_IMAGES_FINAL="${HART_CAR_IMAGES_FINAL:-${DESKTOP_DATA_ROOT}/car-images/CarImagesFinal}"
export HART_STS_HELPERS="${HART_STS_HELPERS:-${STS_HELPERS_ROOT}}"

export STS_DOCKER="${STS_DOCKER:-${STS_DOCKER_ROOT}}"

export COMPOSE_PROFILES="${COMPOSE_PROFILES:-build}"

# --- Mirror sources (live read-only; change when moving machines) ---
export HART_MIRROR_SRC="${HART_MIRROR_SRC:-${HART_REPO_ROOT}}"
export DESKTOP_HART="${DESKTOP_HART:-${HOME}/Desktop/HART}"
export MIRROR_STS_BACKUPS="${MIRROR_STS_BACKUPS:-${STS_BACKUPS:-${HOME}/sts/sts-backups}}"
export MIRROR_STS_DATABASE="${MIRROR_STS_DATABASE:-${STS_DATABASE:-${HOME}/sts/sts-database}}"
export MIRROR_STS_IMAGES="${MIRROR_STS_IMAGES:-${STS_IMAGES:-${HOME}/sts/sts-images}}"

# Legacy aliases used by mirror scripts.
export STS_BACKUPS="${MIRROR_STS_BACKUPS}"
export STS_DATABASE="${MIRROR_STS_DATABASE}"
export STS_IMAGES="${MIRROR_STS_IMAGES}"

export JMRI_LAYOUT="${JMRI_LAYOUT:-hart}"

#!/usr/bin/env bash
# Wire the car-cards workspace (symlinks + empty dirs).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../env/load_env.sh
source "${SCRIPT_DIR}/../env/load_env.sh"

CAR="$HART_CAR_CARDS_ROOT"
HOPS="$HART_OPS_ROOT"
FINAL="$HART_CAR_IMAGES_FINAL"

mkdir -p "$CAR/incoming" "$CAR/CarImages" "$CAR/OcrZoom"
mkdir -p "$FINAL"

link() {
  local target="$1"
  local linkpath="$2"
  if [[ -L "$linkpath" ]]; then return 0; fi
  if [[ -e "$linkpath" && ! -L "$linkpath" ]]; then
    echo "WARN: $linkpath exists and is not a symlink — skipped" >&2
    return 0
  fi
  ln -sf "$target" "$linkpath"
  echo "link $linkpath -> $target"
}

link "incoming" "$CAR/Images"
link "car-images/CarImagesFinal" "$CAR/CarImagesFinal"
link "../../external/hart-ops/data" "$CAR/data"

echo "Car cards workspace ready: $CAR"
echo "  Drop raw photos in: $CAR/incoming/"
echo "  Scripts: $HOPS/card_pipeline/"
echo "  export HART_CAR_CARDS_ROOT=$CAR"
echo "  export HART_CAR_IMAGES_FINAL=$FINAL"

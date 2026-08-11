#!/usr/bin/env bash
# Launch CATS with HART Master ABS Digicon sheet (open-house automatic signaling).
# Usage: ./cats/scripts/launch_hart_master_abs.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec "$ROOT/cats/scripts/launch_cats.sh" "$ROOT/cats/panels/HART_Master_ABS.xml"

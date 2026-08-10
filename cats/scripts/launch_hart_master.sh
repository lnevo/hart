#!/usr/bin/env bash
# Launch CATS with HART Master Digicon sheet (CTC discipline).
# Usage: ./cats/scripts/launch_hart_master.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec "$ROOT/cats/scripts/launch_cats.sh" "$ROOT/cats/panels/sheets/HART_Master.xml"

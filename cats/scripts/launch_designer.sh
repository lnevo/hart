#!/usr/bin/env bash
# Launch CATS Designer 3.2 (run from a machine with JMRI + Java).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CATS="$ROOT/tools/cats/release3.2"
if [[ ! -f "$CATS/designer.jar" ]]; then
  echo "CATS not installed — run: $ROOT/tools/cats/fetch_cats_3.2.sh" >&2
  exit 1
fi
cd "$CATS"
exec ./designer.csh

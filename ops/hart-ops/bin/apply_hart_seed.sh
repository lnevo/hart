#!/usr/bin/env bash
set -euo pipefail
_OPS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_HELPERS="$("$_OPS_ROOT/bin/sts_helpers_root.sh")"
exec "$_HELPERS/bin/$(basename "${BASH_SOURCE[0]}")" "$@"

#!/usr/bin/env bash
set -euo pipefail
_OPS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_HELPERS="$("$_OPS_ROOT/bin/sts_helpers_root.sh")"
for name in apply_warm_start.sh begin_session.sh build_hart_seed_package.sh generate_switchlists.sh; do
  ln -sf "$_HELPERS/bin/$name" "$_OPS_ROOT/bin/$name" 2>/dev/null || cp "$_HELPERS/bin/$name" "$_OPS_ROOT/bin/$name"
done
echo "bin/ wrappers linked to sts-helpers"

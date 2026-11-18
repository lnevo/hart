#!/usr/bin/env bash
# Runs on the Pi (sync_hart_package.sh pipes it over ssh before a Pi deploy). Names the files the
# owner changed on the Pi since the last deploy or pull, which the deploy would replace:
#   ops     the six Operations Pro files differ from operations/.deployed.sha256 (make ops-pull)
#   tables  tables.xml differs from .tables_deployed.sha256, a PanelPro Store (make tables-pull-pi)
# A missing stamp counts as nothing changed: the next deploy or pull writes it.
# Prints one word per changed set, nothing when both are clean.
# Usage: unpulled_changes.sh USERFILES
set -euo pipefail
uf="${1:?usage: unpulled_changes.sh USERFILES}"
ops="$uf/operations"
FILES=(Operations.xml OperationsCarRoster.xml OperationsEngineRoster.xml
       OperationsLocationRoster.xml OperationsRouteRoster.xml OperationsTrainRoster.xml)

sha() { { command -v sha256sum >/dev/null && sha256sum || shasum -a 256; } | cut -d' ' -f1; }

# The same hash install_ops_files.sh and pull_ops.sh write.
if [[ -f "$ops/.deployed.sha256" ]]; then
  have="$(for f in "${FILES[@]}"; do cat "$ops/$f" 2>/dev/null || true; done | sha)"
  [[ "$have" == "$(cat "$ops/.deployed.sha256")" ]] || echo ops
fi
if [[ -f "$uf/.tables_deployed.sha256" && -f "$uf/tables.xml" ]]; then
  [[ "$(sha <"$uf/tables.xml")" == "$(cat "$uf/.tables_deployed.sha256")" ]] || echo tables
fi

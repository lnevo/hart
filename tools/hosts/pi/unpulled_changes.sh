#!/usr/bin/env bash
# Runs on the Pi (sync_hart_package.sh pipes it over ssh before a Pi deploy). Names the files the
# owner changed on the Pi since the last deploy or pull, which the deploy would replace:
#   ops     the six Operations Pro files differ from operations/.deployed.sha256 (make ops-pull)
#   tables  tables.xml differs from what was last deployed or pulled, a PanelPro Store (make tables-pull-pi)
# What was last deployed is tables_sha256 in cats/deploy_stamp.txt (every deploy since 2026-11-12,
# rollbacks too); a later make tables-pull-pi writes .tables_deployed.sha256. The newer of the two counts.
# With no tables reference at all, GENERATED_SHA (the generated tables.xml's hash, which the deploy and the pulls
# pass) is the reference: a file that differs from it counts as changed (ADR-029: it may hold an owner's Store).
# Without GENERATED_SHA, no reference counts as nothing changed (and so for the Operations files always).
# SPLIT_SHA...: the Stores already split into the sources being deployed (store_splits.csv, R9d); a tables.xml with
# one of those hashes counts as taken, so the deploy replaces it with the generated file that now holds its edits.
# Prints one word per changed set, nothing when both are clean.
# Usage: unpulled_changes.sh USERFILES [GENERATED_SHA [SPLIT_SHA...]]
set -euo pipefail
uf="${1:?usage: unpulled_changes.sh USERFILES [GENERATED_SHA [SPLIT_SHA...]]}"
generated="${2:-}"
shift $(( $# < 2 ? $# : 2 ))
splits=" $* "
ops="$uf/operations"
FILES=(Operations.xml OperationsCarRoster.xml OperationsEngineRoster.xml
       OperationsLocationRoster.xml OperationsRouteRoster.xml OperationsTrainRoster.xml)

sha() { { command -v sha256sum >/dev/null && sha256sum || shasum -a 256; } | cut -d' ' -f1; }

# The same hash install_ops_files.sh and pull_ops.sh write.
if [[ -f "$ops/.deployed.sha256" ]]; then
  have="$(for f in "${FILES[@]}"; do cat "$ops/$f" 2>/dev/null || true; done | sha)"
  [[ "$have" == "$(cat "$ops/.deployed.sha256")" ]] || echo ops
fi
stamp="$uf/cats/deploy_stamp.txt" pulled="$uf/.tables_deployed.sha256" want=""
if [[ -f "$pulled" && ( ! -f "$stamp" || "$pulled" -nt "$stamp" ) ]]; then
  want="$(cat "$pulled")"
elif [[ -f "$stamp" ]]; then
  want="$(sed -n 's/^tables_sha256=//p' "$stamp")"
fi
[[ -n "$want" && "$want" != none ]] || want="$generated"
if [[ -n "$want" && "$want" != none && -f "$uf/tables.xml" ]]; then
  have="$(sha <"$uf/tables.xml")"
  [[ "$have" == "$want" || "$splits" == *" $have "* ]] || echo tables
fi

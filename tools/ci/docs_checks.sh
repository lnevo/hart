#!/usr/bin/env bash
# The quick docs checks: what a change of Markdown docs only (tools/ci/changed_kind.py) is checked with, in CI
# (.github/workflows/check.yml, "Quick docs checks") and by tools/check.sh's docs-only path. One list for both, so
# they cannot drift. Each check runs, a failure does not stop the rest, and the exit is 1 when any failed.
# HOPS_PY is the Python for the public text check (tools/check.sh passes ops/hart-ops/.venv's, which has pypdf; CI
# installs it into python3).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 2
HOPS_PY="${HOPS_PY:-python3}"
failed=()
check() {
  local name="$1"
  shift
  echo "--- $name"
  "$@" || failed+=("$name")
}
check docs-index python3 tools/ops/build_docs_index.py --check --strict
check status-counts python3 tools/ops/status_counts.py --check
check ai-speak python3 tools/audit/check_ai_speak.py
check agent-docs python3 tools/audit/check_agent_docs.py
# the map's agent-doc lane is generated from the wiki and agent docs, so a docs-only change can leave it stale
check pipeline-map-site python3 tools/ops/build_pipeline_map.py --public --out www/library/pipeline-map.html --back repository-guide.html --check
check public-text "$HOPS_PY" tools/audit/check_public_text.py
check repo-guide python3 www/scripts/repo_guide_page.py --check
check jmri-additions python3 www/scripts/jmri_additions_page.py --check
if (( ${#failed[@]} > 0 )); then
  echo "quick docs checks FAILED: ${failed[*]}"
  exit 1
fi

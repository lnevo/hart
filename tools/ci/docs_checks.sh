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
# The unit tests that read Markdown docs or the wiki in the repo itself (tools/audit/check_stamps.py declares them on
# docs/ or wiki/): only the test or class that reads them, so a docs-only change cannot break them unseen. The guard
# tools/audit/tests/test_check_docs_only.py keeps this list in step with those declarations. A -k that matches no test
# fails (unittest exits 5 when no test ran, Python 3.12 and later; the guard also checks each -k names a class).
# check_name_copies.py over the whole repo, Markdown included: a renamed device's old name left in a doc
check unit-guards-test_name_copies python3 -m unittest discover -b -q -s tools/audit/tests -p test_name_copies.py
# every log tag in docs/jmri/speedmatching/RUNBOOK.md is emitted by a runner
check unit-jmri-test_speedmatch_distance python3 -m unittest discover -b -q -s jmri/layouts/hart/scripts/tests -p test_speedmatch_distance.py -k RunnerSource.
if (( ${#failed[@]} > 0 )); then
  echo "quick docs checks FAILED: ${failed[*]}"
  exit 1
fi

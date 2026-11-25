#!/usr/bin/env bash
# The quick docs checks: what a change of Markdown docs only (tools/ci/changed_kind.py) is checked with, in CI
# (.github/workflows/check.yml, "Quick docs checks") and by tools/check.sh's docs-only path. One list for both, so
# they cannot drift. Each check runs, a failure does not stop the rest, and the exit is 1 when any failed.
# The checks are the steps marked docs_only in the step manifest, tools/pipeline/checks.toml (ADR-037), each also in
# check.sh's full run; a manifest that does not load, or lists no docs check, stops here with exit 2 and runs nothing.
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
if ! lines="$(python3 tools/pipeline/manifest.py jobs check --docs-only)"; then
  echo "STOP: tools/pipeline/manifest.py jobs check --docs-only failed (its error is above); no docs check ran"
  exit 2
fi
# A line is a step's name, then its command, shell-quoted ("$HOPS_PY" for the public text check's Python). It is
# parsed in a subshell first: a line that will not parse, eval'd here, leaves bash 3.2 unable to read the rest of
# this file.
check_line() { ( eval "set -- $1" ) || return 1; eval "check $1"; }
# The lines come in on fd 3 and each check gets no stdin, so a check that reads stdin cannot eat the lines after it.
ran=0
while IFS= read -r line <&3; do
  [[ -z "$line" ]] && continue
  ran=$((ran + 1))
  check_line "$line" </dev/null || failed+=("${line%% *} (its line from the manifest would not parse)")
done 3<<<"$lines"
if (( ran == 0 )); then
  echo "STOP: tools/pipeline/manifest.py jobs check --docs-only listed no check; no docs check ran"
  exit 2
fi
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

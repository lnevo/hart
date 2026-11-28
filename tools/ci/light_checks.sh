#!/usr/bin/env bash
# The light checks: what a light change (tools/ci/changed_kind.py: docs, or data that only static checks read) is
# checked with, by tools/check.sh's light path (`light_checks.sh --git`) and in CI (the changed paths on stdin,
# `light_checks.sh -z --compare <base ref>`, NUL-separated). The arguments go to `changed_kind.py --jobs`, which prints check.sh's jobs
# for the change: make static's (the static group less the panels-* jobs), then any other static job a changed file
# is declared to feed. check.sh runs those (CHECK_ONLY, with its stamps), then the quick docs checks
# (tools/ci/docs_checks.sh: the docs_only steps, public-text among them, and the unit tests that read docs). Both run;
# the exit is 1 when either failed, 2 when the job list cannot be made. The last line is LIGHT CHECKS PASSED or FAILED,
# never ALL PASSED: it is not a full pass of check.sh.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 2
if ! jobs="$(python3 tools/ci/changed_kind.py --jobs "$@")" || [[ -z "${jobs//[[:space:]]/}" ]]; then
  echo "STOP: tools/ci/changed_kind.py --jobs $* listed no job (its error is above); no light check ran"
  exit 2
fi
failed=()
echo "--- light: check.sh jobs $(paste -sd' ' - <<<"$jobs")"
CHECK_ONLY="^($(paste -sd'|' - <<<"$jobs"))\$" CHECK_PASS_LINE="--- light: check.sh's jobs passed" \
  ./tools/check.sh || failed+=("check.sh jobs")
echo "--- light: quick docs checks"
bash tools/ci/docs_checks.sh || failed+=("quick docs checks")
if (( ${#failed[@]} > 0 )); then
  echo "light checks FAILED: ${failed[*]}"
  echo "FAILED"
  exit 1
fi
echo "LIGHT CHECKS PASSED (make static, the static checks that read the changed files and the quick docs checks; FULL=1 runs check.sh in full)"

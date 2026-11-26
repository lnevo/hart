# shellcheck shell=bash
# Sourced by tools/check.sh and tools/schematic/build_panels.sh: one line per step run into the local timings log,
# step-timings.tsv in the shared cache (hart_cache_dir: <main checkout>/.cache/hart, gitignored, so every worktree
# appends to one log). tools/pipeline/timings.py summarize (make timings) turns it into docs/pipeline-map/timings.json.
# Each line, tab-separated:
#   iso_time  runner  step  seconds  result  mode
# runner is panels or check, step the manifest step's name (check.sh's job name: panels-<step> for the panels jobs),
# result ok, failed or skipped (its stamp said current), mode cold, warm or empty.
# HART_STEP_TIMINGS_LOG names another log; set and empty, nothing is written (tests that run a runner on stubs).
# Nothing here can fail a run: a log that cannot be made or written is left alone.

_STEP_TIMINGS_GUARD="$(cd "$(dirname "${BASH_SOURCE[0]}")/../hosts" 2>/dev/null && pwd)/profile_tables_guard.sh"
# shellcheck source=../hosts/profile_tables_guard.sh
type hart_cache_dir >/dev/null 2>&1 || source "$_STEP_TIMINGS_GUARD" 2>/dev/null || true

# step_timings_open ROOT: set STEP_TIMINGS_LOG to the log for checkout ROOT, or to "" when it is off or its folder
# cannot be made.
step_timings_open() {
  if [[ -n "${HART_STEP_TIMINGS_LOG+set}" ]]; then
    STEP_TIMINGS_LOG="$HART_STEP_TIMINGS_LOG"
  else
    STEP_TIMINGS_LOG="$(hart_cache_dir "$1" step-timings.tsv 2>/dev/null)" || STEP_TIMINGS_LOG=""
  fi
  if [[ -n "$STEP_TIMINGS_LOG" ]] && ! mkdir -p "$(dirname "$STEP_TIMINGS_LOG")" 2>/dev/null; then
    STEP_TIMINGS_LOG=""
  fi
  return 0
}

# step_timings_mode FULL CACHE: "cold" when FULL is 1 or the schematic cache folder CACHE is off (empty), missing or
# empty, else "warm".
step_timings_mode() {
  if [[ "$1" == 1 || -z "$2" || ! -d "$2" || -z "$(find "$2" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
    echo cold
  else
    echo warm
  fi
}

# step_timing RUNNER STEP SECONDS RESULT MODE: append one line, stamped STEP_TIMINGS_NOW when set (one time for a
# batch), else now. Any failure is ignored.
step_timing() {
  [[ -n "${STEP_TIMINGS_LOG:-}" ]] || return 0
  local now="${STEP_TIMINGS_NOW:-}"
  [[ -n "$now" ]] || now="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" || return 0
  { printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$now" "$1" "$2" "$3" "$4" "$5" >>"$STEP_TIMINGS_LOG"; } 2>/dev/null
  return 0
}

# step_timings_jobs ROOT JOBS MANIFEST_JOBS NAME...: check.sh's lines, after its jobs are collected. NAME are its queued
# jobs in order; job i left $JOBS/i.skip (its stamp was current) or $JOBS/i.rc and $JOBS/i.time. Only the jobs named in
# MANIFEST_JOBS (space-separated, with a space at each end) are logged, all with the time the run ends. mode is cold
# with FULL=1 or the schematic cache off (SCHEMATIC_CACHE empty).
step_timings_jobs() {
  local root=$1 jobs=$2 manifest=$3 mode i=0 name res secs
  shift 3
  step_timings_open "$root"
  [[ -n "$STEP_TIMINGS_LOG" ]] || return 0
  mode="$(step_timings_mode "${FULL:-}" "${SCHEMATIC_CACHE:-}")"
  STEP_TIMINGS_NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" || return 0
  for name in "$@"; do
    if [[ "$manifest" == *" $name "* ]]; then
      if [[ -e "$jobs/$i.skip" ]]; then
        res=skipped secs=0
      else
        res=failed
        [[ "$(cat "$jobs/$i.rc" 2>/dev/null)" == 0 ]] && res=ok
        secs="$(cat "$jobs/$i.time" 2>/dev/null)" || secs=""
      fi
      step_timing check "$name" "$secs" "$res" "$mode"
    fi
    i=$((i + 1))
  done
  STEP_TIMINGS_NOW=""
  return 0
}

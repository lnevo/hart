# shellcheck shell=bash
# Sourced by tools/check.sh and tools/schematic/build_panels.sh: one line per step run into the local timings log,
# step-timings.tsv in the shared cache (hart_cache_dir: <main checkout>/.cache/hart, gitignored, so every worktree
# appends to one log). tools/pipeline/timings.py summarize (make timings) turns it into docs/pipeline-map/timings.json.
# Each line, tab-separated:
#   iso_time  runner  step  seconds  result  mode
# runner is panels or check, step the manifest step's name (check.sh's job name: panels-<step> for the panels jobs),
# result ok, failed or skipped (its stamp said current, or it printed SKIPPED), mode cold (the schematic cache off or
# empty), warm or empty. HART_STEP_TIMINGS_LOG names another log (spaces trimmed, a leading ~ expanded); set and
# empty or spaces, nothing is written (tests that run a runner on stubs).
# Nothing here can fail a run or change its output: a log that cannot be made or written is left alone, and the
# failure goes as one line (iso_time  runner  what failed) into step-timings.err beside the default log in the shared
# cache, once per run; when even that cannot be written, nowhere. Each runner writes that line itself when this file
# does not source.

_STEP_TIMINGS_GUARD="$(cd "$(dirname "${BASH_SOURCE[0]}")/../hosts" 2>/dev/null && pwd)/profile_tables_guard.sh"
# shellcheck source=../hosts/profile_tables_guard.sh
type hart_cache_dir >/dev/null 2>&1 || source "$_STEP_TIMINGS_GUARD" 2>/dev/null || true

# step_timings_err WHAT: one line into step-timings.err in the shared cache of STEP_TIMINGS_ROOT, the first time in a
# run; silent when it cannot be written.
step_timings_err() {
  [[ -z "${STEP_TIMINGS_ERRED:-}" ]] || return 0
  STEP_TIMINGS_ERRED=1
  local err
  err="$(hart_cache_dir "${STEP_TIMINGS_ROOT:-.}" step-timings.err 2>/dev/null)" || return 0
  { mkdir -p "$(dirname "$err")" && printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "${STEP_TIMINGS_RUNNER:-}" "$1" >>"$err"; } 2>/dev/null
  return 0
}

# step_timings_open ROOT RUNNER: set STEP_TIMINGS_LOG to the log for checkout ROOT, or to "" when it is off or its
# folder cannot be made (an .err line says which).
step_timings_open() {
  STEP_TIMINGS_ROOT=$1 STEP_TIMINGS_RUNNER=$2
  if [[ -n "${HART_STEP_TIMINGS_LOG+set}" ]]; then
    STEP_TIMINGS_LOG="${HART_STEP_TIMINGS_LOG#"${HART_STEP_TIMINGS_LOG%%[![:space:]]*}"}"
    STEP_TIMINGS_LOG="${STEP_TIMINGS_LOG%"${STEP_TIMINGS_LOG##*[![:space:]]}"}"
    case "$STEP_TIMINGS_LOG" in
      "~") STEP_TIMINGS_LOG="$HOME" ;;
      "~/"*) STEP_TIMINGS_LOG="$HOME/${STEP_TIMINGS_LOG#\~/}" ;;
    esac
  elif ! STEP_TIMINGS_LOG="$(hart_cache_dir "$1" step-timings.tsv 2>/dev/null)"; then
    STEP_TIMINGS_LOG=""
    step_timings_err "hart_cache_dir failed (tools/hosts/profile_tables_guard.sh not loaded?)"
  fi
  if [[ -n "$STEP_TIMINGS_LOG" ]] && ! mkdir -p "$(dirname "$STEP_TIMINGS_LOG")" 2>/dev/null; then
    step_timings_err "cannot make the log's folder $(dirname "$STEP_TIMINGS_LOG")"
    STEP_TIMINGS_LOG=""
  fi
  return 0
}

# step_timings_mode CACHE: "cold" when the schematic cache folder CACHE is off (empty), missing or empty, else "warm".
step_timings_mode() {
  if [[ -z "$1" || ! -d "$1" || -z "$(find "$1" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
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
  { printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$now" "$1" "$2" "$3" "$4" "$5" >>"$STEP_TIMINGS_LOG"; } 2>/dev/null ||
    step_timings_err "cannot append to $STEP_TIMINGS_LOG"
  return 0
}

# step_timings_jobs ROOT JOBS MANIFEST_JOBS NAME...: check.sh's lines, after its jobs are collected. NAME are its queued
# jobs in order; job i left $JOBS/i.skip (its stamp was current) or $JOBS/i.rc, $JOBS/i.time and $JOBS/i.log (a job
# that printed SKIPPED, as collect counts it, is logged skipped). Only the jobs named in MANIFEST_JOBS (space-separated,
# with a space at each end) are logged, all with the time the run ends. mode is read after the jobs ran, so it is cold
# only when the schematic cache is off or still empty.
step_timings_jobs() {
  local root=$1 jobs=$2 manifest=$3 mode i=0 name res secs
  shift 3
  step_timings_open "$root" check
  [[ -n "$STEP_TIMINGS_LOG" ]] || return 0
  mode="$(step_timings_mode "${SCHEMATIC_CACHE:-}")"
  STEP_TIMINGS_NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" || return 0
  for name in "$@"; do
    if [[ "$manifest" == *" $name "* ]]; then
      if [[ -e "$jobs/$i.skip" ]]; then
        res=skipped secs=0
      else
        res=failed
        [[ "$(cat "$jobs/$i.rc" 2>/dev/null)" == 0 ]] && res=ok
        [[ "$res" == ok ]] && grep -q SKIPPED "$jobs/$i.log" 2>/dev/null && res=skipped
        secs="$(cat "$jobs/$i.time" 2>/dev/null)" || secs=""
      fi
      step_timing check "$name" "$secs" "$res" "$mode"
    fi
    i=$((i + 1))
  done
  STEP_TIMINGS_NOW=""
  return 0
}

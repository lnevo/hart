#!/usr/bin/env bash
# Rebuild every output drawn from the schematic, in the order they depend on each other, or check them all with
# --check (exit 1 if any is stale). `make panels` and `make panels CHECK=1` run this.
#
# usage: build_panels.sh [--check] [--full]
#
# The steps, their order, commands and outputs are the panels manifest's, tools/pipeline/panels.toml (ADR-037): one
# [[step]] each, read through `python3 tools/pipeline/manifest.py jobs panels`, which checks the order (each writer
# before the steps that read its file). A step ("step") writes its outputs, or checks them with --check (its
# check_args); a guard ("guard") only checks, in both modes. The approved-* guards stop a write that drifts from the
# owner-approved fingerprints, before anything else reads it. A manifest that does not load, or lists no step, stops
# the run before any step, so make panels never says "all current" having run nothing.
#
# Each step reads the plugin's cache (<main checkout>/.cache/hart/schematic): the solve is shared, and Layout Editor panels whose
# inputs and plugin code are unchanged are read back, so a run after a small change redoes only what that change
# reaches. A write stops at the first failure, since what follows reads that step's output (step) or the files it
# checks (guard); --check runs every step and names each stale one.
#
# Each step also has a traced stamp (tools/schematic/panel_stamps.py, tools/audit/traced.py): a step runs under a hook
# that logs the repo files its Python processes read, probe and list; while all of those, its outputs, its code and the
# plugin's commit are what its last successful run left, it prints "<name>: current, skipped" and does not run, so an
# edit re-runs only the steps that read the file. A step that ran a program the hook cannot see records nothing and
# runs every time. The stamps are kept per checkout in .cache/panel-stamps/; --full (make panels FULL=1) ignores them
# and records. Guards always run.
#
# SML discovery: when sml-current says stale (exit 4) in a write, the run discovers and goes on to tables, but only
# on the Mac (uname Darwin), outside CI, while the operating flag is clear (tools/hosts/operating.sh) and with
# HART_SML_AUTO_DISCOVER not 0 (or false, no, off), with HART_TABLES unset and one discovery at a
# time (a lock in /tmp). Anywhere else it stops as before and names the command. run_sml_discover.sh keeps its
# own refusals: PanelPro or CATS running, HART_TABLES set, a Layout Editor panel the owner has not approved
# (HART_TABLES_REVIEW=1 discovers on one under review). A failed discovery stops the run with its message.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1
# A step that cannot load the schematic-maps plugin fails rather than printing SKIPPED and passing, as in CI (owner,
# 2026-11-23): a worktree without the submodule must not look current. SCHEMATIC_REQUIRED=0 lets those steps skip.
export SCHEMATIC_REQUIRED="${SCHEMATIC_REQUIRED:-1}"

check=()
full=0
for arg in "$@"; do
  case "$arg" in
    --check) check=(--check) ;;
    --full) full=1 ;;
    *) echo "usage: $0 [--check] [--full]" >&2; exit 2 ;;
  esac
done
# A write logs each step it runs (ok, failed, or skipped while its stamp holds) to the local timings log
# (tools/pipeline/step_timings.sh; make timings summarizes it); a step that printed SKIPPED is logged skipped. mode is
# cold when the schematic cache is off or empty at the start (--full ignores the stamps, not the cache).
step_timing() { :; }
timing_mode=""
if [ ${#check[@]} -eq 0 ] && source tools/hosts/profile_tables_guard.sh 2>/dev/null &&
    ! source tools/pipeline/step_timings.sh 2>/dev/null; then
  step_timing() { :; }      # a helper that broke while it was read: its .err line, then nothing
  { mkdir -p "$(hart_cache_dir "$PWD" "")" && printf '%s\tpanels\tsource tools/pipeline/step_timings.sh failed\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >>"$(hart_cache_dir "$PWD" step-timings.err)"; } 2>/dev/null
elif [ ${#check[@]} -eq 0 ] && type step_timings_open >/dev/null 2>&1; then
  step_timings_open "$PWD" panels
  timing_mode=$(step_timings_mode "${SCHEMATIC_CACHE-$(hart_cache_dir "$PWD" schematic 2>/dev/null)}")
fi
# The step lines (manifest.py panel_lines): mode, name, how many check_args, the check_args, then the command; plain
# words, split on spaces. All are read and checked before the first step runs, so no step reads them on its stdin.
manifest_stop() { echo "stopped: $1; no step ran" >&2; exit 2; }
lines=$(python3 tools/pipeline/manifest.py jobs panels) ||
  manifest_stop "tools/pipeline/manifest.py jobs panels failed (its error is above)"
STEP_LINES=()
while IFS= read -r line; do
  [ -n "$line" ] && STEP_LINES+=("$line")
done <<<"$lines"
[ ${#STEP_LINES[@]} -gt 0 ] || manifest_stop "tools/pipeline/manifest.py jobs panels listed no step"
for line in "${STEP_LINES[@]}"; do
  read -r -a w <<<"$line"
  case "${w[0]:-}" in step|guard) ;; *) manifest_stop "manifest.py printed \"$line\", not a step line" ;; esac
  case "${w[2]:-x}" in *[!0-9]*) manifest_stop "manifest.py printed \"$line\", not a step line" ;; esac
  [ ${#w[@]} -ge $((w[2] + 5)) ] || manifest_stop "manifest.py printed \"$line\", with no command"
done
STAMPS=(python3 tools/schematic/panel_stamps.py)
# No stamps while HART_TABLES is set or the plugin is off its pin: nothing is skipped and nothing recorded (said once).
why=$("${STAMPS[@]}" unstampable) && unstamped=0 || unstamped=1
if [ "$unstamped" -eq 1 ]; then
  [ "$full" -eq 0 ] && echo "stamps off for this run: $why"
  full=1
  nostamp=1
else
  nostamp=0
fi

failed=()
# traced LOG CMD...: run CMD with the trace hook logging into LOG (tools/audit/traced.py), or plainly when LOG is empty.
traced() {
  local log=$1
  shift
  if [ -z "$log" ]; then "$@"; return; fi
  env -u HART_TRACE_SPAWN HART_TRACE_LOG="$log" HART_TRACE_ROOT="$PWD" \
    PYTHONPATH="$PWD/tools/audit/trace_hook${PYTHONPATH:+:$PYTHONPATH}" "$@"
}
# run_step STOP KIND NAME CMD...: KIND is "stamped" for a step (skipped while its stamp is the last successful run's,
# tools/schematic/panel_stamps.py; --full ignores the stamps) and "guard" for a check that always runs.
run_step() {
  local stop=$1 kind=$2 name=$3 start=$SECONDS
  shift 3
  echo "== $name"
  if [ "$kind" = stamped ] && [ "$full" -eq 0 ] && "${STAMPS[@]}" current "$name" "$@" 2>/dev/null; then
    echo "   $name: current, skipped"
    step_timing panels "$name" $((SECONDS - start)) skipped "$timing_mode"
    return
  fi
  local out; out=$(mktemp)
  local trace=""
  if [ "$kind" = stamped ] && [ "$nostamp" -eq 0 ]; then
    trace=$(mktemp)
    printf '0\tb\n' >"$trace"      # the runner starts one Python process: its start must be in the trace
    "${STAMPS[@]}" snapshot "$trace.before"     # git and plugin state now: a change while the step runs records nothing
  fi
  traced "$trace" "$@" ${cargs[@]+"${cargs[@]}"} | tee "$out"
  local rc=${PIPESTATUS[0]} tee_rc=${PIPESTATUS[1]}
  [ "$rc" -eq 0 ] && [ "$tee_rc" -ne 0 ] && { echo "   $name: could not save its output ($out)"; rc=$tee_rc; }
  if [ "$rc" -eq 0 ]; then
    echo "   $name: ok, $((SECONDS - start)) s"
    if grep -q '^SKIPPED' "$out"; then
      step_timing panels "$name" $((SECONDS - start)) skipped "$timing_mode"
    else
      step_timing panels "$name" $((SECONDS - start)) ok "$timing_mode"
    fi
    # a step that printed SKIPPED did not really run (plugin off its pin): it must not stamp
    if [ -n "$trace" ]; then
      if grep -q '^SKIPPED' "$out"; then
        echo "   $name: printed SKIPPED, no stamp"
        "${STAMPS[@]}" forget "$name"
      else
        "${STAMPS[@]}" record "$name" --trace "$trace" --snapshot "$trace.before" "$@"
      fi
    fi
    rm -f "$out" ${trace:+"$trace" "$trace.before"}
  else
    rm -f "$out" ${trace:+"$trace" "$trace.before"}
    echo "   $name: FAILED, $((SECONDS - start)) s"
    [ "$kind" = stamped ] && "${STAMPS[@]}" forget "$name"
    if [ "$name" = sml-current ] && [ "$rc" -eq 4 ] && [ "$discovered" -eq 0 ] && discover_sml; then
      run_step "$stop" "$kind" "$name" "$@"     # once: discovered=1 now, so a second stale verdict stops the run
      return                                    # (the retry logs the step's one timing line)
    fi
    step_timing panels "$name" $((SECONDS - start)) failed "$timing_mode"
    failed+=("$name")
    [ ${#check[@]} -eq 0 ] && { echo "stopped: $stop"; exit 1; }
  fi
}
# discover_sml: in a write on the Mac, run SML discovery after sml-current said stale (header, "SML discovery").
# Returns 1 when discovery is not for this run (and says why); exits when discovery itself fails.
discovered=0
discover_sml() {
  local cmd=${HART_SML_DISCOVER_CMD:-jmri/layouts/hart/scripts/run_sml_discover.sh} os=${HART_PANELS_OS:-$(uname -s)}
  local why=""
  if [ ${#check[@]} -gt 0 ]; then return 1
  fi
  case "${HART_SML_AUTO_DISCOVER:-1}" in
    0|false|no|off) why="HART_SML_AUTO_DISCOVER=${HART_SML_AUTO_DISCOVER}" ;;
  esac
  if [ -n "$why" ]; then :
  elif [ -n "${CI:-}" ]; then why="this is CI"
  elif [ -n "${HART_TABLES:-}" ]; then why="HART_TABLES is set (discovery runs on the repo's tables.xml only)"
  elif [ "$os" != Darwin ]; then why="discovery runs PanelPro on the Mac, and this is $os"
  elif bash tools/hosts/operating.sh status >/dev/null 2>&1; then why="the operating flag is set (tools/hosts/operating.sh status)"
  fi
  if [ -n "$why" ]; then
    echo "   sml-current: not discovering here: $why"
    return 1
  fi
  # One discovery at a time on this Mac: worktrees share the PanelPro profile and the script's /tmp marker. The lock
  # holds the owner's pid, so a run that was killed leaves a lock the next one takes over.
  local lock=${HART_SML_DISCOVER_LOCK:-/tmp/hart_sml_discover.lock} holder
  if ! mkdir "$lock" 2>/dev/null; then
    holder=$(cat "$lock/pid" 2>/dev/null)
    if [ -z "$holder" ]; then     # another run made the lock and has not written its pid yet
      echo "   sml-current: not discovering here: another make panels is starting a discovery ($lock has no pid yet; remove it if no run is)"
      return 1
    fi
    if kill -0 "$holder" 2>/dev/null; then
      echo "   sml-current: not discovering here: another make panels (pid $holder) is discovering; make panels again when it ends"
      return 1
    fi
    echo "   sml-discover: taking over $lock from pid $holder, which is gone"
  fi
  echo $$ >"$lock/pid"
  discovered=1
  local t0=$SECONDS rc=0
  echo "== sml-discover: $cmd (PanelPro on the Mac, about 3 min)"
  bash "$cmd" || rc=$?
  rm -rf "$lock"
  if [ "$rc" -ne 0 ]; then
    echo "   sml-discover: FAILED, $((SECONDS - t0)) s"
    echo "stopped: SML discovery failed (its message is above); make panels again once it is fixed"
    exit 1
  fi
  echo "   sml-discover: ok, $((SECONDS - t0)) s"
}
# A step that writes its outputs (or checks them, with --check).
step() { run_step "later steps read what $1 writes" stamped "$@"; }
# A step that only checks, in both modes: it writes nothing, and its message names what to run by hand.
guard() { run_step "$1 only checks and it failed; later steps read the files it checks" guard "$@"; }

# Run them, in the manifest's order.
for line in "${STEP_LINES[@]}"; do
  read -r -a w <<<"$line"
  n=${w[2]}
  cargs=()                              # what --check adds to this step's command
  if [ ${#check[@]} -gt 0 ] && [ "$n" -gt 0 ]; then cargs=("${w[@]:3:n}"); fi
  "${w[0]}" "${w[1]}" "${w[@]:$((3 + n))}"
done

if [ ${#failed[@]} -gt 0 ]; then
  echo "stale or failed: ${failed[*]}"
  exit 1
fi
echo "all current"

#!/usr/bin/env bash
# One PanelPro run on this Mac, shared by the wrappers in jmri/layouts/hart/scripts
# (run_panelpro_smoke_test.sh, run_panelpro_stage1.sh, run_panelpro_traininfo_repair.sh,
# run_sml_discover.sh, run_nx_discover.sh, run_ctc_logic_smoke.sh). Source it after ROOT is set.
# The profile steps are tools/hosts/panelpro_profile.py.
#
#   pp_profile            sets JMRI_HOME, STARTJMRI, PROFILE_XML, PROFILE_ID, PP_USER_FILES, TABLES_URI;
#                         stops unless they name one profile (and, for any profile but the live one,
#                         its own user files folder), before anything is changed
#   pp_refuse_running MSG [CODE]   exits CODE (1) while PanelPro, DecoderPro or CATS runs (hartlib's check)
#   pp_begin SCRIPT       backs the profile up to <profile.xml>.hart-run.bak and sets the traps that put
#                         it back on any exit (also timeout, Ctrl-C, SIGTERM, SIGHUP); points Start Up
#                         at this checkout's tables, switches off every Start Up item that runs code
#                         except panelpro_profile.py's allowlist, adds SCRIPT, and seals the result
#   pp_guard_dir DIR      after pp_begin: DIR is put back as it was if the run fails
#   pp_launch LOG         starts PanelPro on the profile in the background
#   pp_wait_marker MARKER SECONDS INTERVAL   0 marker written, 1 PanelPro quit first, 2 timed out
#   pp_wait_exit SECONDS  0 once the PanelPro this run started has quit, 1 if it still runs
#
# On exit the traps stop the PanelPro this run started (TERM, then KILL after HART_PANELPRO_KILL_WAIT
# seconds, default 30), then restore the profile. Only processes started by pp_launch are stopped,
# never another JMRI or CATS. If they cannot be stopped the backup is left in place with the
# recovery command. HART_PANELPRO_TIMEOUT overrides a wrapper's marker timeout. HART_PANELPRO_POLL
# (seconds, fractions allowed) overrides every poll interval here; the tests set it short.
#
# PanelPro still connects to MQTT during a run. With the Start Up scripts off nothing HART-written
# publishes, but JMRI's own listeners (Logix, LogixNG, SML, Dispatcher) still react to sensor and
# turnout changes. A rehearsal should run with the broker unreachable.
#
# Rehearsal on a copy of the live profile, never touching it or ~/JMRI_UserFiles:
#   1. cp -R ~/Library/Preferences/JMRI/My_JMRI_Railroad.jmri <scratch>/Rehearsal.jmri
#   2. in <scratch>/Rehearsal.jmri/profile/profile.properties (and every node folder's
#      profile.properties) set  jmri-implementation.user-files=<scratch>/userfiles/
#      and copy the user files you need there (jython/, dispatcher/traininfo/)
#   3. point its MQTT connection at an unreachable host if PanelPro must not reach the broker
#   4. JMRI_PROFILE_XML=<scratch>/Rehearsal.jmri/profile/profile.xml ./jmri/layouts/hart/scripts/<wrapper>
#      (JMRI starts on that folder; JMRI_USER_FILES, if set, must equal step 2's folder)
# A profile other than the live one that still uses ~/JMRI_UserFiles is refused. Paths must be
# plain (no spaces or shell characters): StartJMRI splits them.
#
# SIGKILL cannot be trapped. Then the backup stays, and this run's wrappers, deploy and
# launch_cats.sh refuse until it is gone. Recover: quit the PanelPro it left (its java runs with
# -Dorg.jmri.profile=<profile>), then
#   python3 tools/hosts/panelpro_profile.py restore --profile <profile.xml>

PP_LIVE_PROFILE_ID="My_JMRI_Railroad.3ef75bfd"
PP_PATCH="$ROOT/cats/scripts/patch_jmri_startup.py"
PP_PROFILE_PY="$ROOT/tools/hosts/panelpro_profile.py"
PP_PIDS=""
PP_JPID=""
PP_BACKED_UP=0
PP_TMP_FILES=()
PP_GUARD_DIR=""
PP_GUARD_SNAP=""
PP_FAIL_NOTE=""

pp_profile() {
  JMRI_HOME="${JMRI_HOME:-/Applications/JMRI}"
  STARTJMRI="$JMRI_HOME/PanelPro.app/Contents/MacOS/StartJMRI"
  PROFILE_XML="${JMRI_PROFILE_XML:-$HOME/Library/Preferences/JMRI/My_JMRI_Railroad.jmri/profile/profile.xml}"
  if [[ ! -f "$PROFILE_XML" ]]; then
    echo "profile.xml not found: $PROFILE_XML" >&2
    exit 1
  fi
  if [[ -n "${JMRI_PROFILE:-}" ]]; then
    PROFILE_ID="$JMRI_PROFILE"
  elif [[ -n "${JMRI_PROFILE_XML:-}" ]]; then
    PROFILE_ID="$(cd "$(dirname "$PROFILE_XML")/.." && pwd)"
  else
    PROFILE_ID="$PP_LIVE_PROFILE_ID"
  fi
  if [[ ! -x "$STARTJMRI" ]]; then
    echo "PanelPro StartJMRI not found: $STARTJMRI" >&2
    exit 1
  fi
  PP_USER_FILES="$(python3 "$PP_PROFILE_PY" check-profile --profile "$PROFILE_XML" --launch "$PROFILE_ID" \
    ${JMRI_USER_FILES:+--user-files "$JMRI_USER_FILES"})" || exit 1
  # PanelPro loads the tables of the checkout the wrapper lives in (main or a worktree).
  case "$ROOT" in
    "$HOME"/*) TABLES_URI="home:${ROOT#"$HOME"/}/jmri/layouts/hart/output/tables.xml" ;;
    *) TABLES_URI="$ROOT/jmri/layouts/hart/output/tables.xml" ;;
  esac
}

pp_jmri_running() {
  python3 "$PP_PROFILE_PY" jmri-running
}

pp_refuse_running() {
  if pp_jmri_running; then
    echo "$1" >&2
    exit "${2:-1}"
  fi
}

pp_begin() {
  local script="$1"
  python3 "$PP_PROFILE_PY" backup --profile "$PROFILE_XML" >/dev/null || exit 1
  PP_BACKED_UP=1
  trap pp_cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  python3 "$PP_PATCH" load-tables --profile "$PROFILE_XML" --tables "$TABLES_URI"
  python3 "$PP_PROFILE_PY" quiet-startup --profile "$PROFILE_XML" --run "$script"
  python3 "$PP_PROFILE_PY" seal --profile "$PROFILE_XML" >/dev/null
}

pp_guard_dir() {
  PP_GUARD_DIR="$1"
  PP_GUARD_SNAP="$(mktemp -d)"
  if [[ -d "$PP_GUARD_DIR" ]]; then
    cp -Rp "$PP_GUARD_DIR/." "$PP_GUARD_SNAP/"
  else
    rmdir "$PP_GUARD_SNAP"   # no folder before the run: a failed run removes it again
  fi
}

pp_launch() {
  local log="$1" ver jh
  if [[ -z "${JAVA_HOME:-}" ]]; then
    for ver in 21 17 11; do
      if jh=$(/usr/libexec/java_home -v "$ver" 2>/dev/null); then
        export JAVA_HOME="$jh"
        break
      fi
    done
  fi
  "$STARTJMRI" -p "$PROFILE_ID" >"$log" 2>&1 &
  PP_JPID=$!
  PP_PIDS="$PP_JPID"
  _pp_track
}

# Add every descendant of the processes already known (the launcher, then java) to PP_PIDS, so a
# java left behind by a dead launcher is still found.
_pp_track() {
  local todo="$PP_PIDS" pid kid
  while [[ -n "$todo" ]]; do
    set -- $todo
    pid="$1"
    shift
    todo="$*"
    for kid in $(pgrep -P "$pid" 2>/dev/null); do
      case " $PP_PIDS " in
        *" $kid "*) ;;
        *) PP_PIDS="$PP_PIDS $kid"; todo="$todo $kid" ;;
      esac
    done
  done
}

_pp_alive() {
  local st
  kill -0 "$1" 2>/dev/null || return 1
  st="$(ps -o stat= -p "$1" 2>/dev/null)"
  [[ -n "$st" && "$st" != Z* ]]
}

# A tracked pid is still ours when it is the launcher or a java on this profile (no pid reuse).
_pp_ours() {
  local cmd
  cmd="$(ps -o command= -p "$1" 2>/dev/null)"
  if [[ "$1" == "$PP_JPID" ]]; then
    [[ "$cmd" == *StartJMRI* ]]
  else
    [[ "$cmd" == *"org.jmri.profile=$PROFILE_ID"* ]]
  fi
}

_pp_live_pids() {
  local pid out=""
  for pid in $PP_PIDS; do
    if _pp_alive "$pid" && _pp_ours "$pid"; then
      out="$out $pid"
    fi
  done
  echo $out
}

# The poll interval: HART_PANELPRO_POLL when it is a number above 0 (fractions allowed), else the default given.
_pp_poll() {
  local v="${HART_PANELPRO_POLL:-}"
  if [[ -n "$v" ]]; then
    if [[ "$v" =~ ^[0-9]*\.?[0-9]+$ ]] && awk -v v="$v" 'BEGIN { exit !(v > 0) }'; then
      echo "$v"
      return
    fi
    echo "HART_PANELPRO_POLL=$v is not a number above 0; polling every $1 s" >&2
  fi
  echo "$1"
}

pp_wait_marker() {
  local marker="$1" deadline=$((SECONDS + $2)) interval="$3"
  while (( SECONDS < deadline )); do
    [[ -f "$marker" ]] && return 0
    _pp_track
    if [[ -z "$(_pp_live_pids)" ]]; then
      [[ -f "$marker" ]] && return 0
      return 1
    fi
    sleep "$(_pp_poll "$interval")"
  done
  [[ -f "$marker" ]] && return 0
  return 2
}

pp_wait_exit() {
  local deadline=$((SECONDS + $1))
  _pp_track
  while [[ -n "$(_pp_live_pids)" ]]; do
    (( SECONDS < deadline )) || return 1
    sleep "$(_pp_poll 1)"
    _pp_track
  done
  return 0
}

pp_stop_jmri() {
  local live deadline
  _pp_track
  live="$(_pp_live_pids)"
  [[ -n "$live" ]] || return 0
  echo "Stopping the PanelPro this run started (pids $live)" >&2
  kill -TERM $live 2>/dev/null || true
  deadline=$((SECONDS + ${HART_PANELPRO_KILL_WAIT:-30}))
  while [[ -n "$(_pp_live_pids)" ]] && (( SECONDS < deadline )); do
    sleep "$(_pp_poll 1)"
  done
  live="$(_pp_live_pids)"
  if [[ -n "$live" ]]; then
    echo "PanelPro ignored TERM; killing pids $live" >&2
    kill -KILL $live 2>/dev/null || true
    deadline=$((SECONDS + 5))          # KILL cannot be ignored; give the system a moment to remove them
    while [[ -n "$(_pp_live_pids)" ]] && (( SECONDS < deadline )); do
      sleep "$(_pp_poll 1)"
    done
  fi
  _pp_track
  live="$(_pp_live_pids)"
  if [[ -n "$live" ]]; then
    echo "Could not stop pids $live" >&2
    return 1
  fi
  return 0
}

pp_cleanup() {
  local rc=$?
  trap '' INT TERM HUP
  trap - EXIT
  set +e
  # a wrapper's note for a failed run (run_sml_discover.sh: tables.xml left as the discovery base)
  [[ "$rc" != 0 && -n "${PP_FAIL_NOTE:-}" ]] && echo "$PP_FAIL_NOTE" >&2
  if ! pp_stop_jmri; then
    # A PanelPro of this run still holds the profile: leave the backup for the owner.
    echo "PROFILE NOT RESTORED: quit that PanelPro, then run: python3 $PP_PROFILE_PY restore --profile $PROFILE_XML" >&2
    exit 1
  fi
  if [[ -n "$PP_GUARD_DIR" && "$rc" != 0 ]]; then
    rm -rf "$PP_GUARD_DIR"
    if [[ -n "$PP_GUARD_SNAP" && -d "$PP_GUARD_SNAP" ]]; then
      mkdir -p "$PP_GUARD_DIR" && cp -Rp "$PP_GUARD_SNAP/." "$PP_GUARD_DIR/"
    fi
    echo "Put $PP_GUARD_DIR back as it was before the run" >&2
  fi
  [[ -n "$PP_GUARD_SNAP" ]] && rm -rf "$PP_GUARD_SNAP"
  if [[ "$PP_BACKED_UP" == 1 ]]; then
    if python3 "$PP_PROFILE_PY" restore --force --profile "$PROFILE_XML" >&2; then
      PP_BACKED_UP=0
    else
      echo "PROFILE NOT RESTORED. Run: python3 $PP_PROFILE_PY restore --profile $PROFILE_XML" >&2
      rc=1
    fi
  fi
  rm -f ${PP_TMP_FILES[@]+"${PP_TMP_FILES[@]}"}
  exit "$rc"
}

#!/usr/bin/env bash
# One PanelPro run on this Mac, shared by the wrappers in jmri/layouts/hart/scripts
# (run_panelpro_smoke_test.sh, run_panelpro_stage1.sh, run_panelpro_traininfo_repair.sh,
# run_sml_discover.sh, run_nx_discover.sh, run_ctc_logic_smoke.sh). Source it after ROOT is set.
#
#   pp_profile            sets JMRI_HOME, STARTJMRI, PROFILE_XML, PROFILE_ID, PP_USER_FILES, TABLES_URI
#                         and stops unless JMRI_PROFILE and JMRI_PROFILE_XML name the same profile
#   pp_refuse_running MSG [CODE]   exits CODE (1) while CATS or PanelPro runs for this user
#   pp_begin              backs the profile up to <profile.xml>.hart-run.bak, sets the traps that put
#                         it back on any exit (also timeout, Ctrl-C, SIGTERM, SIGHUP), points Start Up at
#                         this checkout's tables and switches off the publishing Start Up scripts
#                         (patch_jmri_startup.py PUBLISHING_STARTUP_SCRIPTS)
#   pp_launch LOG         starts PanelPro on the profile in the background
#   pp_wait_marker MARKER SECONDS INTERVAL   0 marker written, 1 PanelPro quit first, 2 timed out
#   pp_wait_exit SECONDS  0 once the PanelPro this run started has quit, 1 if it still runs
#
# On exit the traps stop the PanelPro this run started (TERM, then KILL after HART_PANELPRO_KILL_WAIT
# seconds, default 30) before the profile goes back. Only the processes started by pp_launch are
# stopped, never another JMRI or CATS. HART_PANELPRO_TIMEOUT overrides a wrapper's marker timeout.
#
# Rehearsal on another profile: JMRI_PROFILE_XML=<name>.jmri/profile/profile.xml alone starts JMRI on
# that folder (JMRI_PROFILE, an id or a folder, must name the same profile). JMRI_USER_FILES names its
# user files folder, else it is read from the profile. Then nothing touches the live profile or
# ~/JMRI_UserFiles.
#
# SIGKILL (kill -9, a closed terminal that kills hard) cannot be trapped. The next run refuses
# while the backup is there. Recover: quit the PanelPro it left (its java runs with
# -Dorg.jmri.profile=<profile>), then
#   python3 cats/scripts/patch_jmri_startup.py restore --profile <profile.xml>

PP_LIVE_PROFILE_ID="My_JMRI_Railroad.3ef75bfd"
PP_PATCH="$ROOT/cats/scripts/patch_jmri_startup.py"
PP_JMRI_PROC='java .*(cats\.apps\.Crandic|apps\.PanelPro\.PanelPro|apps\.gui3\.dp3\.DecoderPro3|apps\.DecoderPro|apps\.DispatcherPro)'
PP_PIDS=""
PP_JPID=""
PP_BACKED_UP=0
PP_TMP_FILES=()

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
  PP_USER_FILES="$(python3 "$PP_PATCH" check-profile --profile "$PROFILE_XML" --launch "$PROFILE_ID" \
    ${JMRI_USER_FILES:+--user-files "$JMRI_USER_FILES"})" || exit 1
  # PanelPro loads the tables of the checkout the wrapper lives in (main or a worktree).
  case "$ROOT" in
    "$HOME"/*) TABLES_URI="home:${ROOT#"$HOME"/}/jmri/layouts/hart/output/tables.xml" ;;
    *) TABLES_URI="$ROOT/jmri/layouts/hart/output/tables.xml" ;;
  esac
}

pp_refuse_running() {
  if pgrep -u "$(id -u)" -f "$PP_JMRI_PROC" >/dev/null 2>&1; then
    echo "$1" >&2
    exit "${2:-1}"
  fi
}

pp_begin() {
  python3 "$PP_PATCH" backup --profile "$PROFILE_XML" >/dev/null || exit 1
  PP_BACKED_UP=1
  trap pp_cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  python3 "$PP_PATCH" load-tables --profile "$PROFILE_XML" --tables "$TABLES_URI"
  python3 "$PP_PATCH" disable-publishing --profile "$PROFILE_XML"
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

pp_wait_marker() {
  local marker="$1" deadline=$((SECONDS + $2)) interval="$3"
  while (( SECONDS < deadline )); do
    [[ -f "$marker" ]] && return 0
    _pp_track
    if [[ -z "$(_pp_live_pids)" ]]; then
      [[ -f "$marker" ]] && return 0
      return 1
    fi
    sleep "$interval"
  done
  [[ -f "$marker" ]] && return 0
  return 2
}

pp_wait_exit() {
  local deadline=$((SECONDS + $1))
  _pp_track
  while [[ -n "$(_pp_live_pids)" ]]; do
    (( SECONDS < deadline )) || return 1
    sleep 1
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
    sleep 1
  done
  live="$(_pp_live_pids)"
  if [[ -n "$live" ]]; then
    echo "PanelPro ignored TERM; killing pids $live" >&2
    kill -KILL $live 2>/dev/null || true
    sleep 1
  fi
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
  pp_stop_jmri
  if [[ "$PP_BACKED_UP" == 1 ]]; then
    if python3 "$PP_PATCH" restore --profile "$PROFILE_XML" >/dev/null; then
      PP_BACKED_UP=0
    else
      echo "PROFILE NOT RESTORED. Run: python3 $PP_PATCH restore --profile $PROFILE_XML" >&2
      rc=1
    fi
  fi
  rm -f ${PP_TMP_FILES[@]+"${PP_TMP_FILES[@]}"}
  exit "$rc"
}

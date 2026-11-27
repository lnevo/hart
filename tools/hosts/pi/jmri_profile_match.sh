# shellcheck shell=bash
# Which processes run a JMRI app, and which run one on a given JMRI profile, by command line. Bash 3.2 and up: the
# Mac runs it (panelpro_session.sh, the tests), the Pi runs it under bash 5.
#
# Where it is loaded: panelpro_session.sh and the Pi apply step source it (the apply step from the deploy drop,
# cats/scripts/pi/); pi_start_panelpro.sh and pi_quit_panelpro.sh send it ahead of their remote part, and the deploy
# sends it ahead of panelpro_restart_due.sh (tools/hosts/deploy/common.sh), since the Pi has no checkout to source it
# from.
#
# A command line names a profile in one of two words: -Dorg.jmri.profile=<id> (the JVM: JMRI's launchers, PanelPro
# -p <id> and cats.csh --profile=<id>, pass the profile to java this way) or --profile=<id> (the cats.csh shell as
# launch_cats.sh runs it, before it starts java). The id is the whole value: a name with no id suffix (TCS_MQTT)
# also takes its id (TCS_MQTT.3f32a166), and neither takes another profile that starts the same (TCS_MQTT_test).
#
# A JMRI app JVM (HART_JMRI_APP) that names no profile opened the one JMRI picked itself (the last used, or the only
# one): it counts as on every profile, so no check takes it for "not running".

# A JMRI or CATS JVM: hartlib.tables._JMRI_PROCESS, which tools/hosts/tests/test_jmri_profile_match.py holds it to.
HART_JMRI_APP='java .*(cats\.apps\.Crandic|apps\.PanelPro\.PanelPro|apps\.gui3\.dp3\.DecoderPro3|apps\.DecoderPro|apps\.DispatcherPro)'

# _jmri_profile_value WORD: print the profile WORD names (the part after -Dorg.jmri.profile= or --profile=); false
# when WORD names none.
_jmri_profile_value() {
  case "$1" in
    -Dorg.jmri.profile=*|--profile=*) printf '%s' "${1#*=}" ;;
    *) return 1 ;;
  esac
}

# _jmri_value_is VALUE ID: true when the profile VALUE is ID, or ID has no "." and VALUE is ID.<letters and digits>.
_jmri_value_is() {
  local value="$1" id="$2" suffix re='^[[:alnum:]]+$'
  [[ "$value" == "$id" ]] && return 0
  [[ "$id" != *.* && "$value" == "$id".* ]] || return 1
  suffix="${value#"$id".}"
  [[ $suffix =~ $re ]]
}

# jmri_cmd_names_profile CMD ID: true when a word of the command line CMD names the profile ID.
jmri_cmd_names_profile() {
  local id="$2" word value words=()
  [[ -n "$id" ]] || return 1
  read -r -a words <<<"$1"
  for word in ${words[@]+"${words[@]}"}; do
    case "$word" in             # _jmri_profile_value without its subshell: this runs for every word of every process
      -Dorg.jmri.profile=*|--profile=*) value="${word#*=}" ;;
      *) continue ;;
    esac
    _jmri_value_is "$value" "$id" && return 0
  done
  return 1
}

# jmri_cmd_names_a_profile CMD: true when a word of CMD names any profile.
jmri_cmd_names_a_profile() {
  local word words=()
  read -r -a words <<<"$1"
  for word in ${words[@]+"${words[@]}"}; do
    _jmri_profile_value "$word" >/dev/null && return 0
  done
  return 1
}

# jmri_cmd_on_profile CMD ID: true when CMD names the profile ID, or is a JMRI app JVM that names no profile.
jmri_cmd_on_profile() {
  [[ $1 == *profile=* || $1 =~ $HART_JMRI_APP ]] || return 1    # most processes: no word to read
  jmri_cmd_names_profile "$1" "$2" && return 0
  [[ $1 =~ $HART_JMRI_APP ]] && ! jmri_cmd_names_a_profile "$1"
}

# jmri_profile_procs ID: print "pid command line" of each process of this user on the profile ID
# (jmri_cmd_on_profile), in ps order. Exit 0 when one was found, 1 when none, 2 when ps could not list the processes.
jmri_profile_procs() {
  local id="$1" listing pid cmd found=1
  listing="$(ps -u "$(id -u)" -o pid=,args=)" || return 2
  while read -r pid cmd; do
    [[ -n "$pid" ]] || continue
    if jmri_cmd_on_profile "$cmd" "$id"; then
      echo "$pid $cmd"
      found=0
    fi
  done <<EOF
$listing
EOF
  return "$found"
}

# jmri_profile_pids ID: the pids of jmri_profile_procs ID, with its exit status.
jmri_profile_pids() {
  local procs state=0 pid rest
  procs="$(jmri_profile_procs "$1")" || state=$?
  while read -r pid rest; do
    [[ -n "$pid" ]] && echo "$pid"
  done <<EOF
$procs
EOF
  return "$state"
}

# jmri_profile_panelpro_pid ID: the pid of the PanelPro JVM on the profile ID; when none of the processes on it is
# one (CATS, its cats.csh shell, DecoderPro), the first of them. Exit status as jmri_profile_procs.
jmri_profile_panelpro_pid() {
  local procs state=0 pid cmd first="" re='^java .*apps\.PanelPro\.PanelPro'
  procs="$(jmri_profile_procs "$1")" || state=$?
  while read -r pid cmd; do
    [[ -n "$pid" ]] || continue
    [[ -n "$first" ]] || first="$pid"
    if [[ $cmd =~ $re ]]; then
      echo "$pid"
      return "$state"
    fi
  done <<EOF
$procs
EOF
  [[ -z "$first" ]] || echo "$first"
  return "$state"
}

# jmri_profile_running ID: exit 0 when a process of this user runs on the profile ID, 1 when none does, 2 when ps
# could not tell.
jmri_profile_running() {
  jmri_profile_pids "$1" >/dev/null
}

# jmri_app_running: exit 0 when a JMRI app or CATS JVM of this user runs (any profile), 1 when none does, 2 or more
# when pgrep could not tell.
jmri_app_running() {
  pgrep -u "$(id -u)" -f "$HART_JMRI_APP" >/dev/null
}

#!/usr/bin/env bash
# Shared by the deploy steps (sourced, never run): the host settings, the stamp facts, the ssh helpers with their
# shared connections, the lists of what is shipped, and the checks that more than one step needs.
#
# The steps, run in this order by tools/hosts/sync_hart_package.sh (the entry point):
#   gate.sh      every check; nothing is sent or installed (host gates, local gates, the Mac Store check,
#                a staging trial, a Windows probe)
#   stage.sh     builds the host packages once, into a folder
#   ship_mac.sh  installs on this Mac
#   ship_pi.sh   sends the Pi's package (rsync) and applies it
#   ship_win.sh  sends Windows' package (tar + scp) and applies it
# Each step can be run alone; the entry point passes what it knows (the stamp facts, the ssh sockets) in the
# environment so the steps of one run agree.
DEPLOY_STEPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DEPLOY_STEPS_DIR/../../.." && pwd)"
source "$ROOT/tools/hosts/profile_tables_guard.sh"
# Hosts: environment first, then tools/env/hart.env, then tools/env/defaults.env (via load_env.sh)
# (the same order the Python tools use through tools/hartlib/src/hartlib/hosts.py).
source "$ROOT/tools/env/load_env.sh"
WIN_HOST="$HART_WIN_SSH"
WIN_PORT="$HART_WIN_SSH_PORT"
PI_HOST="$HART_PI_SSH"
PI_USERFILES="$HART_PI_USERFILES"
WIN_USERFILES="$HART_WIN_USERFILES"
REWRITE="$ROOT/cats/scripts/rewrite_button_icon_paths.py"
# The repo is the master of the Operations Pro files (ADR-015). 0 restores the guards.
HART_OVERWRITE_OPS="${HART_OVERWRITE_OPS:-1}"
export HART_OVERWRITE_OPS
# What a step does comes from its flags only, never from the caller's environment: an exported DO_PI, DO_WIN or
# DRY_RUN changes nothing. (Steps pass facts to each other in HART_-prefixed variables: HART_GATED, HART_DEPLOY_*.)
DO_PI=0
DO_WIN=0
DRY_RUN=0
RESTART=0   # gate.sh: 1 while a PanelPro quit for this deploy must come back if the run stops
PI_STEP=0   # ship_pi.sh and the entry point: the same, from the Pi step

TABLES=""
if [[ -f "$ROOT/jmri/layouts/hart/output/tables.xml" ]]; then
  TABLES="$ROOT/jmri/layouts/hart/output/tables.xml"
fi

LIVE_PANELS=(
  HART_CTC.xml
  HART_ABS.xml
)

JYTHON_STARTUP_SCRIPTS=(
  "$ROOT/jmri/layouts/hart/scripts/hide_cats_desk_windows.py"
  "$ROOT/jmri/layouts/hart/scripts/panel_status.py"
  "$ROOT/jmri/layouts/hart/scripts/jmri_cmd_watcher.py"
  "$ROOT/jmri/layouts/hart/scripts/sts_car_sync.py"
  "$ROOT/jmri/scripts/signal_coordinator.py"
)

# load_parked: the features parked out of the active tables (hartlib.parked.PARKED: Entry/Exit, the Dispatcher System,
# the USS CTC machine). Their files outside tables.xml stay in the repo but are not shipped: the Dispatcher traininfo
# and options (jmri/layouts/hart/dispatcher) and the USS CTC icons and GUIObjects.xml (jmri/layouts/hart/ctc), and
# the jython that only serves them. Nothing here or in the host apply scripts removes copies already installed on a
# host: they stay until removed by hand (owner, 2026-11-17). Unparking a feature ships them again.
# Sets PARKED_DIRS, PARKED_JYTHON and HART_JYTHON_SCRIPTS; exits 1 when the list cannot be read.
load_parked() {
  PARKED_DIRS="$(PYTHONPATH="$ROOT/tools/hartlib/src" python3 -m hartlib.parked dirs)" \
    || { echo "cannot read the parked features (tools/hartlib/src/hartlib/parked.py)" >&2; exit 1; }
  PARKED_JYTHON="$(PYTHONPATH="$ROOT/tools/hartlib/src" python3 -m hartlib.parked jython)" \
    || { echo "cannot read the parked features (tools/hartlib/src/hartlib/parked.py)" >&2; exit 1; }
  HART_JYTHON_SCRIPTS=()
  local f
  for f in \
    jmri/layouts/hart/scripts/panel_status.py \
    jmri/layouts/hart/scripts/discover_sml.py \
    jmri/layouts/hart/scripts/hide_cats_desk_windows.py \
    jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py \
    jmri/layouts/hart/scripts/jmri_cmd_watcher.py \
    jmri/layouts/hart/scripts/sts_car_sync.py \
    jmri/layouts/hart/scripts/mimic_relay.py; do
    # a script that only serves a parked feature is not shipped (repair_dispatcher_traininfo.py)
    grep -qxF "$(basename "$f")" <<<"$PARKED_JYTHON" || HART_JYTHON_SCRIPTS+=("$f")
  done
}
# parked_dir REL: whether the repo folder REL (jmri/layouts/hart/dispatcher, jmri/layouts/hart/ctc) is parked
parked_dir() { grep -qxF "$1" <<<"$PARKED_DIRS"; }

# ---- the stamp: what is being shipped, recorded in cats/deploy_stamp.txt on every host a run installs ----
# (tools/hosts/deploy_status.sh reads it back). deploy_facts WARN takes the facts once per run and exports them, so
# the steps of one run write the same date and commit; a step run alone takes its own. With WARN=1 it also
# says so when the checkout is dirty.
deploy_facts() {
  if [[ -n "${HART_DEPLOY_COMMIT:-}" ]]; then
    DEPLOY_COMMIT="$HART_DEPLOY_COMMIT"; DEPLOY_BRANCH="$HART_DEPLOY_BRANCH"; DEPLOY_DIRTY="$HART_DEPLOY_DIRTY"
    DEPLOY_DIRTY_PATHS="$HART_DEPLOY_DIRTY_PATHS"; DEPLOY_SOURCE="$HART_DEPLOY_SOURCE"
    DEPLOY_REDEPLOY_FROM="$HART_DEPLOY_REDEPLOY_FROM"; DEPLOY_DATE="$HART_DEPLOY_DATE"; DEPLOY_FROM="$HART_DEPLOY_FROM"
    return 0
  fi
  DEPLOY_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
  DEPLOY_BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  local changes
  changes="$(git -C "$ROOT" status --porcelain 2>/dev/null || true)"
  DEPLOY_DIRTY=no
  DEPLOY_DIRTY_PATHS=0
  if [[ -n "$changes" ]]; then
    DEPLOY_DIRTY=yes
    DEPLOY_DIRTY_PATHS="$(printf '%s\n' "$changes" | wc -l | tr -d ' ')"
    if [[ "${1:-0}" == 1 ]]; then
      {
        echo "WARNING: this checkout has $DEPLOY_DIRTY_PATHS uncommitted or untracked path(s)."
        echo "  The hosts get files that are not in commit ${DEPLOY_COMMIT:0:12} ($DEPLOY_BRANCH); the stamp says dirty=yes."
        # sed reads all its input, so a long list cannot SIGPIPE printf under pipefail.
        printf '%s\n' "$changes" | sed -n '1,10s/^/    /p'
        [[ "$DEPLOY_DIRTY_PATHS" -le 10 ]] || echo "    ..."
      } >&2
    fi
  fi
  # tools/hosts/redeploy_commit.sh runs an older commit's deploy from a detached worktree, with
  # a clean environment that sets HART_REDEPLOY_FROM to the commit it was run from.
  DEPLOY_SOURCE=deploy
  DEPLOY_REDEPLOY_FROM=none
  if [[ -n "${HART_REDEPLOY_FROM:-}" ]]; then
    DEPLOY_SOURCE=redeploy
    DEPLOY_REDEPLOY_FROM="$HART_REDEPLOY_FROM"
  fi
  DEPLOY_DATE="$(date +%Y-%m-%dT%H:%M:%S%z)"
  DEPLOY_FROM="$(hostname -s 2>/dev/null || hostname)"
  export HART_DEPLOY_COMMIT="$DEPLOY_COMMIT" HART_DEPLOY_BRANCH="$DEPLOY_BRANCH" HART_DEPLOY_DIRTY="$DEPLOY_DIRTY" \
    HART_DEPLOY_DIRTY_PATHS="$DEPLOY_DIRTY_PATHS" HART_DEPLOY_SOURCE="$DEPLOY_SOURCE" \
    HART_DEPLOY_REDEPLOY_FROM="$DEPLOY_REDEPLOY_FROM" HART_DEPLOY_DATE="$DEPLOY_DATE" HART_DEPLOY_FROM="$DEPLOY_FROM"
}

# tables_facts WARN: the tables.xml shipped (hash) and whether it differs from the committed file. The Digicon boot
# rule is applied by the generator and only checked by the gate, so the hosts get exactly the committed bytes:
# nothing here rewrites tables.xml. With WARN=1 an uncommitted difference is a warning, not a stop.
tables_facts() {
  DEPLOY_TABLES_SHA=none
  DEPLOY_TABLES_MODIFIED=no
  [[ -n "$TABLES" ]] || return 0
  DEPLOY_TABLES_SHA="$(shasum -a 256 "$TABLES" | cut -d' ' -f1)"
  local committed_sha
  committed_sha="$(git -C "$ROOT" show "HEAD:jmri/layouts/hart/output/tables.xml" 2>/dev/null | shasum -a 256 | cut -d' ' -f1)"
  if [[ "$DEPLOY_TABLES_SHA" != "$committed_sha" ]]; then
    DEPLOY_TABLES_MODIFIED=yes
    if [[ "${1:-0}" == 1 ]]; then
      echo "WARNING: the tables.xml being shipped differs from commit ${DEPLOY_COMMIT:0:12} (uncommitted). Commit it after the deploy; the stamp says tables_modified_by_deploy=yes." >&2
    fi
  fi
}

# write_deploy_stamp FILE TARGET: key=value lines, one per fact.
write_deploy_stamp() {
  mkdir -p "$(dirname "$1")"
  cat >"$1" <<STAMP
# Layout deploy stamp, written by tools/hosts/sync_hart_package.sh. Read it with tools/hosts/deploy_status.sh.
commit=$DEPLOY_COMMIT
branch=$DEPLOY_BRANCH
dirty=$DEPLOY_DIRTY
dirty_paths=$DEPLOY_DIRTY_PATHS
tables_sha256=$DEPLOY_TABLES_SHA
tables_modified_by_deploy=$DEPLOY_TABLES_MODIFIED
date=$DEPLOY_DATE
deployed_from=$DEPLOY_FROM
target=$2
source=$DEPLOY_SOURCE
redeploy_from=$DEPLOY_REDEPLOY_FROM
STAMP
}

# ---- ssh ----
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
# Each host's calls share one ssh connection: the Pi's (preflight, unpulled check, drop folder, rsync,
# apply, restart check) on the socket "pi", Windows' (preflight, probe, drop folder, scp, unpack, apply,
# cleanup) on "win". The first call to a host opens a master on its socket in a folder made for this
# run, the rest reuse it, and the step that made the folder closes each master and removes it. The folder is passed
# to the other steps in HART_SSH_MUX_DIR, so one run keeps one connection per host. ControlPersist bounds
# a master left by a killed run. HART_SSH_MUX=0 turns reuse off for both hosts; HART_WIN_SSH_MUX=0
# turns it off for Windows only (OpenSSH for Windows, shared connections approved 2026-11-20).
PI_SSH_OPTS=()
WIN_SSH_OPTS=()
ssh_opts_init() {
  PI_SSH_OPTS=("${SSH_OPTS[@]}")
  WIN_SSH_OPTS=("${SSH_OPTS[@]}")
  [[ -n "${HART_SSH_MUX_DIR:-}" ]] || return 0
  [[ "${HART_SSH_MUX_PI:-0}" != 1 ]] || PI_SSH_OPTS+=(-o ControlMaster=auto -o "ControlPath=$HART_SSH_MUX_DIR/pi" -o ControlPersist=120)
  [[ "${HART_SSH_MUX_WIN:-0}" != 1 ]] || WIN_SSH_OPTS+=(-o ControlMaster=auto -o "ControlPath=$HART_SSH_MUX_DIR/win" -o ControlPersist=120)
}
# ssh_mux_open: uses the folder an earlier step made, or makes one for the hosts named (DO_PI, DO_WIN).
ssh_mux_open() {
  if [[ -z "${HART_SSH_MUX_DIR:-}" && "${HART_SSH_MUX:-1}" != "0" ]]; then
    local pi="$DO_PI" win="$DO_WIN"
    [[ "${HART_WIN_SSH_MUX:-1}" != "0" ]] || win=0
    if [[ "$pi" -eq 1 || "$win" -eq 1 ]]; then
      # A unix socket path is limited to about 104 bytes, and ssh adds a suffix while it binds.
      local parent="${TMPDIR:-/tmp}" dir
      # rsync -e splits its ssh command on whitespace, so the socket path must have none.
      [[ "${#parent}" -le 60 && "$parent" != *[[:space:]]* ]] || parent=/tmp
      if dir="$(mktemp -d "${parent%/}/hart-ssh.XXXXXX")"; then
        export HART_SSH_MUX_DIR="$dir" HART_SSH_MUX_OWNER="$$" HART_SSH_MUX_PI="$pi" HART_SSH_MUX_WIN="$win"
      else
        echo "Note: could not make an ssh socket folder; each host call opens its own connection." >&2
      fi
    fi
  fi
  ssh_opts_init
}
# ssh_mux_close: only the step that made the folder closes it.
ssh_mux_close() {
  [[ -n "${HART_SSH_MUX_DIR:-}" && "${HART_SSH_MUX_OWNER:-}" == "$$" ]] || return 0
  # Only a master that was opened is asked to exit (an unreachable host leaves no socket).
  if [[ -S "$HART_SSH_MUX_DIR/pi" ]]; then
    ssh -o "ControlPath=$HART_SSH_MUX_DIR/pi" -O exit "$PI_HOST" >/dev/null 2>&1 || true
  fi
  if [[ -S "$HART_SSH_MUX_DIR/win" ]]; then
    ssh -o "ControlPath=$HART_SSH_MUX_DIR/win" -p "$WIN_PORT" -O exit "$WIN_HOST" >/dev/null 2>&1 || true
  fi
  rm -rf "$HART_SSH_MUX_DIR"
  unset HART_SSH_MUX_DIR HART_SSH_MUX_OWNER
}
ssh_opts_init
ssh_pi() { ssh "${PI_SSH_OPTS[@]}" "$PI_HOST" "$@"; }
ssh_win() { ssh "${WIN_SSH_OPTS[@]}" -p "$WIN_PORT" "$WIN_HOST" "$@"; }
# SFTP needs "Subsystem sftp" in the Windows sshd_config (OpenSSH 10.4); fall back to
# the legacy scp protocol if a reinstall or reset has removed it.
scp_win() {
  scp "${WIN_SSH_OPTS[@]}" -P "$WIN_PORT" "$@" 2>/dev/null && return 0
  echo "scp over SFTP to Windows failed; retrying with the legacy protocol (-O). Check Subsystem sftp in sshd_config." >&2
  scp -O "${WIN_SSH_OPTS[@]}" -P "$WIN_PORT" "$@"
}

# PanelPro quit for this deploy (pi_quit_panelpro.sh --for-deploy leaves a marker) comes
# back up, also when the Pi step fails. panelpro_restart_due.sh drops a stale marker and
# never starts PanelPro next to CATS. One closed by hand stays closed. HART_PI_RESTART=0
# skips it.
pi_restart_if_due() {
  [[ "$DRY_RUN" -eq 0 && "${HART_PI_RESTART:-1}" != "0" ]] || return 0
  local due
  due="$(ssh_pi "bash -s" < "$ROOT/tools/hosts/pi/panelpro_restart_due.sh")" || due="unknown"
  case "$due" in
    yes)
      echo "Starting PanelPro on the Pi again (it was quit for this deploy)..."
      bash "$ROOT/tools/hosts/pi_start_panelpro.sh" \
        || echo "PanelPro did not start on the Pi; run tools/hosts/pi_start_panelpro.sh" >&2 ;;
    running) echo "Note: JMRI was running on the Pi during the deploy; restart it to load the new files." >&2 ;;
    stale) echo "The PanelPro quit-for-deploy marker on the Pi was over 2 h old; leaving PanelPro closed." ;;
    no) ;;
    *) echo "Could not check whether to start PanelPro on the Pi; run tools/hosts/pi_start_panelpro.sh if it should be up." >&2 ;;
  esac
}

# check_mac_store: this Mac's own Store check. A Store into ~/JMRI_UserFiles/tables.xml since the last deploy
# would be lost by the Mac install: stop instead. Run by the gate, and again by the install.
check_mac_store() {
  [[ -n "$TABLES" ]] || return 0
  local dir="${HOME}/JMRI_UserFiles"
  if profile_tables_unpulled "$TABLES" "$dir"; then
    echo "STOP: $dir/tables.xml changed since the last deploy (a PanelPro Store). Run make tables-pull: it keeps the Store in ~/JMRI_UserFiles-pulled; split it in a task worktree (tools/schematic/split_store.py) and merge that, then deploy. HART_OVERWRITE_PROFILE_TABLES=1 replaces it unkept." >&2
    return 1
  fi
}

# refuse_before_changing: the refusals every step that changes something makes first, so a step run alone is as
# careful as the gate: HART_TABLES (for checks only) and a PanelPro wrapper backup left on the profile.
refuse_before_changing() {
  refuse_hart_tables "deploy"
  refuse_unrestored_profile "deploy"
}

# preflight_hosts: Windows is kept matching the Pi, and the Pi step runs first. A host that does not answer would
# stop the run after the other host, the Mac or the repo's tables.xml had already changed, so ask every host named
# (DO_PI, DO_WIN) for one ssh no-op before anything is sent. It runs before the Pi's unpulled check, which needs ssh
# too and would name the wrong cause for a Pi that is down. A dry run and --stage-only skip it.
preflight_hosts() {
  local down=() pi_up=0 h
  if [[ "$DO_PI" -eq 1 ]]; then
    if ssh_pi true </dev/null >/dev/null; then pi_up=1; else down+=("the Pi ($PI_HOST)"); fi
  fi
  # "exit 0" also runs under cmd.exe, the Windows OpenSSH shell.
  if [[ "$DO_WIN" -eq 1 ]] && ! ssh_win "exit 0" </dev/null >/dev/null; then
    down+=("Windows ($WIN_HOST port $WIN_PORT)")
  fi
  [[ "${#down[@]}" -gt 0 ]] || return 0
  for h in "${down[@]}"; do
    echo "STOP: cannot reach $h over ssh." >&2
  done
  echo "No file was sent to or installed on any host, and the Mac install did not run. Deploy again once every host answers." >&2
  # A PanelPro quit for this deploy comes back, as after any stopped Pi deploy: the one thing done on a host.
  if [[ "$pi_up" -eq 1 ]]; then
    echo "The Pi answered: PanelPro there is started again if it was quit for this deploy (a line below says so)." >&2
    pi_restart_if_due
  fi
  exit 1
}

# pi_stop MESSAGE: stop the run, with PanelPro back up first.
pi_stop() {
  echo "$1" >&2
  RESTART=0
  PI_STEP=0
  pi_restart_if_due
  exit 1
}

# ops_repo_sha: the hash unpulled_changes.sh and pull_ops.sh make of the six Operations files (cat in this order, sha256),
# here of the copies this checkout ships.
ops_repo_sha() {
  local f dir="$ROOT/jmri/layouts/hart/operations"
  for f in Operations.xml OperationsCarRoster.xml OperationsEngineRoster.xml OperationsLocationRoster.xml \
           OperationsRouteRoster.xml OperationsTrainRoster.xml; do
    cat "$dir/$f" 2>/dev/null || true
  done | shasum -a 256 | cut -d' ' -f1
}

# check_pi_unpulled: what the owner changed on the Pi since the last deploy or pull would be replaced: Operations
# Pro saves its files as the session runs, and a PanelPro Store rewrites tables.xml. Nothing is sent. Unless
# HART_NO_AUTOPULL=1 the gate first saves what it found (autopull_pi_changes), then stops anyway: the person
# reviews the pulled files, and a deploy never ships over a Store that is not split in.
# HART_DISCARD_PI_CHANGES=1 skips the check and replaces them (the owner's call).
check_pi_unpulled() {
  [[ "${HART_DISCARD_PI_CHANGES:-0}" != "1" ]] || return 0
  local generated_sha split_shas unpulled msg
  # the generated tables.xml is the reference when the Pi has none (no stamp, no pull): a file unlike it may be a Store
  generated_sha="$(shasum -a 256 "$ROOT/jmri/layouts/hart/output/tables.xml" 2>/dev/null | cut -d' ' -f1)"
  split_shas="$(hart_split_shas "$ROOT" | tr '\n' ' ' | sed 's/ *$//')"
  # The Operations files this checkout would ship count as taken: a Pi session equal to them (an auto-pulled one,
  # once it is committed and merged, and this deploy runs from that) is not "changed" (unpulled_changes.sh, ops:<sha>)
  split_shas="ops:$(ops_repo_sha)${split_shas:+ $split_shas}"
  if ! unpulled="$(ssh_pi "bash -s -- '$PI_USERFILES' '$generated_sha'${split_shas:+ $split_shas}" < "$ROOT/tools/hosts/pi/unpulled_changes.sh")"; then
    pi_stop "STOP: could not check the Pi for unpulled changes. HART_DISCARD_PI_CHANGES=1 deploys without the check."
  fi
  if [[ -n "$unpulled" ]]; then
    # Never pull into a redeploy's temporary or detached worktree: it is thrown away.
    if [[ "${HART_NO_AUTOPULL:-0}" != "1" && -z "${HART_REDEPLOY_FROM:-}" ]] \
       && git -C "$ROOT" symbolic-ref -q HEAD >/dev/null 2>&1; then
      autopull_pi_changes "$unpulled"   # always stops
    fi
    msg=""
    grep -qx ops <<<"$unpulled" && msg+="STOP: the Pi's Operations Pro files changed since the last deploy or pull. Run make ops-pull and commit first."$'\n'
    grep -qx tables <<<"$unpulled" && msg+="STOP: the Pi's tables.xml changed since the last deploy (a PanelPro Store). Run make tables-pull-pi: it keeps the Store in ~/JMRI_UserFiles-pulled; split it in a task worktree (tools/schematic/split_store.py) and merge that, then deploy (this deploy would replace the Pi's file with the generated tables.xml)."$'\n'
    pi_stop "${msg}HART_DISCARD_PI_CHANGES=1 replaces them anyway."
  fi
}

# autopull_pi_changes UNPULLED: save what check_pi_unpulled found, then stop (T9a). The same scripts a person runs:
# tools/ops/pull_tables_pi.sh keeps a Store in the pulled folder with its base (PanelPro may stay up for it);
# tools/ops/pull_ops.sh --no-mark writes the Operations files into the checkout it runs from and leaves the Pi
# unmarked, so the session counts as pulled only once the repo holds it (check_pi_unpulled compares the Pi's files
# with this checkout's; a deploy before the merge stops again). From the main checkout (which stays clean for
# deploys) it runs in a worktree: an existing ops-pull-* one is reused, else a new one (make wt TOPIC=ops-pull-<stamp>).
# The Operations pull needs JMRI closed: PanelPro is quit first with pi_quit_panelpro.sh --for-deploy, and pi_stop's
# restart brings it back. The operating flag's hook has already refused anything that reaches the Pi while it is set.
# A pull failure stops saying so and what was and was not kept. Test hooks (the scripts are stubbed in tests):
# HART_AUTOPULL_QUIT, HART_AUTOPULL_TABLES, HART_AUTOPULL_OPS (script), HART_AUTOPULL_NEWWT (prints the new
# worktree's path), HART_AUTOPULL_RMWT (removes it: path, topic), HART_AUTOPULL_WT_DIR (where ops-pull-* live),
# HART_AUTOPULL_FROM_MAIN (1/0).
autopull_pi_changes() {
  local unpulled="$1" out saved target topic from_main kept="" failed="" rc made=0 wtdir existing
  echo "The Pi has changes that a deploy would replace; saving them first (HART_NO_AUTOPULL=1 only stops)."
  if grep -qx tables <<<"$unpulled"; then
    if out="$(bash "${HART_AUTOPULL_TABLES:-$ROOT/tools/ops/pull_tables_pi.sh}" 2>&1)"; then
      echo "$out"
      saved="$(sed -n "s/^Pulled: the Pi.s Store is kept as \(.*\) (outside every checkout).*/\1/p" <<<"$out" | head -1)"
      if [[ -n "$saved" ]]; then
        kept+="kept the Pi's Store as $saved; split it (python3 tools/schematic/split_store.py $saved), merge, then deploy"$'\n'
      else
        failed+="the Store pull kept nothing (see above); nothing was kept for the Store"$'\n'
      fi
    else
      echo "$out" >&2
      failed+="the pull of the Pi's Store failed; nothing was kept for it"$'\n'
    fi
  fi
  if grep -qx ops <<<"$unpulled"; then
    rc=0
    if ! bash "${HART_AUTOPULL_QUIT:-$ROOT/tools/hosts/pi_quit_panelpro.sh}" --for-deploy; then
      rc=1
      failed+="could not quit PanelPro on the Pi (tools/hosts/pi_quit_panelpro.sh --for-deploy), so the Operations pull failed and nothing was kept for the Operations files"$'\n'
    fi
    from_main="${HART_AUTOPULL_FROM_MAIN:-}"
    if [[ -z "$from_main" ]]; then
      if [[ "$(git -C "$ROOT" rev-parse --git-dir 2>/dev/null)" == "$(git -C "$ROOT" rev-parse --git-common-dir 2>/dev/null)" ]]; then from_main=1; else from_main=0; fi
    fi
    target="$ROOT"
    if [[ "$rc" -eq 0 && "$from_main" == "1" ]]; then
      wtdir="${HART_AUTOPULL_WT_DIR:-$ROOT/.claude/worktrees}"
      existing="$(ls -d "$wtdir"/ops-pull-* 2>/dev/null | tail -1 || true)"
      if [[ -n "$existing" && -d "$existing" ]]; then
        target="$existing"   # an earlier auto-pull not merged yet
      else
        topic="ops-pull-$(date +%Y%m%d-%H%M%S)"
        if [[ -n "${HART_AUTOPULL_NEWWT:-}" ]]; then
          target="$(bash "$HART_AUTOPULL_NEWWT" "$topic")" || rc=1
        else
          target="$(python3 "$ROOT/tools/agent/worktrees.py" new "$topic")" || rc=1
        fi
        made=1
        if [[ "$rc" -ne 0 || ! -d "$target" ]]; then
          rc=1
          failed+="could not make the worktree $topic for the Operations pull; nothing was kept for the Operations files"$'\n'
        fi
      fi
    fi
    if [[ "$rc" -eq 0 ]]; then
      if out="$(cd "$target" && bash "${HART_AUTOPULL_OPS:-$target/tools/ops/pull_ops.sh}" --no-mark 2>&1)"; then
        echo "$out"
        kept+="brought the Pi's Operations session into $target/jmri/layouts/hart/operations; review, commit and merge it, then deploy from the updated main (the Pi counts as pulled only once the repo holds these files)"$'\n'
      else
        echo "$out" >&2
        failed+="the pull of the Pi's Operations files failed (see above); nothing was kept for them"
        if [[ "$made" -eq 1 ]]; then
          if [[ -n "${HART_AUTOPULL_RMWT:-}" ]]; then
            bash "$HART_AUTOPULL_RMWT" "$target" "$topic" && failed+="; the new worktree $target was removed" || failed+="; the new worktree $target was left (remove it)"
          elif git -C "$ROOT" worktree remove --force "$target" >/dev/null 2>&1; then
            git -C "$ROOT" branch -D "agent/claude/$topic" >/dev/null 2>&1 || true
            failed+="; the new worktree $target was removed"
          else
            failed+="; the new worktree $target was left (remove it)"
          fi
        elif [[ "$target" == "$ROOT" ]]; then
          failed+=" (check git status in jmri/layouts/hart/operations)"
        fi
        failed+=$'\n'
      fi
    fi
  fi
  if [[ -n "$failed" ]]; then
    pi_stop "${kept}STOP: the pull failed. ${failed}Nothing was shipped. HART_DISCARD_PI_CHANGES=1 replaces the Pi's files anyway."
  fi
  pi_stop "${kept}STOP: the Pi's changes are saved, not shipped. HART_DISCARD_PI_CHANGES=1 replaces them anyway."
}

# check_windows_can_take_package: Windows can take the package. The tarball is made here, so tar, scp and a temp file
# must work; the temp folder on Windows and its tar (which unpacks it) are asked for with a folder made and removed
# again. Nothing at all in a dry run (no ssh, and --stage-only needs no scp).
check_windows_can_take_package() {
  [[ "$DO_WIN" -eq 1 && "$DRY_RUN" -eq 0 ]] || return 0
  local tool tgz_probe
  for tool in tar scp; do
    command -v "$tool" >/dev/null 2>&1 || {
      echo "STOP: Windows needs $tool on this Mac to send the package, and it is not on PATH. Nothing was sent to any host." >&2
      exit 1
    }
  done
  tgz_probe="$(mktemp "${TMPDIR:-/tmp}/hart-pkg.XXXXXX")" || {
    echo "STOP: Windows needs a temporary file on this Mac for the package (mktemp failed in ${TMPDIR:-/tmp}). Nothing was sent to any host." >&2
    exit 1
  }
  rm -f "$tgz_probe"
  # Windows OpenSSH is cmd.exe; the probe runs in PowerShell like the real steps.
  if ! ssh_win "powershell -NoProfile -Command \"\$d = Join-Path \$env:TEMP ('hart-probe-' + [guid]::NewGuid().ToString('N')); New-Item -ItemType Directory \$d | Out-Null; Remove-Item -LiteralPath \$d -Force; if (-not (Get-Command tar -ErrorAction SilentlyContinue)) { exit 1 }\"" </dev/null >/dev/null; then
    echo "STOP: Windows ($WIN_HOST port $WIN_PORT) cannot take the package: it did not give a temp folder, or it has no tar. Nothing was sent to any host, and the Mac install did not run." >&2
    exit 1
  fi
}
